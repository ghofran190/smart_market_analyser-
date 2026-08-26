
"""
RAG Judge — évaluation du RETRIEVER autour de 4 métriques principales :

  1. relevance          : pertinence des chunks récupérés vis-à-vis de la question
  2. coverage           : les chunks couvrent-ils suffisamment tous les aspects
                           de la question ?
  3. context_precision  : parmi les chunks récupérés, combien sont vraiment
                           utiles (peu de "bruit") ?
  4. diversity           : les chunks sont-ils redondants ou complémentaires ?

Logique de calcul :
- diversity        -> 100% calculé (dissimilarité lexicale entre chunks), aucune
                       dépendance au LLM.
- relevance         -> hybride : score de similarité ChromaDB (objectif) mélangé
                       au jugement du LLM par chunk.
- context_precision -> jugée chunk par chunk par le LLM (utile / pas utile),
                       avec un fallback heuristique basé sur les scores ChromaDB
                       si le LLM échoue.
- coverage          -> le LLM décompose la question en sous-aspects et vérifie
                       lesquels sont couverts, avec un fallback basé sur la
                       couverture des mots-clés de la question si le LLM échoue.

Chaque métrique indique sa méthode de calcul ("llm", "hybrid" ou "heuristic")
dans le résultat, pour la transparence.
"""

import json
import re
import os
import sys
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

from clients import OpenRouterLLMClient
from config import OpenRouterConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


STOPWORDS_FR = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "à", "au",
    "aux", "pour", "par", "dans", "sur", "avec", "est", "sont", "que", "qui",
    "ce", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "quel", "quelle",
}


@dataclass
class ChromaResult:
    id: str
    score: float
    text: str
    source_url: str = ""


@dataclass
class QueryEvaluation:
    query: str
    total_results: int

    overall_score: float
    relevance_score: float
    coverage_score: float
    context_precision_score: float
    diversity_score: float

    scoring_methods: Dict[str, str]           # méthode utilisée par métrique (llm / hybrid / heuristic)
    chunk_details: List[Dict[str, Any]]        # détail par chunk (score, pertinence, utile ou non)
    query_aspects: List[Dict[str, Any]]        # sous-aspects de la question et leur couverture

    informations_principales_extraites: List[Dict[str, Any]]
    data_gaps: List[str]
    executive_summary: str

    model_used: str = ""
    error: Optional[str] = None


