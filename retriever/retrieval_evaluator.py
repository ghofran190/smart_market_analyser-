"""
Retrieval quality evaluator.

Measures the quality of retrieved documents independently of downstream usage.
Input : normalized retrieval results (question + K chunks)
Output: Relevance, Coverage, Diversity + composite score.
"""

import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from clients import LLMClient, OpenRouterLLMClient

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from retreiver.methode_retrieval import NormalizedResult

# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class RetrievalEvaluationInput:
    """Input for retrieval evaluation."""

    query: str
    results: List[NormalizedResult]


@dataclass
class RetrievalEvaluationResult:
    """Result of retrieval quality evaluation."""

    relevance_score: float
    coverage_score: float
    diversity_score: float
    composite_score: float

    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relevance_score": round(self.relevance_score, 4),
            "coverage_score": round(self.coverage_score, 4),
            "diversity_score": round(self.diversity_score, 4),
            "composite_score": round(self.composite_score, 4),
            "details": self.details,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        lines = [
            "# 🔍 Retrieval Quality Evaluation",
            "",
            f"**Query:** {self.details.get('query', '')}",
            f"**Number of chunks:** {self.details.get('num_chunks', 0)}",
            "",
            "## 📊 Scores",
            "",
            "| Metric | Score | Weight | Weighted Contribution |",
            "|--------|-------|--------|----------------------|",
            f"| Relevance | {self.relevance_score:.4f} | 0.50 | {self.relevance_score * 0.40:.4f} |",
            f"| Coverage | {self.coverage_score:.4f} | 0.30 | {self.coverage_score * 0.35:.4f} |",
            f"| Diversity | {self.diversity_score:.4f} | 0.20 | {self.diversity_score * 0.25:.4f} |",
            "",
            f"## 🎯 Composite Score",
            "",
            f"**{self.composite_score:.4f}**",
            "",
        ]

        relevance_details = self.details.get("relevance", {})
        if relevance_details:
            lines.extend(["## 📌 Relevance Details", ""])
            lines.append(f"- LLM score: {relevance_details.get('llm_score', 'N/A')}")
            lines.append(f"- Heuristic score: {relevance_details.get('heuristic_score', 'N/A')}")
            lines.append("")

        coverage_details = self.details.get("coverage", {})
        aspects = coverage_details.get("aspects", [])
        coverage_items = coverage_details.get("coverage_details", [])
        if aspects:
            lines.extend(["## 🧩 Aspects Coverage", ""])
            for item in coverage_items:
                status = "✅" if item.get("covered") else "❌"
                lines.append(f"- {status} **{item.get('aspect', '')}**")
                lines.append(f"  - Max similarity: {item.get('max_similarity', 'N/A')}")
            lines.append("")

        diversity_details = self.details.get("diversity", {})
        if diversity_details:
            lines.extend(["## 🌐 Diversity Details", ""])
            lines.append(f"- Method: {diversity_details.get('method', 'N/A')}")
            lines.append(f"- Mean dissimilarity: {diversity_details.get('mean_dissimilarity', 'N/A')}")
            lines.append(f"- Number of pairs: {diversity_details.get('num_pairs', 'N/A')}")
            lines.append("")

        return "\n".join(lines) + "\n"

    def save(
        self,
        output_path: str,
        also_json: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Save evaluation result to disk."""
        save_evaluation(self, output_path, also_json=also_json, logger=logger)


# ============================================================================
# LEXICAL DIVERSITY HELPERS (mirrors rag_judge.py)
# ============================================================================


STOPWORDS_FR = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "à", "au",
    "aux", "pour", "par", "dans", "sur", "avec", "est", "sont", "que", "qui",
    "ce", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "quel", "quelle",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zàâäéèêëïîôöùûüç]{4,}", text.lower())
    return {w for w in words if w not in STOPWORDS_FR}


# ============================================================================
# HELPERS
# ============================================================================


def _normalize_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ============================================================================
# METRIC 1: CONTEXTUAL RELEVANCE
# ============================================================================


class RelevanceMetric:
    """
    Hybrid relevance: LLM-as-judge + retriever score heuristic.
    """

    def __init__(self, llm_client: LLMClient, logger: Optional[logging.Logger] = None):
        self.llm_client = llm_client
        self.logger = logger or logging.getLogger(__name__)

    def evaluate(self, query: str, results: List[NormalizedResult]) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate relevance.

        Returns:
            (score, details)
        """
        if not results:
            return 0.0, {"reason": "no results"}

        # 1. LLM judgment
        llm_score = self._llm_judge(query, results)

        # 2. Heuristic from retriever scores
        heuristic_score = self._heuristic_score(results)

        # 3. Hybrid combination
        final_score = 0.5 * llm_score + 0.5 * heuristic_score

        details = {
            "llm_score": round(llm_score, 4),
            "heuristic_score": round(heuristic_score, 4),
            "weights": {"llm": 0.5, "heuristic": 0.5},
        }

        return _normalize_score(final_score), details

    def _llm_judge(self, query: str, results: List[NormalizedResult]) -> float:
        """Ask LLM to judge each chunk's usefulness."""
        system = (
            "Tu es un évaluateur de qualité de recherche documentaire. "
            "Pour chaque extrait fourni, tu dois répondre UNIQUEMENT par un chiffre :\n"
            "1 = Inutile (ne contient aucune information pertinente pour répondre à la question)\n"
            "2 = Partiellement utile (contient des informations partiellement pertinentes)\n"
            "3 = Très utile (contient des informations clairement pertinentes et complètes)\n\n"
            "Tu dois répondre STRICTEMENT au format JSON suivant, sans aucun texte supplémentaire :\n"
            '{"scores": [1, 2, 3, ...]}'
        )

        chunks_text = "\n\n".join(
            f"[Extrait {i+1}]\n{r.text[:2000]}"
            for i, r in enumerate(results)
        )

        user = (
            f"## Question\n{query}\n\n"
            f"## Extraits à évaluer\n{chunks_text}\n\n"
            "Évalue chaque extrait de 1 à 3 selon son utilité pour répondre à la question. "
            "Réponds uniquement avec le JSON demandé."
        )

        raw = self._call_llm(system, user)
        parsed = self._try_parse_json(raw)

        if parsed and "scores" in parsed:
            scores = parsed["scores"]
            if len(scores) != len(results):
                self.logger.warning(
                    f"LLM returned {len(scores)} scores for {len(results)} chunks, "
                    "falling back to uniform scoring."
                )
                scores = [2] * len(results)
        else:
            self.logger.warning("LLM relevance judgment failed, using uniform 2.")
            scores = [2] * len(results)

        # Convert {1, 2, 3} -> {0, 0.5, 1}
        normalized = [(s - 1) / 2.0 for s in scores]
        return sum(normalized) / len(normalized) if normalized else 0.0

    def _heuristic_score(self, results: List[NormalizedResult]) -> float:
        """Average retriever score as heuristic relevance.

        If the retriever scores are effectively identical (e.g. all 1.0 due to
        min-max normalization saturation), fall back to rank-discounted scoring
        so the heuristic still discriminates between retrieval methods.
        """
        scores = [r.score for r in results if r.score is not None]
        if not scores:
            return 0.0

        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

        if variance < 1e-4:
            n = len(scores)
            rank_weights = [1.0 - 0.5 * (i / max(n - 1, 1)) for i in range(n)]
            return sum(rank_weights) / n

        return mean_score

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        last_error = None
        for attempt in range(1, 4):
            try:
                result = self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.0,
                    max_tokens=2000,
                )
                if result and result.strip():
                    return result.strip()
            except Exception as e:
                last_error = e
                self.logger.warning(f"RelevanceMetric LLM attempt {attempt} failed: {e}")
                time.sleep(min(2 ** attempt, 8))
        return ""

    def _try_parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        candidate = raw.strip()
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


