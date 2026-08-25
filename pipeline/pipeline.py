

# pipeline/pipeline.py
"""
Pipeline complet d'analyse de marché SaaS.

Flux :
    1. Analyse du projet (DSPy)           -> ProjectInfo
    2. Génération de requêtes (DSPy)      -> AnalysisOutput
    3. Recherche web (Tavily)             -> search results
    4. Scraping (Firecrawl)               -> ScrapingStats
    5. Nettoyage (ContentCleaner)         -> CleaningResult[]
    6. Chunking (ChunkOrchestrator)       -> Chunk[]
    7. Embedding + Indexation (ChromaDB)  -> collection créée et peuplée
    8. Expert agents (parallélisés)       -> liste de SectionAnalysis
    9. Génération de rapport              -> ReportSynthesisResult

Chaque exécution crée :
    - un nouveau dossier de projet horodaté
    - une nouvelle collection ChromaDB dédiée

Résilience :
    - Chaque étape est exécutée via `_run_step_safely`, qui uniformise
      la gestion d'erreur (log + fallback + statut) pour toutes les étapes.
    - Le pipeline peut reprendre à partir des artefacts déjà sauvegardés
      sur disque via `resume=True`, évitant de refaire des appels
      réseau/LLM coûteux après un crash partiel.
    - Les appels réseau (Tavily, Firecrawl) sont protégés par un
      mécanisme de retry avec backoff exponentiel.
"""

from __future__ import annotations

import contextvars
import functools
import json
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.Persistence import build_ragas_dataset, save_ragas_dataset
from config import CleanerConfig, ChunkerConfig
from pipeline.helpers import project_info_to_dict, slugify
from pipeline.utils import analysis_outputs_to_question_inputs, log_step
from queries_generator.models import AnalysisOutput
from scraping_cleaning.models import CleaningResult, ScrapingStats
from utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# LOGGING CONTEXT (traçabilité multi-étapes / multi-runs)
# ============================================================================

_run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")


def _new_run_id(project_name: str) -> str:
    return f"{slugify(project_name[:20])}-{uuid.uuid4().hex[:8]}"


def _log_extra(**kwargs: Any) -> Dict[str, Any]:
    return {"run_id": _run_id_var.get(), **kwargs}


def timed_step(step_name: str):
    """Mesure la durée d'une étape et logue entrée/sortie/erreur de façon uniforme."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            extra = _log_extra(step=step_name)
            start = time.perf_counter()
            logger.debug("Etape '%s' demarree", step_name, extra=extra)
            try:
                result = func(self, *args, **kwargs)
                logger.info(
                    "Etape '%s' terminee en %.2fs",
                    step_name, time.perf_counter() - start, extra=extra,
                )
                return result
            except Exception:
                logger.exception(
                    "Etape '%s' echouee apres %.2fs",
                    step_name, time.perf_counter() - start, extra=extra,
                )
                raise

        return wrapper

    return decorator


def with_retries(max_attempts: int = 3, base_delay: float = 2.0):
    """
    Retry avec backoff exponentiel pour les appels réseau instables
    (Tavily, Firecrawl). Ne masque pas l'erreur : la relève après
    épuisement des tentatives.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Tentative %d/%d echouee pour '%s' (%s). Nouvel essai dans %.1fs",
                        attempt, max_attempts, func.__name__, exc, delay,
                        extra=_log_extra(),
                    )
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


# ------------------------------------------------------------------
# Imports optionnels (selon les dépendances installées)
# ------------------------------------------------------------------

try:
    from clients import APIClients
except ImportError:
    logger.warning("Module 'clients' indisponible (APIClients desactive)")
    APIClients = None

try:
    from project_analysis.project_analyser import ProjectAnalyser
except ImportError:
    logger.warning("Module 'project_analysis' indisponible")
    ProjectAnalyser = None

try:
    from queries_generator.query_generator import MarketAnalysisQueryPipelineExecuter
except ImportError:
    logger.warning("Module 'queries_generator' indisponible")
    MarketAnalysisQueryPipelineExecuter = None

try:
    from web_search.searcher import WebSearchEngine
except ImportError:
    logger.warning("Module 'web_search' indisponible")
    WebSearchEngine = None

try:
    from scraping_cleaning.firecrawl_scraper import FirecrawlMarkdownCollector
except ImportError:
    logger.warning("Module 'scraping.firecrawl_scraper' indisponible")
    FirecrawlMarkdownCollector = None

try:
    from scraping_cleaning.content_cleaner import ContentCleaner
except ImportError:
    logger.warning("Module 'scraping.content_cleaner' indisponible")
    ContentCleaner = None

try:
    from chunking.chunk_orchestrator import ChunkOrchestrator
except ImportError:
    logger.warning("Module 'chunking' indisponible")
    ChunkOrchestrator = None

try:
    from embedding.chroma_manager import ChromaManager