class RAGJudge:
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    WEIGHTS = {
        "relevance": 0.3,
        "context_precision": 0.25,
        "coverage": 0.3,
        "diversity": 0.15,
    }

    def __init__(self, api_key: str = "", model: str = "openai/gpt-4o-mini", max_chunks: int = 10, debug: bool = False, llm_client: Optional[Any] = None):
        self.debug = debug
        self.max_chunks = max_chunks
        self.OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

        if llm_client is not None:
            self.llm_client = llm_client
            self.model = getattr(llm_client, "model", model)
            api_key = ""
        else:
            self.llm_client = None
            self.model = model
            if not api_key:
                api_key = OpenRouterConfig.api_key
            if not api_key:
                raise ValueError(
                    "OpenRouter API key required. Set OPENROUTER_API_KEY or pass api_key explicitly."
                )

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    # =========================================================================
    # 1. PARSING DU RAPPORT MARKDOWN
    # =========================================================================

    def parse_markdown_report(self, markdown_content: str) -> Dict[str, Any]:
        query_match = re.search(r"\*\*Requête:\*\* (.+)", markdown_content)
        query = query_match.group(1).strip() if query_match else "N/A"

        results: List[ChromaResult] = []
        blocks = re.split(r"\n---\n", markdown_content)

        for block in blocks:
            if "### Résultat" not in block:
                continue

            id_m = re.search(r"\*\*ID:\*\* `([^`]+)`", block)
            score_m = re.search(r"\*\*Score:\*\* `([\d.]+)`", block)
            text_m = re.search(
                r"\*\*Texte:\*\*\n\n> (.+?)(?:\n\n\*\*Métadonnées:\*\*|\n\*\*Source:\*\*|$)",
                block,
                re.DOTALL,
            )
            if not (id_m and score_m and text_m):
                continue

            text = re.sub(r"\n> ", "\n", text_m.group(1)).strip()
            # source_m = re.search(r"\*\*Source:\*\* `([^`]+)`", block)

            results.append(
                ChromaResult(
                    id=id_m.group(1),
                    score=float(score_m.group(1)),
                    text=text,
                    # source_url=source_m.group(1) if source_m else "",
                )
            )
            if len(results) >= self.max_chunks:
                break

        return {"query": query, "results": results}

    # =========================================================================
    # 2. UTILITAIRES
    # =========================================================================

    def _tokenize(self, text: str) -> set:
        words = re.findall(r"[a-zàâäéèêëïîôöùûüç]{4,}", text.lower())
        return {w for w in words if w not in STOPWORDS_FR}

    # =========================================================================
    # 3. DIVERSITY — 100% calculé
    # =========================================================================

    def _score_diversity(self, results: List[ChromaResult]) -> float:
        """Dissimilarité lexicale moyenne entre chaque paire de chunks
        (1 - similarité de Jaccard). Chunks redondants -> score bas.
        Chunks complémentaires/distincts -> score haut.
        """
        if len(results) < 2:
            return 50.0  # non mesurable sur un seul chunk

        token_sets = [self._tokenize(r.text) for r in results]
        dissimilarities = []
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                a, b = token_sets[i], token_sets[j]
                if not a and not b:
                    continue
                union = a | b
                inter = a & b
                jaccard_sim = len(inter) / len(union) if union else 0
                dissimilarities.append(1 - jaccard_sim)

        if not dissimilarities:
            return 50.0
        return round((sum(dissimilarities) / len(dissimilarities)) * 100, 1)

    # =========================================================================
    # 4. FALLBACKS DÉTERMINISTES (utilisés si le LLM échoue)
    # =========================================================================

    def _fallback_relevance(self, results: List[ChromaResult]) -> float:
        """Moyenne des scores de similarité ChromaDB, normalisée sur 100."""
        if not results:
            return 0.0
        avg = sum(r.score for r in results) / len(results)
        return round(max(0.0, min(1.0, avg)) * 100, 1)

    def _fallback_context_precision(self, results: List[ChromaResult]) -> float:
        """Approxime la précision par la proportion de chunks dont le score
        ChromaDB est au-dessus de la moyenne du lot (proxy grossier de
        'chunk probablement utile')."""
        if not results:
            return 0.0
        scores = [r.score for r in results]
        avg_score = sum(scores) / len(scores)
        useful_count = sum(1 for s in scores if s >= avg_score)
        return round((useful_count / len(results)) * 100, 1)

    def _fallback_coverage(self, query: str, results: List[ChromaResult]) -> float:
        """Approxime la couverture par le pourcentage de mots-clés significatifs
        de la question retrouvés dans l'ensemble des chunks."""
        query_keywords = self._tokenize(query)
        if not query_keywords:
            return 50.0
        combined_text = " ".join(r.text for r in results)
        text_words = self._tokenize(combined_text)
        coverage = len(query_keywords & text_words) / len(query_keywords)
        return round(coverage * 100, 1)

    # =========================================================================
    # 5. APPEL LLM — relevance par chunk, utilité par chunk, couverture des aspects
    # =========================================================================

    def _build_prompt(self, query: str, results: List[ChromaResult]) -> str:
        results_text = "\n".join(
            f"R{i + 1} (similarité ChromaDB={r.score:.2f}): {r.text[:350].replace(chr(34), chr(39))}"
            for i, r in enumerate(results)
        )
        return f"""Tu évalues un système de retrieval RAG (retriever) pour une étude de marché.
Base-toi UNIQUEMENT sur le contenu ci-dessous, n'invente rien.

QUESTION: {query[:200]}

CHUNKS RÉCUPÉRÉS ({len(results)} au total):
{results_text}

Réponds UNIQUEMENT avec ce JSON (pas de texte hors JSON, pas de balises markdown):
{{
  "chunk_assessments": [
    {{"chunk": "R1", "relevance_score": 0-100, "useful_for_answering": true, "reason": "justification courte (max 12 mots)"}}
  ],
  "query_aspects": [
    {{"aspect": "sous-thème ou dimension de la question (ex: 'taille du marché', 'acteurs concurrents', 'tendances technologiques')", "covered": true, "supporting_chunks": ["R1", "R3"]}}
  ],
  "informations_principales_extraites": [
    {{"information": "libellé libre selon ce qui est réellement trouvé", "valeur": "...", "source": "R1/R2/..."}}
  ],
  "data_gaps": ["information manquante ou insuffisamment couverte"],
  "executive_summary": "3-4 phrases denses et factuelles, propres à CETTE recherche"
}}

Règles précises:
1. "chunk_assessments": évalue CHAQUE chunk (R1 à R{len(results)}), un par un:
   - "relevance_score": mesure la CONTRIBUTION du chunk à construire une réponse utile.
     Distingue trois niveaux:
     * 70-100: le chunk répond directement et factuellement à la question
     * 40-69:  le chunk apporte un contexte, une donnée adjacente ou un signal
               qui aide à cadrer ou enrichir la réponse (même indirectement)
     * 0-39:   le chunk est hors-sujet ou ne contient aucune information exploitable
   - "contribution_type":
     * "direct" → répond explicitement à la question
     * "contextuel" → éclaire le contexte, confirme une tendance, donne du fond
     * "faible" → peu ou pas pertinent
   - "useful_for_answering": true si le chunk apporte une valeur quelconque (même
     contextuelle) pour construire ou nuancer la réponse. false UNIQUEMENT si le chunk
     est complètement hors-sujet ou strictement redondant avec un autre chunk déjà noté true.

2. "query_aspects": identifie 3 à 6 sous-aspects/facettes distincts que la question implique.
   Pour chaque aspect, indique:
   - "covered": true si au moins un chunk contient une information liée, directement
     OU indirectement (donnée de contexte, tendance générale, exemple sectoriel...)
   - "coverage_level":
     * "explicite"  → chiffre, fait ou affirmation directe trouvé dans un chunk
     * "implicite"  → information déductible ou contextualisée à partir des chunks
     * "partiel"    → couverture fragmentaire, donnée incomplète ou approximative
   - "supporting_chunks": liste les chunks concernés, même pour une couverture partielle.

3. Calibrage des scores — évite les deux extrêmes:
   - Ne sanctionne PAS un chunk parce qu'il est indirect ou contextuel: le contexte
     est une information utile dans une étude de marché.
   - Ne sur-note PAS des chunks qui mentionnent le sujet sans apporter de substance.
   - Distingue clairement les chunks forts (70+) des chunks contextuels (40-69)
     des chunks faibles (0-39): la distribution doit refléter la réalité des chunks."""
    def _call_llm(self, prompt: str, retries: int = 2, timeout: int = 120) -> Optional[dict]:
        system_prompt = (
            "Tu es un évaluateur rigoureux de systèmes RAG. "
            "Réponds UNIQUEMENT en JSON valide, sans texte additionnel."
        )

        if self.llm_client is not None:
            last_error = None
            for attempt in range(retries + 1):
                try:
                    content = self.llm_client.generate(
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        temperature=0.2,
                        max_tokens=1400,
                    )
                    if content and content.strip():
                        return {"choices": [{"message": {"content": content.strip()}}]}
                    raise ValueError("Empty LLM response")
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Erreur LLM (tentative {attempt + 1}/{retries + 1}): {last_error}")
                    time.sleep(2 ** attempt)

            logger.error(
                f"Appel LLM définitivement échoué après {retries + 1} tentative(s). "
                f"Dernière erreur: {last_error}"
            )
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1400,
        }

        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    self.OPENROUTER_URL, headers=self.headers, json=payload, timeout=timeout
                )

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                    logger.error(
                        f"Erreur API (tentative {attempt + 1}/{retries + 1}): {last_error}"
                    )
                    time.sleep(2 ** attempt)
                    continue

                data = resp.json()

                if "error" in data:
                    last_error = f"Erreur applicative: {data['error']}"
                    logger.error(
                        f"Erreur renvoyée par l'API, statut 200 "
                        f"(tentative {attempt + 1}/{retries + 1}): {data['error']}"
                    )
                    time.sleep(2 ** attempt)
                    continue

                if self.debug:
                    logger.info(f"--- PROMPT ---\n{prompt}\n--- FIN PROMPT ---")
                    logger.info(
                        f"--- REPONSE BRUTE ---\n{json.dumps(data, ensure_ascii=False, indent=2)}\n--- FIN ---"
                    )

                return data

            except requests.exceptions.Timeout:
                last_error = f"Timeout après {timeout}s"
                logger.error(f"Timeout (tentative {attempt + 1}/{retries + 1}), nouvelle tentative...")
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.error(f"Erreur réseau (tentative {attempt + 1}/{retries + 1}): {last_error}")
                time.sleep(2 ** attempt)

        logger.error(
            f"Appel LLM définitivement échoué après {retries + 1} tentative(s). "
            f"Dernière erreur: {last_error}"
        )
        return None

    def _safe_parse(self, content: str) -> dict:
        content = content.strip()
        content = re.sub(r"^```json|^```|```$", "", content).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            return {}

    # =========================================================================
    # 6. ORCHESTRATION
    # =========================================================================

    def _empty_eval(self, query: str, total_results: int, error: str) -> QueryEvaluation:
        return QueryEvaluation(
            query=query,
            total_results=total_results,
            overall_score=0,
            relevance_score=0,
            coverage_score=0,
            context_precision_score=0,
            diversity_score=0,
            scoring_methods={},
            chunk_details=[],
            query_aspects=[],
            informations_principales_extraites=[],
            data_gaps=[error],
            executive_summary="",
            model_used=self.model,
            error=error,
        )

    def evaluate(self, markdown_content: str) -> QueryEvaluation:
        parsed = self.parse_markdown_report(markdown_content)
        query, results = parsed["query"], parsed["results"]

        if self.debug:
            logger.info(f"Requête détectée: {query}")
            logger.info(f"Chunks extraits du markdown: {len(results)}")

        if not results:
            return self._empty_eval(query, 0, "Aucun résultat trouvé dans le rapport")

        # --- Diversity : toujours calculée, jamais dépendante du LLM ---
        diversity = self._score_diversity(results)

        # --- Fallbacks déterministes, calculés dans tous les cas ---
        relevance_fallback = self._fallback_relevance(results)
        precision_fallback = self._fallback_context_precision(results)
        coverage_fallback = self._fallback_coverage(query, results)

        # --- Appel LLM ---
        prompt = self._build_prompt(query, results)
        response = self._call_llm(prompt)

        chunk_assessments, query_aspects = [], []
        informations, data_gaps, executive_summary = [], [], ""
        error = None

        if response is None or "choices" not in response:
            error = "Échec de l'appel API — scores calculés via fallback heuristique uniquement"
            logger.error(error)
        else:
            content = response["choices"][0]["message"]["content"]
            data = self._safe_parse(content)
            if not data:
                logger.error(f"Contenu brut non parsable:\n{content}")
                error = "Réponse LLM non parsable — scores calculés via fallback heuristique uniquement"
            else:
                chunk_assessments = data.get("chunk_assessments", [])
                query_aspects = data.get("query_aspects", [])
                informations = data.get("informations_principales_extraites", [])
                data_gaps = data.get("data_gaps", [])
                executive_summary = data.get("executive_summary", "")

        # --- Construction du détail par chunk (fusion données ChromaDB + jugement LLM) ---
        llm_by_chunk = {}
        for a in chunk_assessments:
            m = re.search(r"\d+", str(a.get("chunk", "")))
            if m:
                llm_by_chunk[int(m.group())] = a

        chunk_details = []
        llm_relevance_scores = []
        useful_flags = []
        for idx, r in enumerate(results, start=1):
            llm_a = llm_by_chunk.get(idx)
            entry = {
                "chunk": f"R{idx}",
                "id": r.id,
                "chroma_score": round(r.score, 3),
                "source": r.source_url or "N/A",
                "snippet": (r.text[:150] + "...") if len(r.text) > 150 else r.text,
            }
            if llm_a:
                entry["llm_relevance_score"] = llm_a.get("relevance_score")
                entry["useful_for_answering"] = llm_a.get("useful_for_answering")
                entry["reason"] = llm_a.get("reason", "")
                if isinstance(llm_a.get("relevance_score"), (int, float)):
                    llm_relevance_scores.append(float(llm_a["relevance_score"]))
                if isinstance(llm_a.get("useful_for_answering"), bool):
                    useful_flags.append(llm_a["useful_for_answering"])
            chunk_details.append(entry)

        # --- Calcul final des 4 métriques : LLM si dispo, sinon fallback ---
        methods = {}

        if llm_relevance_scores:
            llm_relevance = sum(llm_relevance_scores) / len(llm_relevance_scores)
            relevance = round(0.3 * llm_relevance + 0.7 * relevance_fallback, 1)
            methods["relevance"] = "hybrid (LLM + similarité ChromaDB)"
        else:
            relevance = relevance_fallback
            methods["relevance"] = "heuristic (similarité ChromaDB uniquement)"

        if useful_flags and len(useful_flags) == len(results):
            context_precision = round((sum(useful_flags) / len(results)) * 100, 1)
            methods["context_precision"] = "llm"
        else:
            context_precision = precision_fallback
            methods["context_precision"] = "heuristic (proxy score ChromaDB)"

        if query_aspects:
            covered = sum(1 for a in query_aspects if a.get("covered") is True)
            coverage = round((covered / len(query_aspects)) * 100, 1)
            methods["coverage"] = "llm"
        else:
            coverage = coverage_fallback
            methods["coverage"] = "heuristic (couverture mots-clés)"

        methods["diversity"] = "heuristic (dissimilarité lexicale, toujours calculée)"

        # --- Score global pondéré ---
        overall = round(
            relevance * self.WEIGHTS["relevance"]
            + context_precision * self.WEIGHTS["context_precision"]
            + coverage * self.WEIGHTS["coverage"]
            + diversity * self.WEIGHTS["diversity"],
            1,
        )

        return QueryEvaluation(
            query=query,
            total_results=len(results),
            overall_score=overall,
            relevance_score=relevance,
            coverage_score=coverage,
            context_precision_score=context_precision,
            diversity_score=diversity,
            scoring_methods=methods,
            chunk_details=chunk_details,
            query_aspects=query_aspects,
            informations_principales_extraites=informations,
            data_gaps=data_gaps,
            executive_summary=executive_summary,
            model_used=self.model,
            error=error,
        )