# ============================================================================
# METRIC 2: INFORMATIONAL COVERAGE
# ============================================================================


class CoverageMetric:
    """
    Aspect-based coverage: decompose question into aspects,
    then verify each aspect is covered by at least one chunk.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        embedder: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.llm_client = llm_client
        self.embedder = embedder
        self.logger = logger or logging.getLogger(__name__)
        self._similarity_threshold = 0.5
        self._aspect_cache: Dict[str, List[str]] = {}



    def reset_cache(self):
        """Reset the aspect cache."""
        self._aspect_cache.clear()
        self.logger.info("CoverageMetric cache cleared")

    def evaluate(self, query: str, results: List[NormalizedResult]) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate coverage using discrete sub-theme scoring.

        Returns:
            (score in [0, 1], details)
        """
        if not results:
            return 0.0, {"reason": "no results", "aspects": []}

        # 1. Decompose question into aspects
        aspects = self._decompose_question(query)

        if not aspects:
            return 1.0, {"aspects": [], "reason": "no aspects to cover"}

        # 2. For each aspect, compute max similarity across all chunks,
        #    then map to discrete coverage score.
        chunk_embeddings = self._get_embeddings([r.text for r in results])
        coverage_details = []
        aspect_scores: List[float] = []

        for aspect in aspects:
            aspect_embedding = self._get_embeddings([aspect])[0]
            max_sim = 0.0
            best_idx = -1

            for idx, chunk_emb in enumerate(chunk_embeddings):
                sim = _cosine_similarity(aspect_embedding, chunk_emb)
                if sim > max_sim:
                    max_sim = sim
                    best_idx = idx

            if max_sim >= 0.6:
                s = 1.0
            elif max_sim >= 0.4:
                s = 0.5
            else:
                s = 0.0

            aspect_scores.append(s)
            coverage_details.append({
                "aspect": aspect,
                "max_similarity": round(max_sim, 4),
                "score": s,
                "best_chunk_id": results[best_idx].id if best_idx >= 0 else None,
            })

        score = sum(aspect_scores) / len(aspects) if aspects else 0.0

        details = {
            "aspects": aspects,
            "coverage_details": coverage_details,
            "covered": sum(1 for s in aspect_scores if s >= 1.0),
            "partial": sum(1 for s in aspect_scores if s == 0.5),
            "uncovered": sum(1 for s in aspect_scores if s == 0.0),
            "total": len(aspects),
        }

        return _normalize_score(score), details

    def _decompose_question(self, query: str) -> List[str]:
        """Decompose question into distinct aspects using LLM."""
        normalized_query = query.strip()
        if normalized_query in self._aspect_cache:
            return self._aspect_cache[normalized_query]

        system = (
            "Tu es un analyste expert en décomposition de questions. "
            "Ta tâche : décomposer la question suivante en aspects distincts et concis. "
            "Chaque aspect doit être une phrase courte ou un groupe de mots représentant "
            "une facette informationnelle distincte de la question.\n\n"
            "Tu dois répondre STRICTEMENT au format JSON suivant :\n"
            '{"aspects": ["aspect 1", "aspect 2", ...]}'
        )

        user = f"## Question\n{query}\n\nDécompose cette question en aspects distincts."

        raw = self._call_llm(system, user)
        parsed = self._try_parse_json(raw)

        if parsed and "aspects" in parsed and isinstance(parsed["aspects"], list):
            aspects = [a.strip() for a in parsed["aspects"] if a.strip()]
        else:
            fallback = [a.strip() for a in re.split(r'[?;]', query) if a.strip()]
            aspects = fallback if fallback else [query]

        self._aspect_cache[normalized_query] = aspects
        return aspects

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for texts."""
        if not texts:
            return np.array([])

        if self.embedder is not None:
            try:
                embeddings = self.embedder.encode(texts, normalize_embeddings=True)
                if isinstance(embeddings, np.ndarray):
                    return embeddings
                return np.array(embeddings)
            except Exception as e:
                self.logger.warning(f"Embedding failed: {e}")

        # Fallback: random embeddings (should not happen in production)
        self.logger.warning("No embedder available, using random embeddings.")
        return np.random.rand(len(texts), 384).astype(np.float32)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        last_error = None
        for attempt in range(1, 4):
            try:
                result = self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.0,
                    max_tokens=1000,
                )
                if result and result.strip():
                    return result.strip()
            except Exception as e:
                last_error = e
                self.logger.warning(f"CoverageMetric LLM attempt {attempt} failed: {e}")
                time.sleep(min(2 ** attempt, 8))
        return ""

    def _try_parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        candidate = raw.strip()
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


# ============================================================================
# METRIC 3: DIVERSITY (lexical Jaccard dissimilarity, mirrors rag_judge.py)
# ============================================================================


class DiversityMetric:
    """
    Hybrid diversity: lexical Jaccard dissimilarity + optional semantic
    cosine dissimilarity, aggregated with a trimmed mean.

    Mirrors rag_judge._score_diversity for the lexical baseline, but
    augments it with embedding-based semantic diversity when an embedder
    is available. This better distinguishes complementary chunks from
    merely lexically distinct ones.
    """

    def __init__(
        self,
        embedder: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.embedder = embedder
        self.logger = logger or logging.getLogger(__name__)

    def evaluate(self, results: List[NormalizedResult]) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate diversity using hybrid lexical + semantic dissimilarity.

        Returns:
            (score in [0, 1], details)
        """
        if len(results) < 2:
            return 0.5, {"reason": "less than 2 results, neutral diversity"}

        token_sets = [_tokenize(r.text) for r in results]

        # Lexical dissimilarities: 1 - Jaccard similarity
        lexical_dissimilarities: List[float] = []
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                a, b = token_sets[i], token_sets[j]
                if not a and not b:
                    continue
                union = a | b
                inter = a & b
                jaccard_sim = len(inter) / len(union) if union else 0.0
                lexical_dissimilarities.append(1.0 - jaccard_sim)

        if not lexical_dissimilarities:
            return 0.5, {"reason": "no comparable pairs"}

        # Semantic dissimilarities: 1 - cosine similarity (optional)
        semantic_dissimilarities: Optional[List[float]] = None
        if self.embedder is not None:
            try:
                embeddings = self._get_embeddings([r.text for r in results])
                if len(embeddings) >= 2:
                    semantic_dissimilarities = []
                    for i in range(len(embeddings)):
                        for j in range(i + 1, len(embeddings)):
                            sim = _cosine_similarity(embeddings[i], embeddings[j])
                            semantic_dissimilarities.append(1.0 - sim)
            except Exception as e:
                self.logger.warning(f"Semantic diversity failed: {e}")

        # Combine lexical and semantic dissimilarities
        if (
            semantic_dissimilarities is not None
            and len(semantic_dissimilarities) == len(lexical_dissimilarities)
        ):
            combined = [
                0.4 * lex + 0.6 * sem
                for lex, sem in zip(lexical_dissimilarities, semantic_dissimilarities)
            ]
            method = "hybrid_lexical_semantic"
        else:
            combined = lexical_dissimilarities
            method = "lexical_jaccard"

        # Robust aggregation: trimmed mean (10% from each tail)
        trimmed = self._trimmed_mean(combined, trim_fraction=0.1)
        diversity_score = _normalize_score(trimmed)

        # Build details
        details: Dict[str, Any] = {
            "num_pairs": len(combined),
            "mean_dissimilarity": round(trimmed, 4),
            "min_dissimilarity": round(min(combined), 4),
            "max_dissimilarity": round(max(combined), 4),
            "method": method,
        }
        if semantic_dissimilarities:
            details["semantic_mean_dissimilarity"] = round(
                sum(semantic_dissimilarities) / len(semantic_dissimilarities), 4
            )

        return diversity_score, details

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for texts using the available embedder."""
        if not texts:
            return np.array([])

        if self.embedder is not None:
            try:
                embeddings = self.embedder.encode(texts, normalize_embeddings=True)
                if isinstance(embeddings, np.ndarray):
                    return embeddings
                return np.array(embeddings)
            except Exception as e:
                self.logger.warning(f"Embedding failed: {e}")

        self.logger.warning("No embedder available, using random embeddings.")
        return np.random.rand(len(texts), 384).astype(np.float32)

    @staticmethod
    def _trimmed_mean(values: List[float], trim_fraction: float = 0.1) -> float:
        """Compute a trimmed mean to reduce the impact of outlier pairs."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        trim_count = int(n * trim_fraction)
        if trim_count > 0:
            sorted_vals = sorted_vals[trim_count:-trim_count]
        if not sorted_vals:
            return 0.0
        return sum(sorted_vals) / len(sorted_vals)


