 
"""
Agent de base pour l'analyse de section avec récupération configurable.

Contient tout le pipeline générique (raffinement HyDE, récupération,
génération de réponse, synthèse) ; les sous-classes concrètes n'ont
qu'à définir leurs métadonnées et leur prompt de synthèse
(voir agents.py).
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, Tuple

from clients import OpenRouterLLMClient
from embedding.chroma_manager import ChromaManager

from retreiver.hybrid_retriever import HybridResultReporter, HybridRetriever, MergedHybridResult
from retreiver.simple_retriever import Retriever, RetrievalResult, VectorRetrievalConfig
from retreiver.methode_retrieval import RetrievalMethods, NormalizedResult

from .models import QuestionInput, QuestionAnalysis, SectionAnalysis, SubQueryHyde
from .Retrieval_strategy import RetrievalStrategy
from utils.logger import get_logger
logger = get_logger(__name__)

class BaseSectionAgent(ABC):
    """
    Classe de base pour les agents d'analyse de section.

    Les sous-classes DOIVENT définir :
        - SECTION_NAME  : identifiant court
        - SECTION_LABEL : libellé lisible
        - _build_synthesis_prompt(question_analyses) -> (system, user)

    Les sous-classes PEUVENT surcharger :
        - DEFAULT_QUESTIONS
        - _build_hyde_refinement_prompt
        - _build_question_prompt
    """

    SECTION_NAME: str = "base"
    SECTION_LABEL: str = "Section"
    DEFAULT_QUESTIONS: List[str] = []
    N_QUESTIONS: int = 3

    def __init__(
        self,
        chroma_manager: ChromaManager,
        collection_name: str,
        llm_client: OpenRouterLLMClient,
        project_info: Dict[str, Any],
        retrieval_strategy: Literal["hybrid", "vector", "M1", "M2", "M3a", "M3b", "M4a", "M4b", "M4c"] = "hybrid",
        retrieval_kwargs: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = logger,
        max_llm_retries: int = 2,
    ):
        """
        Args:
            chroma_manager: instance de ChromaManager.
            collection_name: nom de la collection pour la récupération.
            llm_client: client LLM pour la génération.
            project_info: informations de contexte projet.
            retrieval_strategy: méthode de récupération (M1-M4c) ou alias legacy.
            retrieval_kwargs: paramètres de récupération additionnels.
            logger: instance de logger.
            max_llm_retries: nombre max de tentatives pour les appels LLM.
        """
        self.chroma_manager = chroma_manager
        self.collection_name = collection_name
        self.llm_client = llm_client
        self.project_info = project_info or {}
        self.retrieval_strategy = retrieval_strategy
        self.max_llm_retries = max_llm_retries
        self.logger = logger

        self._init_retrievers()
        self.retrieval_config = RetrievalStrategy(retrieval_strategy, **(retrieval_kwargs or {}))

        self.reporter = HybridResultReporter()
        
        self.logger.info(
            f"Agent '{self.SECTION_NAME}' initialisé avec la méthode "
            f"de récupération {self.retrieval_config.strategy}"
        )


    def _init_retrievers(self) -> None:
        """Initialise les retriever et la méthode de récupération dynamique."""
        self.hybrid_retriever = HybridRetriever(self.chroma_manager, logger=self.logger)

        config = VectorRetrievalConfig()
        self.vector_retriever = Retriever(self.chroma_manager, config, self.logger)

        from retreiver.methode_retrieval import HyDEGenerator
        hyde_generator = HyDEGenerator(self.llm_client, self.logger) if self.llm_client else None

        self.retrieval_methods = RetrievalMethods(
            chroma_manager=self.chroma_manager,
            hybrid_retriever=self.hybrid_retriever,
            vector_retriever=self.vector_retriever,
            hyde_generator=hyde_generator,
            collection_name=self.collection_name,
            logger=self.logger,
        )



    # ========================================================================
    # Pipeline principal
    # ========================================================================

    def analyze(self, questions: List[QuestionInput]) -> SectionAnalysis:
        """Exécute le pipeline complet d'analyse sur une liste de questions."""
        if len(questions) != self.N_QUESTIONS:
            self.logger.warning(
                f"[{self.SECTION_NAME}] {len(questions)} question(s) fournie(s), "
                f"{self.N_QUESTIONS} attendue(s) — poursuite malgré tout."
            )

        question_analyses = []
        for i, q in enumerate(questions, 1):
            self.logger.info(
                f"[{self.SECTION_NAME}] Question {i}/{len(questions)}: '{q.question[:80]}...'"
            )
            question_analyses.append(self._process_question(q))

        self.logger.info(
            f"[{self.SECTION_NAME}] Synthèse de la section à partir de "
            f"{len(question_analyses)} question(s)..."
        )
        synthesis = self._synthesize_section(question_analyses)

        self.logger.info(f"✅ [{self.SECTION_NAME}] Analyse de section terminée")

        analysis = SectionAnalysis(
            section_name=self.SECTION_NAME,
            project_info=self.project_info,
            question_analyses=question_analyses,
            synthesis=synthesis,
            retrieval_strategy=self.retrieval_strategy,
            retrieval_method=self.retrieval_config.strategy,
        )

        # Évaluation de la section
        analysis.evaluation = self._evaluate_section(analysis)

        return analysis

    # ========================================================================
    # Traitement d'une question
    # ========================================================================

    def _process_question(self, q: QuestionInput) -> QuestionAnalysis:
        """Traite une question unique de bout en bout."""
        refined_queries = self._refine_hyde_queries(q)
        chunks = self._retrieve_chunks(q.question, refined_queries)
        answer = self._answer_question(q.question, chunks)

        return QuestionAnalysis(
            question=q.question,
            refined_queries=refined_queries,
            chunks=chunks,
            answer=answer,
            retrieval_strategy=self.retrieval_strategy,
            retrieval_method=self.retrieval_config.strategy,
        )

    def _refine_hyde_queries(self, q: QuestionInput) -> List[str]:
        """Raffine les requêtes HyDE via le LLM."""
        refined = []
        for sq in q.sub_queries:
            system, user = self._build_hyde_refinement_prompt(q.question, sq)
            refined_text = self._call_llm(system, user, temperature=0.4, max_tokens=400)
            refined.append(refined_text if refined_text else sq.hyde_answer)

        if not refined:
            self.logger.warning(
                f"[{self.SECTION_NAME}] Pas de sous-requête pour "
                f"'{q.question[:60]}...' — utilisation de la question brute."
            )
        return refined

    # ========================================================================
    # Récupération (retrieval) dynamique par méthode M1-M4c
    # ========================================================================

    def _retrieve_chunks(self, question: str, refined_queries: List[str]) -> List[Any]:
        """
        Récupère les chunks selon la méthode configurée (M1-M4c).

        Returns:
            Liste de NormalizedResult.
        """
        sub_queries = refined_queries if refined_queries else [question]
        method = self.retrieval_config.strategy
        config = self.retrieval_config.get_params()

        self.logger.info(
            f"[{self.SECTION_NAME}] Récupération dynamique méthode {method} "
            f"pour '{question[:60]}...'"
        )

        try:
            results = self._dispatch_retrieval(method, question, sub_queries, config)
        except Exception as e:
            self.logger.error(
                f"[{self.SECTION_NAME}] Échec de la méthode {method}: {e}. "
                f"Repli sur M1 (vectoriel)."
            )
            results = self.retrieval_methods.m1_pure_vectorial(
                query=question,
                n_results=config.get("n_results", 30),
                top_k=config.get("top_k", 20),
            )

        if not results:
            self.logger.warning(
                f"[{self.SECTION_NAME}] Aucun chunk récupéré pour '{question[:60]}...'"
            )
        return results

    def _dispatch_retrieval(
        self,
        method: str,
        question: str,
        sub_queries: List[str],
        config: Dict[str, Any],
    ) -> List[NormalizedResult]:
        """Dispatch vers la méthode de récupération appropriée."""
        if method == RetrievalStrategy.M1:
            return self.retrieval_methods.m1_pure_vectorial(
                query=question,
                n_results=config.get("n_results", 30),
                top_k=config.get("top_k", 20),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
            )

        if method == RetrievalStrategy.M2:
            return self.retrieval_methods.m2_hybrid_search(
                query=question,
                top_k=config.get("top_k", 20),
                n_candidates=config.get("n_candidates", 50),
                embedding_weight=config.get("embedding_weight", 0.5),
                lexical_weight=config.get("lexical_weight", 0.5),
                hybrid_weight_final=config.get("hybrid_weight_final", 0.3),
                rerank_weight_final=config.get("rerank_weight_final", 0.7),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
            )

        if method == RetrievalStrategy.M3A:
            return self.retrieval_methods.m3a_vector_hyde(
                query=question,
                n_results=config.get("n_results", 30),
                top_k=config.get("top_k", 20),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
                hyde_temperature=config.get("hyde_temperature", 0.4),
            )

        if method == RetrievalStrategy.M3B:
            return self.retrieval_methods.m3b_vector_multi_query_fusion(
                query=question,
                sub_queries=sub_queries,
                n_results=config.get("n_results", 30),
                top_k=config.get("top_k", 20),
                final_top_k=config.get("final_top_k", 20),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
            )

        if method == RetrievalStrategy.M4A:
            return self.retrieval_methods.m4a_hybrid_multi_query_fusion(
                query=question,
                sub_queries=sub_queries,
                top_k=config.get("top_k", 20),
                n_candidates_per_query=config.get("n_candidates_per_query", 30),
                n_candidates=config.get("n_candidates", 50),
                embedding_weight=config.get("embedding_weight", 0.5),
                lexical_weight=config.get("lexical_weight", 0.5),
                hybrid_weight_final=config.get("hybrid_weight_final", 0.3),
                rerank_weight_final=config.get("rerank_weight_final", 0.7),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
                merge_strategy=config.get("merge_strategy", "max"),
                multi_query_bonus=config.get("multi_query_bonus", 0.05),
            )

        if method == RetrievalStrategy.M4B:
            return self.retrieval_methods.m4b_hybrid_hyde(
                query=question,
                top_k=config.get("top_k", 20),
                n_candidates=config.get("n_candidates", 50),
                embedding_weight=config.get("embedding_weight", 0.5),
                lexical_weight=config.get("lexical_weight", 0.5),
                hybrid_weight_final=config.get("hybrid_weight_final", 0.3),
                rerank_weight_final=config.get("rerank_weight_final", 0.7),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
                hyde_temperature=config.get("hyde_temperature", 0.4),
            )

        if method == RetrievalStrategy.M4C:
            return self.retrieval_methods.m4c_hybrid_multi_query(
                query=question,
                sub_queries=sub_queries,
                top_k=config.get("top_k", 20),
                n_candidates_per_query=config.get("n_candidates_per_query", 30),
                n_candidates=config.get("n_candidates", 50),
                embedding_weight=config.get("embedding_weight", 0.5),
                lexical_weight=config.get("lexical_weight", 0.5),
                hybrid_weight_final=config.get("hybrid_weight_final", 0.3),
                rerank_weight_final=config.get("rerank_weight_final", 0.7),
                use_reranking=config.get("use_reranking", True),
                min_score_threshold=config.get("min_score_threshold", 0.0),
                merge_strategy=config.get("merge_strategy", "max"),
                multi_query_bonus=config.get("multi_query_bonus", 0.05),
                hyde_temperature=config.get("hyde_temperature", 0.4),
            )

        raise ValueError(f"Méthode de récupération non supportée: {method}")

    # ========================================================================
    # Évaluation de la récupération (RAGAS-compatible)
    # ========================================================================

    def _evaluate_section(self, analysis: SectionAnalysis) -> Dict[str, Any]:
        """Évalue la qualité de la récupération pour l'ensemble de la section."""
        try:
            from retreiver.retrieval_evaluator import RetrievalEvaluator
            evaluator = RetrievalEvaluator(
                llm_client=self.llm_client,
                chroma_manager=self.chroma_manager,
                logger=self.logger,
            )

            all_results: List[Any] = []
            for qa in analysis.question_analyses:
                all_results.extend(qa.chunks)

            if not all_results:
                return {
                    "composite_score": 0.0,
                    "relevance_score": 0.0,
                    "coverage_score": 0.0,
                    "diversity_score": 0.0,
                    "reason": "no chunks retrieved",
                }

            # Évaluer sur la question globale de la section
            global_query = analysis.question_analyses[0].question if analysis.question_analyses else ""
            result = evaluator.evaluate(global_query, all_results[:20])
            return result.to_dict()
        except Exception as e:
            self.logger.warning(
                f"[{self.SECTION_NAME}] Évaluation échouée: {e}"
            )
            return {
                "composite_score": 0.0,
                "relevance_score": 0.0,
                "coverage_score": 0.0,
                "diversity_score": 0.0,
                "error": str(e),
            }

    # ========================================================================
    # Génération (LLM)
    # ========================================================================

    def _answer_question(self, question: str, chunks: List[Any]) -> str:
        """Génère la réponse à une question à partir des chunks récupérés."""
        context = self._format_chunks_for_context(chunks)
        system, user = self._build_question_prompt(question, context)
        answer = self._call_llm(system, user, temperature=0.3, max_tokens=900)

        if not answer:
            answer = (
                "⚠️ Réponse non générée (échec de l'appel LLM). "
                f"{len(chunks)} extrait(s) brut(s) disponible(s) pour analyse manuelle."
            )
        return answer

    def _synthesize_section(self, question_analyses: List[QuestionAnalysis]) -> str:
        """Synthétise la section à partir des réponses aux questions."""
        system, user = self._build_synthesis_prompt(question_analyses)
        synthesis = self._call_llm(system, user, temperature=0.3, max_tokens=2200)

        if not synthesis:
            self.logger.error(
                f"[{self.SECTION_NAME}] Échec de la synthèse LLM — repli sur la "
                f"concaténation des réponses aux questions."
            )
            synthesis = "\n\n".join(
                f"**{qa.question}**\n\n{qa.answer}" for qa in question_analyses
            )
        return synthesis

    # ========================================================================
    # Construction des prompts
    # ========================================================================

    def _build_hyde_refinement_prompt(
        self, question: str, sub_query: SubQueryHyde
    ) -> Tuple[str, str]:
        """Construit le prompt de raffinement HyDE."""
        system = (
            "Tu es un expert en recherche documentaire pour des études de marché. "
            "Ta tâche : réécrire un paragraphe hypothétique (technique HyDE) pour "
            "qu'il ressemble le plus possible à un extrait RÉEL d'un rapport "
            "d'étude de marché professionnel sur ce sujet précis (vocabulaire "
            "sectoriel, chiffres plausibles, structure), afin de maximiser la "
            "pertinence d'une recherche par similarité dans une base de "
            "connaissance de rapports de marché. N'ajoute aucun commentaire, "
            "écris directement le paragraphe."
        )
        user = (
            f"## Question principale de la section ({self.SECTION_LABEL})\n"
            f"{question}\n\n"
            f"## Sous-requête\n{sub_query.sub_query}\n\n"
            f"## Réponse hypothétique initiale (recherche web)\n"
            f"{sub_query.hyde_answer}\n\n"
            f"## Contexte projet\n{self._format_project_info()}\n\n"
            f"## Consigne\nRéécris cette réponse hypothétique en un paragraphe "
            f"dense (4 à 6 phrases), au style d'un extrait de rapport d'étude "
            f"de marché professionnel, qui servira UNIQUEMENT de requête de "
            f"recherche. Ne dis pas 'je', ne mentionne pas qu'il s'agit d'une "
            f"hypothèse : écris directement le paragraphe."
        )
        return system, user

    def _build_question_prompt(self, question: str, context: str) -> Tuple[str, str]:
        """Construit le prompt de réponse à une question."""
        system = (
            f"Tu es un analyste expert en études de marché, spécialisé dans la "
            f"section '{self.SECTION_LABEL}'. Tu réponds UNIQUEMENT à partir du "
            f"contexte fourni (extraits de la base de connaissance) et des "
            f"informations projet. Si une information manque, dis-le "
            f"explicitement plutôt que d'inventer. Cite systématiquement les "
            f"chiffres clés (pourcentages, montants, dates, taux de croissance) "
            f"tels qu'ils apparaissent dans le contexte."
        )
        user = (
            f"## Informations projet\n{self._format_project_info()}\n\n"
            f"## Question à traiter\n{question}\n\n"
            f"## Contexte (extraits de la base de connaissance)\n{context}\n\n"
            f"## Consigne\nRéponds à la question de façon factuelle, structurée "
            f"et synthétique (6 à 10 phrases), en t'appuyant explicitement sur "
            f"les chiffres et faits présents dans le contexte."
        )
        return system, user

    @abstractmethod
    def _build_synthesis_prompt(
        self, question_analyses: List[QuestionAnalysis]
    ) -> Tuple[str, str]:
        """Construit le prompt de synthèse de section (à implémenter par sous-classe)."""
        raise NotImplementedError

    # ========================================================================
    # Utilitaires
    # ========================================================================

    def _format_project_info(self) -> str:
        """Formate les informations projet pour les prompts."""
        if not self.project_info:
            return "(Aucune information projet fournie.)"
        return "\n".join(f"- **{k}:** {v}" for k, v in self.project_info.items())

    def _format_chunks_for_context(
        self,
        chunks: List[Any],
        max_chunks: int = 20,
        max_chars_per_chunk: int = 1000,
    ) -> str:
        """Formate les chunks récupérés pour le contexte LLM."""
        if not chunks:
            return "(Aucun extrait pertinent trouvé dans la base de connaissance.)"

        blocks = []
        for i, c in enumerate(chunks[:max_chunks], 1):
            meta = getattr(c, "metadata", None) or {}
            source = meta.get("parent_doc") or meta.get("source_url") or "source inconnue"
            score = getattr(c, "score", None)
            score_info = f"score: {score:.2f}" if score is not None else "score: N/A"

            if hasattr(c, "query_count") and c.query_count:
                score_info += f" | retrouvé par {c.query_count} sous-requête(s)"

            blocks.append(
                f"[Extrait {i} | source: {source} | {score_info}]\n{getattr(c, 'text', '')[:max_chars_per_chunk]}"
            )
        return "\n\n".join(blocks)




    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """Appelle le LLM avec logique de retry."""
        last_error = None
        attempts = self.max_llm_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                result = self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if result and result.strip():
                    return result.strip()
                raise ValueError("Réponse LLM vide")
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"[{self.SECTION_NAME}] Échec de l'appel LLM "
                    f"(tentative {attempt}/{attempts}): {e}"
                )
                if attempt < attempts:
                    time.sleep(min(2 ** attempt, 8))

        self.logger.error(
            f"[{self.SECTION_NAME}] Échec de l'appel LLM après {attempts} tentatives: {last_error}"
        )
        return ""