# =============================================================================
# RAPPORT FORMATÉ
# =============================================================================

def format_report(ev: QueryEvaluation) -> str:
    lines = [f"# Évaluation du Retriever RAG — {ev.query}", f"\n**Chunks analysés**: {ev.total_results}"]

    if ev.total_results == 0:
        lines.append(f"\n## Erreur\n{ev.error}")
        return "\n".join(lines)

    lines += [
        "\n## Scores (4 métriques principales)",
        f"- **Global**: {ev.overall_score:.1f}/100",
        f"- Relevance (pertinence des chunks): {ev.relevance_score:.1f}/100 _(méthode: {ev.scoring_methods.get('relevance', 'N/A')})_",
        f"- Context Precision (chunks vraiment utiles): {ev.context_precision_score:.1f}/100 _(méthode: {ev.scoring_methods.get('context_precision', 'N/A')})_",
        f"- Coverage (aspects de la question couverts): {ev.coverage_score:.1f}/100 _(méthode: {ev.scoring_methods.get('coverage', 'N/A')})_",
        f"- Diversity (dissimilarité entre chunks): {ev.diversity_score:.1f}/100 _(méthode: {ev.scoring_methods.get('diversity', 'N/A')})_",
    ]

    if ev.error:
        lines.append(f"\n⚠️ {ev.error}")

    if ev.query_aspects:
        lines.append("\n## Aspects de la question et leur couverture")
        for a in ev.query_aspects:
            status = "✅" if a.get("covered") else "❌"
            chunks = ", ".join(a.get("supporting_chunks", [])) or "aucun"
            lines.append(f"- {status} **{a.get('aspect', 'N/A')}** (supporté par: {chunks})")

    if ev.chunk_details:
        lines.append("\n## Détail par chunk")
        lines.append("| Chunk | Score ChromaDB | Score LLM | Utile ? | Raison | Extrait |")
        lines.append("|---|---|---|---|---|---|")
        for d in ev.chunk_details:
            useful = d.get("useful_for_answering")
            useful_str = "✅" if useful is True else ("❌" if useful is False else "N/A")
            llm_score = d.get("llm_relevance_score", "N/A")
            reason = str(d.get("reason", "")).replace("|", "/")
            snippet = d["snippet"].replace("\n", " ").replace("|", "/")
            lines.append(
                f"| {d['chunk']} | {d['chroma_score']} | {llm_score} | {useful_str} | {reason} | {snippet} |"
            )

    if ev.informations_principales_extraites:
        lines.append("\n## Informations principales extraites")
        for info in ev.informations_principales_extraites:
            label = info.get("information", "Information")
            valeur = info.get("valeur", "N/A")
            source = info.get("source", "N/A")
            lines.append(f"- **{label}**: {valeur} (source: {source})")

    if ev.data_gaps:
        lines.append("\n## Gaps d'information\n" + "\n".join(f"- {g}" for g in ev.data_gaps))

    if ev.executive_summary:
        lines.append(f"\n## Synthèse\n{ev.executive_summary}")

    return "\n".join(lines)