except ImportError:
    logger.warning("Module 'embedding' indisponible")
    ChromaManager = None

try:
    from agents.Agents import SECTION_AGENTS
    from agents.models import SectionAnalysis
    from agents.report_synthesis_agent import ReportSynthesisAgent

    AGENTS_AVAILABLE = True
except ImportError:
    logger.warning(
        "Module 'agents' indisponible (dependances manquantes: dspy, openai). "
        "Les etapes 8 et 9 seront sautees."
    )
    AGENTS_AVAILABLE = False
    SECTION_AGENTS = None
    SectionAnalysis = None
    ReportSynthesisAgent = None


# ============================================================================
# Configuration d'une exécution
# ============================================================================

@dataclass
class PipelineRunConfig:
    """
    Configuration centralisée d'un run. Regroupe tous les paramètres
    auparavant éclatés entre arguments de fonction et variables
    d'environnement, pour un contrat explicite et testable.
    """

    project_name: str
    project_description: str
    project_info: Optional[Dict[str, Any]] = None

    num_queries: int = 4
    search_max_results: int = 5

    skip_embedding: bool = False
    skip_agents: bool = False

    llm_model: str = "openai/gpt-oss-20b:free"
    retrieval_method: str = "M4c"
    chunks_per_query: int = 30

    firecrawl_api_key: Optional[str] = None

    # Reprend l'exécution à partir des artefacts JSON déjà présents sur
    # disque plutôt que de refaire les appels réseau/LLM déjà effectués.
    resume: bool = False

    # Parallélisme pour l'étape 8 (agents indépendants par section).
    max_parallel_agents: int = 4

    def __post_init__(self):
        self.firecrawl_api_key = self.firecrawl_api_key or os.environ.get(
            "FIRECRAWL_API_KEY", ""
        )


@dataclass
class StepResult:
    """Résultat uniforme d'une étape, quel que soit son statut."""

    status: str  # "ok" | "skipped" | "failed"
    data: Any = None
    reason: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> Dict[str, Any]:
        summary = {"status": self.status, **self.meta}
        if self.reason:
            summary["reason"] = self.reason
        return summary


# ============================================================================
# Pipeline
# ============================================================================