# ============================================================================
# RETRIEVAL EVALUATOR
# ============================================================================


class RetrievalEvaluator:
    """
    Evaluates retrieval quality using Relevance, Coverage, and Diversity metrics.

    Usage:
        evaluator = RetrievalEvaluator(
            llm_client=llm_client,
            chroma_manager=chroma,
            logger=logger,
        )
        result = evaluator.evaluate(query, results)
        print(result.composite_score)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        chroma_manager: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.llm_client = llm_client
        self.logger = logger or logging.getLogger(__name__)

        # Try to get embedder from chroma_manager
        embedder = None
        if chroma_manager is not None:
            try:
                embedder = chroma_manager.embedder
            except AttributeError:
                self.logger.warning("ChromaManager has no embedder attribute.")

        # Fallback: try to load sentence-transformers directly
        if embedder is None and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                embedder = SentenceTransformer("BAAI/bge-m3")
                self.logger.info("Loaded fallback embedder: BAAI/bge-m3")
            except Exception as e:
                self.logger.warning(f"Failed to load fallback embedder: {e}")

        self.embedder = embedder

        self.relevance_metric = RelevanceMetric(llm_client, self.logger)
        self.coverage_metric = CoverageMetric(llm_client, self.embedder, self.logger)
        self.diversity_metric = DiversityMetric(self.embedder, self.logger)

    def evaluate(
        self,
        query: str,
        results: List[NormalizedResult],
        weights: Optional[Dict[str, float]] = None,
    ) -> RetrievalEvaluationResult:
        """
        Evaluate retrieval quality.

        Args:
            query: Original search query
            results: List of NormalizedResult
            weights: Optional custom weights for composite score

        Returns:
            RetrievalEvaluationResult with all scores
        """
        weights = weights or {
            "relevance": 0.5,
            "coverage": 0.3,
            "diversity": 0.2,
        }

        self.logger.info(
            f"Evaluating retrieval for query: '{query[:60]}...' "
            f"with {len(results)} results"
        )

        # Metric 1: Relevance
        relevance_score, relevance_details = self.relevance_metric.evaluate(query, results)
        self.logger.info(f"Relevance: {relevance_score:.4f}")

        # Metric 2: Coverage
        coverage_score, coverage_details = self.coverage_metric.evaluate(query, results)
        self.logger.info(f"Coverage: {coverage_score:.4f}")

        # Metric 3: Diversity
        diversity_score, diversity_details = self.diversity_metric.evaluate(results)
        self.logger.info(f"Diversity: {diversity_score:.4f}")

        # Composite
        composite_score = (
            weights["relevance"] * relevance_score
            + weights["coverage"] * coverage_score
            + weights["diversity"] * diversity_score
        )

        details = {
            "query": query,
            "num_chunks": len(results),
            "weights": weights,
            "relevance": relevance_details,
            "coverage": coverage_details,
            "diversity": diversity_details,
        }

        return RetrievalEvaluationResult(
            relevance_score=relevance_score,
            coverage_score=coverage_score,
            diversity_score=diversity_score,
            composite_score=composite_score,
            details=details,
        )

    def evaluate_batch(
        self,
        inputs: List[RetrievalEvaluationInput],
        weights: Optional[Dict[str, float]] = None,
    ) -> List[RetrievalEvaluationResult]:
        """
        Evaluate multiple retrieval results.

        Args:
            inputs: List of RetrievalEvaluationInput
            weights: Optional custom weights

        Returns:
            List of RetrievalEvaluationResult
        """
        return [
            self.evaluate(inp.query, inp.results, weights)
            for inp in inputs
        ]


# ============================================================================
# SAVE FUNCTION
# ============================================================================


def save_evaluation(
    result: RetrievalEvaluationResult,
    output_path: str,
    also_json: bool = True,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Save evaluation result to disk.

    Writes:
        - Markdown report at `output_path` (or with `.md` extension)
        - JSON export at same path with `.json` extension if `also_json=True`

    Args:
        result: RetrievalEvaluationResult to save
        output_path: Path to save the file
        also_json: Also save JSON export
        logger: Optional logger instance
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    md_path = output_path.with_suffix(".md") if output_path.suffix != ".md" else output_path
    md_path.write_text(result.to_markdown(), encoding="utf-8")
    logger.info(f"✅ Evaluation saved to: {md_path}")

    if also_json:
        json_path = output_path.with_suffix(".json") if output_path.suffix != ".json" else output_path.with_suffix(".json")
        json_path.write_text(result.to_json(), encoding="utf-8")
        logger.info(f"✅ Evaluation JSON saved to: {json_path}")


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def evaluate_retrieval(
    query: str,
    results: List[NormalizedResult],
    llm_client: LLMClient,
    chroma_manager: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
    weights: Optional[Dict[str, float]] = None,
) -> RetrievalEvaluationResult:
    """
    Shortcut: evaluate retrieval quality.

    Example:
        result = evaluate_retrieval(
            query="What is the market size?",
            results=normalized_results,
            llm_client=llm_client,
            chroma_manager=chroma,
        )
        print(f"Composite score: {result.composite_score:.4f}")
    """
    evaluator = RetrievalEvaluator(
        llm_client=llm_client,
        chroma_manager=chroma_manager,
        logger=logger,
    )
    return evaluator.evaluate(query, results, weights)


# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    from clients import OpenRouterLLMClient
    from retreiver.methode_retrieval import NormalizedResult
    
    # # Create two test chunks
    # chunk1 = NormalizedResult(
    #     id="chunk_1",
    #     text=""" L'intelligence artificielle est devenue omniprésente dans notre quotidien. Elle transforme radicalement nos habitudes sans que nous le réalisions toujours.""",
    #     metadata={},
    #     score=0.9,
    #     query="test query"
    # )

    # chunk2 = NormalizedResult(
    #     id="chunk_2", 
    #     text="""la taille du marché mondial des produits pharmaceutiques est évaluée à environ 2 150 milliards de dollars en 2026 .""" ,
    #     metadata={},
    #     score=0.8,
    #     query="test query"
    # )



    llm_client = OpenRouterLLMClient(model="openai/gpt-4.1-mini")
    evaluator = RetrievalEvaluator(llm_client=llm_client, logger=logger)
    # score, details =evaluator.diversity_metric.evaluate([chunk1,chunk2])

    # # Display results
    # print(f"Diversity Score: {score:.4f}")
    # print(f"Details: {details}")

    query = "How is the current demand and client segments for the PMS SaaS market for independent hotels?"

    dummy_results = [
        NormalizedResult(
            id="chunk_1",
            text="The PMS SaaS market for independent hotels is growing rapidly, with a CAGR of 12% expected through 2028. Demand is driven by small chains seeking cloud-based solutions.",
            metadata={"source_url": "https://example.com/1"},
            score=0.89,
            query=query,
        ),
        NormalizedResult(
            id="chunk_2",
            text="Independent hotels in France represent a significant segment, with 60% of properties using cloud PMS solutions. Key decision factors include ease of use and integration capabilities.",
            metadata={"source_url": "https://example.com/2"},
            score=0.76,
            query=query,
        ),
        NormalizedResult(
            id="chunk_3",
            text="The global luxury hotel market reached $450 billion in 2024, with 5-star chains dominating urban locations.",
            metadata={"source_url": "https://example.com/3"},
            score=0.45,
            query=query,
        ),
    ]

    result = evaluator.evaluate(query, dummy_results)

    print("\n" + "=" * 70)
    print("📋 Retrieval Quality Evaluation")
    print("=" * 70)
    print(result.to_json())
    print("\n" + result.to_markdown())

    save_evaluation(result=result,output_path="data_testing/evaluation")