def evaluation_to_dict(ev: QueryEvaluation) -> Dict[str, Any]:
    """Export structuré (JSON) pour usage programmatique / comparaison entre recherches."""
    return {
        "query": ev.query,
        "total_results": ev.total_results,
        "scores": {
            "overall": ev.overall_score,
            "relevance": ev.relevance_score,
            "context_precision": ev.context_precision_score,
            "coverage": ev.coverage_score,
            "diversity": ev.diversity_score,
        },
        "scoring_methods": ev.scoring_methods,
        "query_aspects": ev.query_aspects,
        "chunk_details": ev.chunk_details,
        "informations_principales_extraites": ev.informations_principales_extraites,
        "data_gaps": ev.data_gaps,
        "executive_summary": ev.executive_summary,
        "model_used": ev.model_used,
        "error": ev.error,
    }


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

def main():
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        api_key = OpenRouterConfig.api_key
    if not api_key:
        logger.error("OPENROUTER_API_KEY non défini dans les variables d'environnement")
        return

    api_key = api_key.strip()
    if not api_key.startswith("sk-or-"):
        logger.warning(
            f"La clé chargée ne ressemble pas à une clé OpenRouter valide. "
            f"Clé actuelle (masquée): {api_key[:6]}...{api_key[-4:] if len(api_key) > 10 else ''}"
        )

    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
    else:
        file_path = Path(r"C:\Users\ghofr\Documents\acorbeille\data_2\searching\fused_demande_hyde.md")

    if not file_path.exists():
        logger.error(f"Fichier non trouvé: {file_path}")
        return

    content = file_path.read_text(encoding="utf-8")

    llm_client = OpenRouterLLMClient(api_key=api_key)
    judge = RAGJudge(max_chunks=20, debug=True, llm_client=llm_client)
    evaluation = judge.evaluate(content)

    report = format_report(evaluation)
    out_path = file_path.parent / f"judge_{file_path.stem}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    json_path = file_path.parent / f"judge_{file_path.stem}.json"
    json_path.write_text(
        json.dumps(evaluation_to_dict(evaluation), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(report)
    print(f"\nRapport Markdown sauvegardé: {out_path}")
    print(f"Export JSON sauvegardé: {json_path}")


if __name__ == "__main__":
    main()