class Pipeline:
    """Orchestrateur de bout en bout pour l'analyse de marché SaaS."""

    def __init__(
        self,
        output_base_dir: str = "outputs",
        chroma_persist_dir: str = "data/chromadb",
        embedding_model: str = "BAAI/bge-m3",
    ):
        log_step(0, "Initialisation du pipeline")

        self.output_base_dir = Path(output_base_dir)
        self.chroma_persist_dir = chroma_persist_dir
        self.embedding_model = embedding_model
        self.project_dir: Optional[Path] = None

        # Composants initialisés paresseusement
        self._analyser = None
        self._query_generator = None
        self._search_engine = None
        self._crawler = None
        self._cleaner = None
        self._chunker = None
        self._chroma = None

        if APIClients is None:
            logger.error("APIClients indisponible: le pipeline ne peut pas demarrer.")
            raise ImportError("Le module 'clients' (APIClients) est requis.")

        start = time.perf_counter()
        try:
            # Instancié une seule fois et réutilisé partout (évite de
            # recréer des clients HTTP à chaque accès à une propriété).
            self.api_client = APIClients()
        except Exception:
            logger.exception("Echec de l'initialisation des clients API")
            raise

        logger.info(
            "Pipeline initialise en %.1fms (output_dir=%s, chroma_dir=%s, embedding_model=%s)",
            (time.perf_counter() - start) * 1000,
            self.output_base_dir, self.chroma_persist_dir, self.embedding_model,
        )

    # ------------------------------------------------------------------
    # Accès paresseux aux composants
    # ------------------------------------------------------------------

    @property
    def analyser(self):
        if ProjectAnalyser is None:
            raise ImportError("ProjectAnalyser necessite 'dspy' et 'openai'.")
        if self._analyser is None:
            self._analyser = ProjectAnalyser()
        return self._analyser

    @property
    def query_generator(self):
        if MarketAnalysisQueryPipelineExecuter is None:
            raise ImportError("MarketAnalysisQueryPipelineExecuter necessite 'dspy'.")
        if self._query_generator is None:
            self._query_generator = MarketAnalysisQueryPipelineExecuter()
        return self._query_generator

    @property
    def search_engine(self):
        if WebSearchEngine is None:
            raise ImportError("WebSearchEngine necessite 'tavily'.")
        if self._search_engine is None:
            self._search_engine = WebSearchEngine(client=self.api_client.tavily_client)
        return self._search_engine

    @property
    def crawler(self):
        if FirecrawlMarkdownCollector is None:
            raise ImportError("FirecrawlMarkdownCollector necessite 'firecrawl'.")
        if self._crawler is None:
            self._crawler = FirecrawlMarkdownCollector(client=self.api_client.firecrawl_client)
        return self._crawler

    @property
    def cleaner(self):
        if ContentCleaner is None:
            raise ImportError("ContentCleaner non disponible.")
        if self._cleaner is None:
            self._cleaner = ContentCleaner(
                project_dir=str(self.project_dir), config=CleanerConfig()
            )
        return self._cleaner

    @property
    def chunker(self):
        if ChunkOrchestrator is None:
            raise ImportError("ChunkOrchestrator non disponible.")
        if self._chunker is None:
            self._chunker = ChunkOrchestrator(config=ChunkerConfig())
        return self._chunker

    @property
    def chroma(self):
        if ChromaManager is None:
            raise ImportError("ChromaManager necessite 'chromadb' et 'sentence-transformers'.")
        if self._chroma is None:
            self._chroma = ChromaManager(
                persist_directory=self.chroma_persist_dir,
                embedding_model=self.embedding_model,
            )
        return self._chroma

    @property
    def llm_client(self):
        """Client LLM partagé, réutilisé depuis self.api_client (pas de recréation)."""
        llm = self.api_client.lm_client
        if not llm:
            raise ValueError("Le client LLM (lm_client) n'a pas pu etre initialise.")
        return llm

    # ------------------------------------------------------------------
    # Utilitaires projet / collection
    # ------------------------------------------------------------------

    def _create_project_dir(self, project_name: str) -> Path:
        slug = slugify(project_name[:60])
        base_dir = self.output_base_dir / "projects"
        base_dir.mkdir(parents=True, exist_ok=True)

        candidate = base_dir / slug
        if candidate.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            candidate = base_dir / f"{slug}_{timestamp}"
            counter = 1
            while candidate.exists():
                candidate = base_dir / f"{slug}_{timestamp}_{counter}"
                counter += 1

        project_dir = candidate
        project_dir.mkdir(parents=True, exist_ok=True)
        for sub in (
            "analysis", "queries", "search", "scraped",
            "cleaned", "chunks", "index", "agents", "report",
        ):
            (project_dir / sub).mkdir(exist_ok=True)

        logger.info("Dossier projet: %s", project_dir)
        return project_dir

    def _resume_project_dir(self, project_name: str) -> Path:
        """
        En mode resume, réutilise le dernier dossier de ce projet
        (au lieu d'en créer un nouveau), pour retrouver les artefacts
        déjà sauvegardés.
        """
        base_dir = self.output_base_dir / "projects"
        slug = slugify(project_name[:60])
        candidates = sorted(base_dir.glob(f"{slug}*"), key=lambda p: p.stat().st_mtime)
        if candidates:
            project_dir = candidates[-1]
            logger.info("Mode resume: reutilisation du dossier %s", project_dir)
            return project_dir
        logger.warning(
            "Mode resume demande mais aucun dossier existant pour '%s'; creation d'un nouveau.",
            project_name,
        )
        return self._create_project_dir(project_name)

    def _generate_collection_name(self, project_info: Dict[str, Any]) -> str:
        sector = slugify(project_info.get("product_sector", "project"), 30)
        industry = slugify(project_info.get("customer_industry", ""), 20)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts = [sector] + ([industry] if industry else []) + [timestamp]
        return "_".join(parts)

    def _load_json_if_exists(self, path: Path) -> Optional[Any]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.warning("Impossible de relire %s, ignore.", path, extra=_log_extra())
        return None

    # ------------------------------------------------------------------
    # Wrapper uniforme d'exécution d'étape (gestion d'erreur + fallback)
    # ------------------------------------------------------------------

    def _run_step_safely(
        self,
        step_label: str,
        step_fn: Callable[[], Any],
        *,
        fallback: Any = None,
        required: bool = False,
    ) -> StepResult:
        """
        Exécute une étape et uniformise son résultat.

        - required=True  : une exception ici fait échouer tout le pipeline.
        - required=False : une exception est capturée, loguée avec sa
          stack trace complète, et un `fallback` est utilisé à la place
          pour permettre au pipeline de continuer.
        """
        extra = _log_extra(step=step_label)
        try:
            data = step_fn()
            return StepResult(status="ok", data=data)
        except Exception as exc:
            if required:
                logger.exception(
                    "Etape critique '%s' echouee: arret du pipeline.",
                    step_label, extra=extra,
                )
                raise
            logger.warning(
                "Etape '%s' echouee, fallback applique.",
                step_label, exc_info=True, extra=extra,
            )
            return StepResult(status="skipped", data=fallback, reason=str(exc)[:200])

    # ------------------------------------------------------------------
    # Etape 1 : Analyse du projet
    # ------------------------------------------------------------------

    @timed_step("analyse_projet")
    def _step_analyze_project(self, description: str) -> Dict[str, Any]:
        log_step(1, "ANALYSE DU PROJET")
        extra = _log_extra()

        project_info = self.analyser.analyse_project(description)
        if project_info is None:
            raise RuntimeError("L'analyse du projet a retourne None.")

        project_info_dict = project_info_to_dict(project_info)

        analysis_path = self.project_dir / "analysis" / "project_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(project_info_dict, f, ensure_ascii=False, indent=4)

        logger.info(
            "Analyse sauvegardee (secteur=%s) -> %s",
            project_info_dict.get("product_sector", "n/a"), analysis_path, extra=extra,
        )
        return project_info_dict

    @staticmethod
    def _fallback_project_info(description: str) -> Dict[str, Any]:
        """Project info générique utilisé quand l'analyse LLM échoue."""
        return {
            "country": "France",
            "customer_industry": "Restauration",
            "product_sector": "Hospitality SaaS",
            "software_category": "Restaurant Management System",
            "market_category": "Restaurant SaaS Market",
            "business_model": "B2B SaaS",
            "target_market": "Restaurants independants",
            "personas": [],
            "value_proposition": description[:200],
            "primary_keywords": [],
            "secondary_keywords": [],
            "potential_competitors": [],
            "raw_description": description,
        }

    # ------------------------------------------------------------------
    # Etape 2 : Génération de requêtes
    # ------------------------------------------------------------------

    @timed_step("generation_requetes")
    def _step_generate_queries(
        self, project_info_dict: Dict[str, Any], num_queries: int
    ) -> Dict[str, Any]:
        log_step(2, "GENERATION DE REQUETES")
        extra = _log_extra()

        queries = self.query_generator.all_sections(
            project_info=project_info_dict,
            num_queries=num_queries,
            output_dir=self.project_dir / "queries",
        )

        queries_path = self.project_dir / "queries" / "all_queries.json"
        with open(queries_path, "w", encoding="utf-8") as f:
            json.dump(queries, f, ensure_ascii=False, indent=4)

        logger.info(
            "Requetes generees pour %d section(s) -> %s",
            len(queries) if hasattr(queries, "__len__") else -1, queries_path, extra=extra,
        )
        return queries

    # ------------------------------------------------------------------
    # Etape 3 : Recherche web
    # ------------------------------------------------------------------

    @with_retries(max_attempts=3, base_delay=2.0)
    def _call_search_batch(self, queries: Dict[str, Any], max_results: int):
        return self.search_engine.search_batch(queries, max_results=max_results)

    @timed_step("recherche_web")
    def _step_web_search(
        self, queries: Dict[str, Any], max_results: int
    ) -> Dict[str, Any]:
        log_step(3, "RECHERCHE WEB")
        extra = _log_extra()

        if not queries:
            raise ValueError("Aucune requete disponible pour la recherche web.")

        search_results = self._call_search_batch(queries, max_results)

        total_hits = sum(
            len(v) if isinstance(v, list) else 0 for v in search_results.values()
        )
        search_path = self.project_dir / "search" / "search_results.json"
        with open(search_path, "w", encoding="utf-8") as f:
            json.dump(search_results, f, ensure_ascii=False, indent=4)

        logger.info(
            "Recherche web: %d resultat(s) -> %s", total_hits, search_path, extra=extra
        )
        return search_results

    # ------------------------------------------------------------------
    # Etape 4 : Scraping
    # ------------------------------------------------------------------

    @with_retries(max_attempts=2, base_delay=3.0)
    def _call_scrape_all(self, search_results: Dict[str, Any]):
        return self.crawler.scrape_all(search_results)

    @timed_step("scraping")
    def _step_scrape(self, search_results: Dict[str, Any]) -> ScrapingStats:
        log_step(4, "SCRAPING")
        extra = _log_extra()

        if not search_results:
            raise ValueError("Aucun resultat de recherche a scraper.")

        self.crawler.output_dir = str(self.project_dir / "scraped" / "raw_markdown")
        scraping_stats = self._call_scrape_all(search_results)

        stats_path = self.project_dir / "scraped" / "scraping_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(scraping_stats.to_dict(), f, ensure_ascii=False, indent=4)

        failure_rate = (
            scraping_stats.failed / scraping_stats.total if scraping_stats.total else 0
        )
        log_fn = logger.warning if failure_rate > 0.3 else logger.info
        log_fn(
            "Scraping: %d succes, %d echecs sur %d (echec=%.0f%%)",
            scraping_stats.success, scraping_stats.failed, scraping_stats.total,
            failure_rate * 100, extra=extra,
        )
        return scraping_stats

    # ------------------------------------------------------------------
    # Etape 5 : Nettoyage
    # ------------------------------------------------------------------

    @timed_step("nettoyage")
    def _step_clean(self, scraping_stats: ScrapingStats) -> List[CleaningResult]:
        log_step(5, "NETTOYAGE")
        extra = _log_extra()

        cleaning_results = self.cleaner.process_all(scraping_stats)

        cleaned_path = self.project_dir / "cleaned" / "cleaning_results.json"
        with open(cleaned_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in cleaning_results], f, ensure_ascii=False, indent=4)

        success = sum(1 for r in cleaning_results if r.success)
        logger.info(
            "Nettoyage: %d/%d fichiers ok -> %s",
            success, len(cleaning_results), cleaned_path, extra=extra,
        )
        return cleaning_results

    # ------------------------------------------------------------------
    # Etape 6 : Chunking
    # ------------------------------------------------------------------

    @timed_step("chunking")
    def _step_chunk(self, cleaning_results: List[CleaningResult]) -> Dict[str, Any]:
        log_step(6, "CHUNKING")
        extra = _log_extra()

        chunk_result = self.chunker.process_documents(
            cleaning_results=cleaning_results,
            project_dir=str(self.project_dir / "chunks"),
            save_output=True,
            generate_report=True,
        )

        if chunk_result.get("chunks_file"):
            src = Path(chunk_result["chunks_file"])
            dst = self.project_dir / "chunks" / "chunks_consolidated.json"
            if src.exists():
                shutil.copy2(src, dst)

        logger.info(
            "Chunking: %d chunks (quality=%s)",
            chunk_result["total_chunks"],
            chunk_result.get("validation", {}).get("quality_score", "n/a"),
            extra=extra,
        )
        return chunk_result

    # ------------------------------------------------------------------
    # Etape 7 : Embedding + Indexation ChromaDB
    # ------------------------------------------------------------------

    @timed_step("embedding_indexation")
    def _step_index(self, chunk_result: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
        log_step(7, "EMBEDDING & INDEXATION")
        extra = _log_extra(collection=collection_name)

        chunks = chunk_result.get("all_chunks", [])
        if not chunks:
            logger.warning("Aucun chunk a indexer.", extra=extra)
            return {"indexed": 0, "collection_name": collection_name}

        chroma_chunks = [
            {
                "id": c.metadata.chunk_id,
                "text": c.content,
                "metadata": {
                    "source_url": c.metadata.source_url,
                    "doc_title": c.metadata.doc_title,
                    "section": c.metadata.section,
                    "question": c.metadata.question,
                    "angle": c.metadata.angle,
                    "heading_path": " > ".join(c.metadata.heading_path),
                    "chunk_type": (
                        c.metadata.chunk_type.value
                        if hasattr(c.metadata.chunk_type, "value")
                        else str(c.metadata.chunk_type)
                    ),
                    "token_count": c.metadata.token_count,
                    "character_count": c.metadata.character_count,
                    "has_code": c.metadata.has_code,
                    "has_tables": c.metadata.has_tables,
                    "has_lists": c.metadata.has_lists,
                    "has_numbers": c.metadata.has_numbers,
                    "has_dates": c.metadata.has_dates,
                    "extraction_date": c.metadata.extraction_date,
                },
            }
            for c in chunks
        ]

        self.chroma.create_collection(collection_name)
        total_added = self.chroma.add_chunks_to_collection(
            collection_name=collection_name, chunks=chroma_chunks, batch_size=50
        )

        stats = self.chroma.get_collection_stats(collection_name)
        stats.update(total_added=total_added, collection_name=collection_name)

        index_path = self.project_dir / "index" / "indexing_results.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)

        log_fn = logger.warning if total_added < len(chroma_chunks) else logger.info
        log_fn(
            "Indexation: %d/%d chunks -> '%s'",
            total_added, len(chroma_chunks), collection_name, extra=extra,
        )
        return stats

    # ------------------------------------------------------------------
    # Etape 8 : Analyse experte (agents parallélisés)
    # ------------------------------------------------------------------

    def _run_single_agent(
        self,
        section_id: str,
        agent_cls,
        project_info_dict: Dict[str, Any],
        collection_name: str,
        llm_client,
        retrieval_method: str,
        retrieval_kwargs: Dict[str, Any],
        queries: Dict[str, AnalysisOutput],
        agents_dir: Path,
    ) -> Tuple[str, Dict[str, Any], Optional[Any]]:
        """
        Exécute un agent de section. Conçu pour tourner dans un thread
        séparé (voir _step_expert_analysis) : chaque appel crée sa propre
        instance d'agent, aucun état partagé n'est muté ici.
        """
        extra = _log_extra(collection=collection_name, section_id=section_id)
        start = time.perf_counter()
        logger.info("--- Agent [%s] : %s ---", section_id, agent_cls.SECTION_LABEL, extra=extra)

        try:
            sec_queries = queries.get(section_id)
            if not sec_queries:
                logger.warning(
                    "Aucune requete disponible pour la section [%s], agent saute.",
                    section_id, extra=extra,
                )
                return section_id, {
                    "section_name": getattr(agent_cls, "SECTION_NAME", section_id),
                    "status": "skipped",
                    "reason": "no_queries",
                    "synthesis": "",
                    "question_count": 0,
                }, None

            questions = analysis_outputs_to_question_inputs(
                outputs=sec_queries, project=project_info_dict
            )

            agent = agent_cls(
                chroma_manager=self.chroma,
                collection_name=collection_name,
                llm_client=llm_client,
                project_info=project_info_dict,
                retrieval_strategy=retrieval_method,
                retrieval_kwargs=retrieval_kwargs,
                logger=logger,
            )
            analysis = agent.analyze(questions)

            md_path = agents_dir / f"{section_id}_analysis.md"
            ragas_path = agents_dir / f"{section_id}_ragas_dataset.json"
            analysis.save(str(md_path), also_json=True, logger=logger)
            save_ragas_dataset(build_ragas_dataset(analysis), ragas_path)

            score = (
                analysis.evaluation.get("composite_score", "N/A")
                if analysis.evaluation else "N/A"
            )
            logger.info(
                "Agent [%s] termine en %.1fs (score=%s)",
                section_id, time.perf_counter() - start, score, extra=extra,
            )

            summary = {
                "section_name": analysis.section_name,
                "synthesis": analysis.synthesis,
                "question_count": len(analysis.question_analyses),
                "evaluation": analysis.evaluation,
                "retrieval_method": analysis.retrieval_method,
                "output_path": str(md_path),
            }
            return section_id, summary, analysis

        except Exception:
            logger.exception(
                "Agent [%s] a echoue apres %.1fs",
                section_id, time.perf_counter() - start, extra=extra,
            )
            return section_id, {
                "section_name": getattr(agent_cls, "SECTION_NAME", section_id),
                "status": "failed",
                "error": "voir logs pour la stack trace complete",
            }, None

    @timed_step("analyse_experte")
    def _step_expert_analysis(
        self,
        project_info_dict: Dict[str, Any],
        collection_name: str,
        queries: Dict[str, AnalysisOutput],
        retrieval_method: str,
        chunks_per_query: int,
        max_workers: int,
    ) -> Dict[str, Any]:
        log_step(8, "ANALYSE EXPERTE (AGENTS)")
        extra = _log_extra(collection=collection_name)

        if not AGENTS_AVAILABLE or SECTION_AGENTS is None:
            logger.warning("Agents experts indisponibles, etape sautee.", extra=extra)
            return {"status": "skipped", "reason": "dependencies_missing", "sections": {}}

        llm_client = self.llm_client  # levée si indisponible -> capturée par _run_step_safely

        retrieval_kwargs = {
            "top_k": chunks_per_query,
            "n_candidates_per_query": chunks_per_query,
            "n_candidates": 50,
            "embedding_weight": 0.5,
            "lexical_weight": 0.5,
            "hybrid_weight_final": 0.3,
            "rerank_weight_final": 0.7,
            "use_reranking": True,
            "min_score_threshold": 0.0,
            "merge_strategy": "max",
            "multi_query_bonus": 0.05,
            "hyde_temperature": 0.4,
        }

        agents_dir = self.project_dir / "agents"
        agents_dir.mkdir(exist_ok=True)

        section_analyses: Dict[str, Any] = {}
        analyses_list = []

        # Les 4 agents (Macro/Demand/Competition/SWOT) sont indépendants :
        # exécution en parallèle pour réduire la durée de cette étape,
        # potentiellement la plus longue du pipeline (appels LLM répétés).
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._run_single_agent,
                    section_id, agent_cls, project_info_dict, collection_name,
                    llm_client, retrieval_method, retrieval_kwargs, queries, agents_dir,
                ): section_id
                for section_id, agent_cls in SECTION_AGENTS.items()
            }
            for future in as_completed(futures):
                section_id, summary, analysis_obj = future.result()
                section_analyses[section_id] = summary
                if analysis_obj is not None:
                    analyses_list.append(analysis_obj)

        summary_path = agents_dir / "agents_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(section_analyses, f, ensure_ascii=False, indent=4)

        n_failed = sum(1 for s in section_analyses.values() if s.get("status") == "failed")
        log_fn = logger.warning if n_failed else logger.info
        log_fn(
            "Analyses expertes: %d/%d agent(s) en echec -> %s",
            n_failed, len(SECTION_AGENTS), summary_path, extra=extra,
        )
        return {
            "status": "ok",
            "sections": section_analyses,
            "summary_path": str(summary_path),
            "analyses_list": analyses_list,
        }

    # ------------------------------------------------------------------
    # Etape 9 : Synthèse du rapport
    # ------------------------------------------------------------------

    @timed_step("synthese_rapport")
    def _step_report_synthesis(
        self, agents_result: Dict[str, Any], project_info_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        log_step(9, "SYNTHESE DU RAPPORT")
        extra = _log_extra()

        if not AGENTS_AVAILABLE or ReportSynthesisAgent is None:
            logger.warning("ReportSynthesisAgent indisponible, etape sautee.", extra=extra)
            return {"status": "skipped", "reason": "dependencies_missing"}

        section_objects = agents_result.get("analyses_list")
        if not section_objects:
            logger.warning("Aucune section valide pour la synthese.", extra=extra)
            return {"status": "skipped", "reason": "no_valid_sections"}

        synthesizer = ReportSynthesisAgent(llm_client=self.llm_client, logger=logger)

        report_path = self.project_dir / "report" / "market_report.md"
        report = synthesizer.synthesize(
            section_objects, output_path=str(report_path), also_markdown=True
        )

        json_path = self.project_dir / "report" / "market_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=4)

        logger.info(
            "Rapport: %d section(s) -> %s", len(report.sections), report_path, extra=extra
        )
        return {
            "status": "ok",
            "report_path": str(report_path),
            "json_path": str(json_path),
            "sections_count": len(report.sections),
            "retrieval_method": report.retrieval_method,
        }

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def run(self, config: PipelineRunConfig) -> Dict[str, Any]:
        """Exécute le pipeline complet d'analyse de marché à partir d'une config."""
        run_id = _new_run_id(config.project_name)
        token = _run_id_var.set(run_id)
        extra = _log_extra()
        start_time = datetime.now()

        self.project_dir = (
            self._resume_project_dir(config.project_name)
            if config.resume
            else self._create_project_dir(config.project_name)
        )

        logger.info("=" * 80, extra=extra)
        logger.info("DEMARRAGE DU PIPELINE (run_id=%s, resume=%s)", run_id, config.resume, extra=extra)
        logger.info("=" * 80, extra=extra)

        results: Dict[str, Any] = {
            "run_id": run_id,
            "project_dir": str(self.project_dir),
            "start_time": start_time.isoformat(),
            "steps": {},
        }

        try:
            # ---------------- Etape 1 : Analyse du projet ----------------
            analysis_path = self.project_dir / "analysis" / "project_analysis.json"
            if config.project_info is not None:
                project_info_dict = dict(config.project_info)
                results["steps"]["analysis"] = {"status": "ok", "source": "provided"}
            elif config.resume and (cached := self._load_json_if_exists(analysis_path)):
                project_info_dict = cached
                results["steps"]["analysis"] = {"status": "ok", "source": "resumed"}
                logger.info("Etape 'analyse_projet' reprise depuis le cache.", extra=extra)
            else:
                step1 = self._run_step_safely(
                    "analyse_projet",
                    lambda: self._step_analyze_project(config.project_description),
                    fallback=self._fallback_project_info(config.project_description),
                )
                project_info_dict = step1.data
                results["steps"]["analysis"] = step1.to_summary()

            results["project_info"] = project_info_dict

            # ---------------- Etape 2 : Génération de requêtes ----------------
            queries_path = self.project_dir / "queries" / "all_queries.json"
            if config.resume and (cached := self._load_json_if_exists(queries_path)):
                queries = cached
                results["steps"]["queries"] = {"status": "ok", "source": "resumed"}
            else:
                step2 = self._run_step_safely(
                    "generation_requetes",
                    lambda: self._step_generate_queries(project_info_dict, config.num_queries),
                    fallback={},
                )
                queries = step2.data
                results["steps"]["queries"] = step2.to_summary()

            # ---------------- Etape 3 : Recherche web ----------------
            search_path = self.project_dir / "search" / "search_results.json"
            if config.resume and (cached := self._load_json_if_exists(search_path)):
                search_results = cached
                results["steps"]["search"] = {"status": "ok", "source": "resumed"}
            else:
                step3 = self._run_step_safely(
                    "recherche_web",
                    lambda: self._step_web_search(queries, config.search_max_results),
                    fallback={},
                )
                search_results = step3.data
                results["steps"]["search"] = step3.to_summary()

            # ---------------- Etape 4 : Scraping ----------------
            if search_results:
                step4 = self._run_step_safely(
                    "scraping",
                    lambda: self._step_scrape(search_results),
                    fallback=ScrapingStats(total=0, success=0, failed=0),
                )
                scraping_stats = step4.data
                results["steps"]["scraping"] = {
                    **step4.to_summary(),
                    "success": scraping_stats.success,
                    "failed": scraping_stats.failed,
                    "total": scraping_stats.total,
                }
            else:
                scraping_stats = ScrapingStats(total=0, success=0, failed=0)
                results["steps"]["scraping"] = {"status": "skipped", "reason": "no_search_results"}

            # ---------------- Etape 5 : Nettoyage ----------------
            step5 = self._run_step_safely(
                "nettoyage", lambda: self._step_clean(scraping_stats), fallback=[]
            )
            cleaning_results = step5.data or []
            results["steps"]["cleaning"] = {
                **step5.to_summary(),
                "success": sum(1 for r in cleaning_results if r.success),
                "total": len(cleaning_results),
            }

            # ---------------- Etape 6 : Chunking ----------------
            step6 = self._run_step_safely(
                "chunking", lambda: self._step_chunk(cleaning_results),
                fallback={"total_chunks": 0, "all_chunks": [], "validation": {}},
            )
            chunk_result = step6.data
            results["steps"]["chunking"] = {
                **step6.to_summary(),
                "total_chunks": chunk_result.get("total_chunks", 0),
                "quality_score": chunk_result.get("validation", {}).get("quality_score"),
            }

            # ---------------- Etape 7 : Embedding + Indexation ----------------
            collection_name = self._generate_collection_name(project_info_dict)
            results["collection_name"] = collection_name

            if config.skip_embedding:
                results["steps"]["indexing"] = {"status": "skipped", "reason": "skip_embedding=True"}
            else:
                step7 = self._run_step_safely(
                    "embedding_indexation",
                    lambda: self._step_index(chunk_result, collection_name),
                    fallback={"total_added": 0},
                )
                results["steps"]["indexing"] = {
                    **step7.to_summary(),
                    "collection_name": collection_name,
                    "indexed_chunks": (step7.data or {}).get("total_added", 0),
                }

            # ---------------- Etape 8 : Analyse experte ----------------
            if config.skip_agents:
                results["steps"]["agents"] = {"status": "skipped", "reason": "skip_agents=True"}
                agents_result: Dict[str, Any] = {}
            else:
                step8 = self._run_step_safely(
                    "analyse_experte",
                    lambda: self._step_expert_analysis(
                        project_info_dict=project_info_dict,
                        collection_name=collection_name,
                        queries=queries,
                        retrieval_method=config.retrieval_method,
                        chunks_per_query=config.chunks_per_query,
                        max_workers=config.max_parallel_agents,
                    ),
                    fallback={"sections": {}, "analyses_list": []},
                )
                agents_result = step8.data or {}
                results["steps"]["agents"] = {
                    **step8.to_summary(),
                    "sections": agents_result.get("sections", {}),
                }

            # ---------------- Etape 9 : Synthèse du rapport ----------------
            if config.skip_agents or not agents_result.get("analyses_list"):
                results["steps"]["synthesis"] = {
                    "status": "skipped",
                    "reason": "skip_agents=True" if config.skip_agents else "no_sections_available",
                }
            else:
                step9 = self._run_step_safely(
                    "synthese_rapport",
                    lambda: self._step_report_synthesis(agents_result, project_info_dict),
                    fallback={},
                )
                results["steps"]["synthesis"] = step9.to_summary()
                if step9.data and step9.data.get("report_path"):
                    results["report_path"] = step9.data["report_path"]

            results["status"] = "ok"

        except Exception:
            logger.exception("Pipeline echoue de facon critique (run_id=%s)", run_id, extra=extra)
            results["error"] = "voir logs pour la stack trace complete"
            results["status"] = "failed"
        finally:
            _run_id_var.reset(token)

        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()

        summary_path = self.project_dir / "pipeline_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4, default=str)

        logger.info("=" * 80, extra=extra)
        logger.info(
            "PIPELINE %s (run_id=%s, duree=%.1fs)",
            "TERMINE" if results["status"] == "ok" else "TERMINE AVEC ERREURS",
            run_id, results["duration_seconds"], extra=extra,
        )
        logger.info("=" * 80, extra=extra)
        logger.info("Dossier projet : %s", self.project_dir, extra=extra)
        logger.info("Collection     : %s", results.get("collection_name", "N/A"), extra=extra)
        logger.info("Resume         : %s", summary_path, extra=extra)

        return results


# ============================================================================
# Point d'entrée
# ============================================================================

if __name__ == "__main__":
    description = (
        "Je souhaite lancer une plateforme SaaS destinée aux restaurants "
        "indépendants en France permettant de gérer les commandes, les "
        "réservations, les stocks et l'analyse des ventes grâce à "
        "l'intelligence artificielle."
    )

    run_config = PipelineRunConfig(
        project_name="my_first_project",
        project_description=description,
    )

    pipeline = Pipeline()
    result = pipeline.run(run_config)

    print()
    print("=" * 80)
    print("RESUME DU PIPELINE")
    print("=" * 80)
    print(f"Statut        : {result.get('status', 'unknown')}")
    print(f"Dossier projet: {result.get('project_dir')}")
    print(f"Collection    : {result.get('collection_name', 'N/A')}")
    print(f"Durée         : {result.get('duration_seconds', 0):.1f}s")
    print()
    for step, info in result.get("steps", {}).items():
        print(f"  {step:15} -> {info.get('status', '?')}")