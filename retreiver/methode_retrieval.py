"""
Multiple retrieval methods with normalized output format.

Implements:
- M1: Pure vector search with reranking
- M2: Hybrid search (vector + BM25) with reranking
- M3a: Vector search with HyDE generation + reranking
- M3b: Vector search for multiple sub-queries with fusion + reranking
- M4a: Hybrid search for sub-queries with fusion + reranking
- M4b: Hybrid search with HyDE for original query + reranking
- M4c: Hybrid search for sub-queries with fusion and reranking
"""

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from embedding.chroma_manager import ChromaManager
# from llm_config import LLMClient, OpenRouterLLMClient

from retreiver.rtriever import Retriever, RetrievalResult, RetrievalResponse, VectorRetrievalConfig
from retreiver.hybrid_retreiver import (
    HybridRetriever,
    HybridResult,
    MergedHybridResult,
    HybridResultReporter,
    HybridSearchConfig,
    aggregate_scores,
)
from retreiver.hybrid_retreiver import CROSS_ENCODER_AVAILABLE
import concurrent.futures
from clients import APIClients , OpenRouterLLMClient

# ============================================================================
# NORMALIZED RESULT FORMAT
# ============================================================================


@dataclass
class NormalizedResult:
    """Unified result format across all retrieval methods."""

    id: str
    text: str
    metadata: Dict[str, Any]
    score: float
    method: str = ""
    query: str = ""
    sub_queries: List[str] = field(default_factory=list)

    vector_score: Optional[float] = None
    lexical_score: Optional[float] = None
    hybrid_score: Optional[float] = None
    rerank_score: Optional[float] = None
    per_query_scores: Optional[Dict[str, float]] = None
    query_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "score": self.score,
            "method": self.method,
            "query": self.query,
            "sub_queries": self.sub_queries,
            "vector_score": self.vector_score,
            "lexical_score": self.lexical_score,
            "hybrid_score": self.hybrid_score,
            "rerank_score": self.rerank_score,
            "per_query_scores": self.per_query_scores,
            "query_count": self.query_count,
        }


# ============================================================================
# CONVERSION HELPERS
# ============================================================================


def _retrieval_result_to_normalized(
    result: RetrievalResult,
    method: str,
    query: str,
    sub_queries: List[str] = None,
) -> NormalizedResult:
    """Convert RetrievalResult to NormalizedResult."""
    return NormalizedResult(
        id=result.id,
        text=result.text,
        metadata=result.metadata,
        score=result.score,
        method=method,
        query=query,
        sub_queries=sub_queries or [],
        vector_score=result.vector_score,
        rerank_score=result.rerank_score,
    )


def _hybrid_result_to_normalized(
    result: HybridResult,
    method: str,
    query: str,
    sub_queries: List[str] = None,
) -> NormalizedResult:
    """Convert HybridResult to NormalizedResult."""
    return NormalizedResult(
        id=result.id,
        text=result.text,
        metadata=result.metadata,
        score=result.score,
        method=method,
        query=query,
        sub_queries=sub_queries or [],
        vector_score=result.embedding_score,
        lexical_score=result.lexical_score,
        hybrid_score=result.hybrid_score,
        rerank_score=result.rerank_score,
    )


def _merged_hybrid_result_to_normalized(
    result: MergedHybridResult,
    method: str,
    query: str,
    sub_queries: List[str] = None,
) -> NormalizedResult:
    """Convert MergedHybridResult to NormalizedResult."""
    return NormalizedResult(
        id=result.id,
        text=result.text,
        metadata=result.metadata,
        score=result.score,
        method=method,
        query=query,
        sub_queries=sub_queries or [],
        per_query_scores=result.per_query_scores,
        query_count=result.query_count,
    )


def _retrieval_response_to_normalized(
    response: RetrievalResponse,
    method: str,
    query: str,
    sub_queries: List[str] = None,
) -> List[NormalizedResult]:
    """Convert RetrievalResponse to list of NormalizedResult."""
    return [
        _retrieval_result_to_normalized(r, method, query, sub_queries)
        for r in response.results
    ]


# ============================================================================
# HYDE GENERATOR
# ============================================================================


class HyDEGenerator:
    """Generate hypothetical answers (HyDE) for a given query."""

    def __init__(self, llm_client:OpenRouterLLMClient, logger: Optional[logging.Logger] = None):
        self.llm_client = llm_client
        self.logger = logger or logging.getLogger(__name__)

    def generate(
        self,
        query: str,
        temperature: float = 0.4,
        max_tokens: int = 400,
    ) -> str:
        """Generate a hypothetical answer for the query."""
        system = (
            "Tu es un expert en recherche documentaire pour des études de marché. "
            "Ta tâche : écrire un paragraphe hypothétique (technique HyDE) qui "
            "ressemble le plus possible à un extrait RÉEL d'un rapport d'étude "
            "de marché professionnel sur ce sujet précis (vocabulaire sectoriel, "
            "chiffres plausibles, structure), afin de maximiser la pertinence "
            "d'une recherche par similarité dans une base de connaissance de "
            "rapports de marché. N'ajoute aucun commentaire, écris directement "
            "le paragraphe."
        )
        user = (
            f"## Question principale\n{query}\n\n"
            "## Consigne\nRéécris cette réponse hypothétique en un paragraphe "
            "dense (4 à 6 phrases), au style d'un extrait de rapport d'étude "
            "de marché professionnel, qui servira UNIQUEMENT de requête de "
            "recherche. Ne dis pas 'je', ne mentionne pas qu'il s'agit d'une "
            "hypothèse : écris directement le paragraphe."
        )

        try:
            result = self.llm_client.generate(
                system_prompt=system,
                user_prompt=user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if result and result.strip():
                return result.strip()
        except Exception as e:
            self.logger.warning(f"HyDE generation failed: {e}")

        return query


# ============================================================================
# MARKDOWN SAVER
# ============================================================================


def save_results_markdown(
    results: List[NormalizedResult],
    output_path: str,
    method: str,
    collection_name: str,
    original_query: str,
    sub_queries: Optional[List[str]] = None,
) -> Path:
    """
    Save results in the exact normalized Markdown format.

    Args:
        results: List of normalized results
        output_path: Path to save the .md file
        method: Method name (e.g., "M1 Pure Vectorial")
        collection_name: Collection name
        original_query: Original search query
        sub_queries: Optional list of sub-queries used

    Returns:
        Path to saved file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sub_queries = sub_queries or []

    lines = [
        "# 🔍 Search Results",
        "",
        f"**Method:** {method}",
        f"**Collection:** `{collection_name}`",
        f"**Original Query:** {original_query}",
    ]

    if sub_queries:
        lines.append(f"**Sub-queries:** {', '.join(sub_queries)}")
    else:
        lines.append("**Sub-queries:** None")

    lines.extend([
        f"**Date:** {now}",
        f"**Number of Results:** {len(results)}",
        "",
        "---",
        "",
        "## 📊 Statistics",
        "",
    ])

    if results:
        scores = [r.score for r in results if r.score is not None]
        if scores:
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            min_score = min(scores)
            variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
            std_dev = math.sqrt(variance)

            lines.extend([
                f"- **Mean Score:** {avg_score:.4f}",
                f"- **Max Score:** {max_score:.4f}",
                f"- **Min Score:** {min_score:.4f}",
                f"- **Standard Deviation:** {std_dev:.4f}",
            ])
    else:
        lines.append("_No results available._")

    lines.extend([
        "",
        "---",
        "",
        "## 📄 Detailed Results",
        "",
    ])

    for i, result in enumerate(results, 1):
        score_pct = int(max(0.0, min(result.score or 0.0, 1.0)) * 100)
        bar_length = 20
        filled = min(score_pct // 5, bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        lines.extend([
            f"### Result {i}",
            "",
            f"**ID:** `{result.id}`",
            "",
            f"**Score:** `{result.score:.4f}`  `{score_pct}%`  `[{bar}]`",
            "",
            "**Text:**",
            "",
            f"> {result.text}",
            "",
            "**Metadata:**",
            "",
            "| Key | Value |",
            "|-----|-------|",
        ])

        if result.metadata:
            for key, value in result.metadata.items():
                if value is not None and str(value).strip():
                    lines.append(f"| {key} | {value} |")

        lines.extend([
            "",
            f"**Source:** `{result.metadata.get('source_url', result.metadata.get('source_file', 'N/A'))}`",
            "",
            "---",
            "",
        ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


# ============================================================================
# RETRIEVAL METHODS
# ============================================================================


class RetrievalMethods:
    """
    Collection of retrieval methods with normalized output.

    Usage:
        methods = RetrievalMethods(
            chroma_manager=chroma,
            hybrid_retriever=hybrid_retriever,
            vector_retriever=vector_retriever,
            hyde_generator=hyde_generator,
            collection_name="hotellerie_saas",
        )
        results = methods.m1_pure_vectorial("query")
        save_results_markdown(results, "output.md", "M1 Pure Vectorial", ...)
    """

    def __init__(
        self,
        chroma_manager: ChromaManager,
        hybrid_retriever: HybridRetriever,
        vector_retriever: Retriever,
        hyde_generator: HyDEGenerator,
        collection_name: str,
        logger: Optional[logging.Logger] = None,
    ):
        self.chroma = chroma_manager
        self.hybrid_retriever = hybrid_retriever
        self.vector_retriever = vector_retriever
        self.hyde_generator = hyde_generator
        self.collection_name = collection_name
        self.logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # M1: Pure Vectorial Search
    # ------------------------------------------------------------------

    def m1_pure_vectorial(
        self,
        query: str,
        n_results: int = 30,
        top_k: int = 20,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
    ) -> List[NormalizedResult]:
        """
        M1: Semantic retrieval (vector search using ChromaManager with reranking).

        Args:
            query: Search query
            n_results: Number of initial results from vector search
            top_k: Number of final results
            use_reranking: Whether to use cross-encoder reranking
            min_score_threshold: Minimum score threshold

        Returns:
            List of NormalizedResult
        """
        self.logger.info(f"[M1] Pure vectorial search: '{query[:60]}...'")

        response = self.vector_retriever.search(
            query=query,
            collection_name=self.collection_name,
            n_results=n_results,
            top_k=top_k,
            use_reranking=use_reranking,
            min_score_threshold=min_score_threshold,
        )

        return _retrieval_response_to_normalized(
            response, "M1 Pure Vectorial", query
        )

    # ------------------------------------------------------------------
    # M2: Hybrid Search
    # ------------------------------------------------------------------

    def m2_hybrid_search(
        self,
        query: str,
        top_k: int = 20,
        n_candidates: int = 50,
        embedding_weight: float = 0.5,
        lexical_weight: float = 0.5,
        hybrid_weight_final: float = 0.3,
        rerank_weight_final: float = 0.7,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
    ) -> List[NormalizedResult]:
        """
        M2: Hybrid search (vector + BM25) with final reranking.

        Args:
            query: Search query
            top_k: Number of final results
            n_candidates: Number of candidates per branch
            embedding_weight: Weight for embedding in hybrid score
            lexical_weight: Weight for lexical in hybrid score
            hybrid_weight_final: Weight for hybrid score in final
            rerank_weight_final: Weight for rerank score in final
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold

        Returns:
            List of NormalizedResult
        """
        self.logger.info(f"[M2] Hybrid search: '{query[:60]}...'")

        results = self.hybrid_retriever.search(
            query=query,
            collection_name=self.collection_name,
            top_k=top_k,
            n_candidates=n_candidates,
            embedding_weight=embedding_weight,
            lexical_weight=lexical_weight,
            hybrid_weight_final=hybrid_weight_final,
            rerank_weight_final=rerank_weight_final,
            normalize=True,
            min_score_threshold=min_score_threshold,
            use_reranking=use_reranking,
        )

        return [
            _hybrid_result_to_normalized(r, "M2 Hybrid", query)
            for r in results
        ]

    # ------------------------------------------------------------------
    # M3a: Vector Search with HyDE
    # ------------------------------------------------------------------

    def m3a_vector_hyde(
        self,
        query: str,
        n_results: int = 30,
        top_k: int = 20,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
        hyde_temperature: float = 0.4,
    ) -> List[NormalizedResult]:
        """
        M3a: Vector search with HyDE generation + reranking.

        Generates a hypothetical answer using LLM, then uses it as the
        search query for vector retrieval with reranking.

        Args:
            query: Original search query
            n_results: Number of initial results
            top_k: Number of final results
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold
            hyde_temperature: Temperature for HyDE generation

        Returns:
            List of NormalizedResult
        """
        self.logger.info(f"[M3a] Vector search with HyDE: '{query[:60]}...'")

        hyde_answer = self.hyde_generator.generate(
            query=query,
            temperature=hyde_temperature,
        )

        self.logger.info(f"[M3a] HyDE answer generated: '{hyde_answer[:60]}...'")

        response = self.vector_retriever.search(
            query=hyde_answer,
            collection_name=self.collection_name,
            n_results=n_results,
            top_k=top_k,
            use_reranking=use_reranking,
            min_score_threshold=min_score_threshold,
        )

        results = _retrieval_response_to_normalized(
            response, "M3a Vector + HyDE", query
        )
        for r in results:
            r.sub_queries = [hyde_answer]

        return results

    # ------------------------------------------------------------------
    # M3b: Vector Search for Multiple Sub-Queries with Fusion
    # ------------------------------------------------------------------

    def m3b_vector_multi_query_fusion(
        self,
        query: str,
        sub_queries: List[str],
        n_results: int = 30,
        top_k: int = 20,
        final_top_k: int = 20,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
    ) -> List[NormalizedResult]:
        """
        M3b: Vector search for multiple sub-queries with result fusion and reranking.

        Args:
            query: Original search query
            sub_queries: List of sub-queries to search
            n_results: Number of initial results per query
            top_k: Number of results per query before fusion
            final_top_k: Number of final fused results
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold

        Returns:
            List of NormalizedResult
        """
        self.logger.info(
            f"[M3b] Vector multi-query fusion: '{query[:60]}...' "
            f"with {len(sub_queries)} sub-queries"
        )

        response = self.vector_retriever.search_with_fusion(
            sub_queries=sub_queries,
            original_query=query,
            collection_name=self.collection_name,
            n_results=n_results,
            top_k=top_k,
            final_top_k=final_top_k,
            use_reranking=use_reranking,
            min_score_threshold=min_score_threshold,
        )

        return _retrieval_response_to_normalized(
            response, "M3b Vector Multi-Query Fusion", query, sub_queries
        )

    # ------------------------------------------------------------------
    # M4a: Hybrid Search for Sub-Queries with Fusion
    # ------------------------------------------------------------------

    def m4a_hybrid_multi_query_fusion(
        self,
        query: str,
        sub_queries: List[str],
        top_k: int = 20,
        n_candidates_per_query: int = 30,
        n_candidates: int = 50,
        embedding_weight: float = 0.5,
        lexical_weight: float = 0.5,
        hybrid_weight_final: float = 0.3,
        rerank_weight_final: float = 0.7,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
        merge_strategy: str = "max",
        multi_query_bonus: float = 0.05,
    ) -> List[NormalizedResult]:
        """
        M4a: Hybrid search for sub-queries with fusion and reranking.

        Uses search_batch for each sub-query, then manually merges results
        using the same aggregation logic as hybrid_search_multi_query.

        Args:
            query: Original search query
            sub_queries: List of sub-queries to search
            top_k: Number of final results
            n_candidates_per_query: Number of results per query before fusion
            n_candidates: Number of candidates per branch
            embedding_weight: Weight for embedding in hybrid score
            lexical_weight: Weight for lexical in hybrid score
            hybrid_weight_final: Weight for hybrid score in final
            rerank_weight_final: Weight for rerank score in final
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold
            merge_strategy: How to aggregate scores ("max", "mean", "sum_capped")
            multi_query_bonus: Bonus per additional sub-query

        Returns:
            List of NormalizedResult
        """
        self.logger.info(
            f"[M4a] Hybrid multi-query fusion: '{query[:60]}...' "
            f"with {len(sub_queries)} sub-queries"
        )

        if not sub_queries:
            return []

        # Run hybrid batch search
        results_by_subquery = self.hybrid_retriever.search_batch(
            queries=sub_queries,
            collection_name=self.collection_name,
            top_k=n_candidates_per_query,
            n_candidates=n_candidates,
            embedding_weight=embedding_weight,
            lexical_weight=lexical_weight,
            hybrid_weight_final=hybrid_weight_final,
            rerank_weight_final=rerank_weight_final,
            normalize=True,
            min_score_threshold=min_score_threshold,
            use_reranking=use_reranking,
        )

        # Merge results by document ID
        merged: Dict[str, Dict[str, Any]] = {}
        for sub_query, results in results_by_subquery.items():
            for r in results:
                if r.id not in merged:
                    merged[r.id] = {
                        "text": r.text,
                        "metadata": r.metadata,
                        "per_query_scores": {},
                    }
                merged[r.id]["per_query_scores"][sub_query] = r.final_score

        if not merged:
            return []

        # Aggregate scores
        final_results: List[NormalizedResult] = []
        for doc_id, entry in merged.items():
            scores = list(entry["per_query_scores"].values())
            matched_queries = list(entry["per_query_scores"].keys())

            if merge_strategy == "max":
                base_score = max(scores)
            elif merge_strategy == "mean":
                base_score = sum(scores) / len(scores)
            elif merge_strategy == "sum_capped":
                base_score = min(sum(scores), 1.0)
            else:
                base_score = max(scores)

            consensus_bonus = min(
                multi_query_bonus * (len(matched_queries) - 1),
                HybridSearchConfig.MAX_MULTI_QUERY_BONUS,
            )
            final_score = max(0.0, min(base_score + consensus_bonus, 1.0))

            final_results.append(
                NormalizedResult(
                    id=doc_id,
                    text=entry["text"],
                    metadata=entry["metadata"],
                    score=final_score,
                    method="M4a Hybrid Multi-Query Fusion",
                    query=query,
                    sub_queries=sub_queries,
                    per_query_scores=entry["per_query_scores"],
                    query_count=len(matched_queries),
                )
            )

        final_results.sort(key=lambda r: r.score, reverse=True)
        return final_results[:top_k]

    # ------------------------------------------------------------------
    # M4b: Hybrid Search with HyDE
    # ------------------------------------------------------------------

    def m4b_hybrid_hyde(
        self,
        query: str,
        top_k: int = 20,
        n_candidates: int = 50,
        embedding_weight: float = 0.5,
        lexical_weight: float = 0.5,
        hybrid_weight_final: float = 0.3,
        rerank_weight_final: float = 0.7,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
        hyde_temperature: float = 0.4,
    ) -> List[NormalizedResult]:
        """
        M4b: Hybrid search with HyDE for the original query + reranking.

        Generates a hypothetical answer using LLM, then uses it as the
        search query for hybrid retrieval with reranking.

        Args:
            query: Original search query
            top_k: Number of final results
            n_candidates: Number of candidates per branch
            embedding_weight: Weight for embedding in hybrid score
            lexical_weight: Weight for lexical in hybrid score
            hybrid_weight_final: Weight for hybrid score in final
            rerank_weight_final: Weight for rerank score in final
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold
            hyde_temperature: Temperature for HyDE generation

        Returns:
            List of NormalizedResult
        """
        self.logger.info(f"[M4b] Hybrid search with HyDE: '{query[:60]}...'")

        hyde_answer = self.hyde_generator.generate(
            query=query,
            temperature=hyde_temperature,
        )

        self.logger.info(f"[M4b] HyDE answer generated: '{hyde_answer[:60]}...'")

        results = self.hybrid_retriever.search(
            query=hyde_answer,
            collection_name=self.collection_name,
            top_k=top_k,
            n_candidates=n_candidates,
            embedding_weight=embedding_weight,
            lexical_weight=lexical_weight,
            hybrid_weight_final=hybrid_weight_final,
            rerank_weight_final=rerank_weight_final,
            normalize=True,
            min_score_threshold=min_score_threshold,
            use_reranking=use_reranking,
        )

        normalized = [
            _hybrid_result_to_normalized(r, "M4b Hybrid + HyDE", query)
            for r in results
        ]
        for r in normalized:
            r.sub_queries = [hyde_answer]

        return normalized

# ------------------------------------------------------------------
# M4c: Hybrid Search for Sub-Queries with Fusion (Multi-Query)
# ------------------------------------------------------------------

    def m4c_hybrid_multi_query(
        self,
        query: str,
        sub_queries: List[str],
        top_k: int = 20,
        n_candidates_per_query: int = 30,
        n_candidates: int = 50,
        embedding_weight: float = 0.5,
        lexical_weight: float = 0.5,
        hybrid_weight_final: float = 0.3,
        rerank_weight_final: float = 0.7,
        use_reranking: bool = True,
        min_score_threshold: float = 0.0,
        merge_strategy: str = "max",
        multi_query_bonus: float = 0.05,
        hyde_temperature: float = 0.4,
    ) -> List[NormalizedResult]:
        """
        M4c: Hybrid multi-query search with HyDE + fusion.

        Same fusion logic as M4a, but instead of using raw sub-queries
        directly, we first generate a HyDE response for each sub-query,
        then execute the hybrid search on those HyDE-generated responses.

        Args:
            query: Original search query
            sub_queries: List of sub-queries to search
            top_k: Number of final results
            n_candidates_per_query: Number of results per query before fusion
            n_candidates: Number of candidates per branch
            embedding_weight: Weight for embedding in hybrid score
            lexical_weight: Weight for lexical in hybrid score
            hybrid_weight_final: Weight for hybrid score in final
            rerank_weight_final: Weight for rerank score in final
            use_reranking: Whether to use reranking
            min_score_threshold: Minimum score threshold
            merge_strategy: How to aggregate scores ("max", "mean", "sum_capped")
            multi_query_bonus: Bonus per additional sub-query
            hyde_temperature: Temperature for HyDE generation

        Returns:
            List of NormalizedResult
        """
        self.logger.info(
            f"[M4c] Hybrid multi-query with HyDE: '{query[:60]}...' "
            f"with {len(sub_queries)} sub-queries"
        )

        if not sub_queries:
            return []

        # Step 1: Generate HyDE for each sub-query
        hyde_queries = []
        for sq in sub_queries:
            hyde_answer = self.hyde_generator.generate(
                query=sq,
                temperature=hyde_temperature,
            )
            hyde_queries.append(hyde_answer)
            self.logger.debug(
                f"[M4c] HyDE for sub-query '{sq[:60]}...': '{hyde_answer[:60]}...'"
            )

        # Step 2: Execute hybrid search on each HyDE response
        results_by_subquery = self.hybrid_retriever.search_batch(
            queries=hyde_queries,
            collection_name=self.collection_name,
            top_k=n_candidates_per_query,
            n_candidates=n_candidates,
            embedding_weight=embedding_weight,
            lexical_weight=lexical_weight,
            hybrid_weight_final=hybrid_weight_final,
            rerank_weight_final=rerank_weight_final,
            normalize=True,
            min_score_threshold=min_score_threshold,
            use_reranking=use_reranking,
        )

        # Step 3: Merge results by document ID (same as M4a)
        merged: Dict[str, Dict[str, Any]] = {}
        for hyde_q, results in results_by_subquery.items():
            for r in results:
                if r.id not in merged:
                    merged[r.id] = {
                        "text": r.text,
                        "metadata": r.metadata,
                        "per_query_scores": {},
                    }
                merged[r.id]["per_query_scores"][hyde_q] = r.final_score

        if not merged:
            return []

        # Step 4: Aggregate scores + consensus bonus
        final_results: List[NormalizedResult] = []
        for doc_id, entry in merged.items():
            scores = list(entry["per_query_scores"].values())
            matched_queries = list(entry["per_query_scores"].keys())

            if merge_strategy == "max":
                base_score = max(scores)
            elif merge_strategy == "mean":
                base_score = sum(scores) / len(scores)
            elif merge_strategy == "sum_capped":
                base_score = min(sum(scores), 1.0)
            else:
                base_score = max(scores)

            consensus_bonus = min(
                multi_query_bonus * (len(matched_queries) - 1),
                HybridSearchConfig.MAX_MULTI_QUERY_BONUS,
            )
            final_score = max(0.0, min(base_score + consensus_bonus, 1.0))

            final_results.append(
                NormalizedResult(
                    id=doc_id,
                    text=entry["text"],
                    metadata=entry["metadata"],
                    score=final_score,
                    method="M4c Hybrid Multi-Query + HyDE",
                    query=query,
                    sub_queries=sub_queries,
                    per_query_scores=entry["per_query_scores"],
                    query_count=len(matched_queries),
                )
            )

        final_results.sort(key=lambda r: r.score, reverse=True)
        return final_results[:top_k]

    # ------------------------------------------------------------------
    # M4b: Hybrid Search with HyDE
    # ------------------------------------------------------------------

# ============================================================================
# BATCH WRAPPER
# ============================================================================


def run_all_methods(
    query: str,
    chroma_manager: ChromaManager,
    collection_name: str,
    output_dir: str = "data/search_results/methods",
    sub_queries: Optional[List[str]] = None,
    llm_client: Optional[OpenRouterLLMClient] = None,
    top_k: int = 20,
    n_results: int = 30,
    n_candidates: int = 50,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, List[NormalizedResult]]:
    """
    Run all retrieval methods for a given query and save results.

    Args:
        query: Original search query
        chroma_manager: ChromaManager instance
        collection_name: Collection name
        output_dir: Directory to save markdown results
        sub_queries: Optional list of sub-queries for multi-query methods
        llm_client: Optional LLM client for HyDE methods
        top_k: Number of final results
        n_results: Number of initial results for vector search
        n_candidates: Number of candidates for hybrid search
        logger: Optional logger

    Returns:
        Dictionary mapping method name to list of NormalizedResult
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    sub_queries = sub_queries or []

    # Initialize components
    vector_config = VectorRetrievalConfig()
    vector_retriever = Retriever(chroma_manager, vector_config, logger)

    hybrid_config = HybridSearchConfig()
    hybrid_retriever = HybridRetriever(chroma_manager, hybrid_config, logger)

    hyde_generator = HyDEGenerator(llm_client, logger) if llm_client else None

    methods = RetrievalMethods(
        chroma_manager=chroma_manager,
        hybrid_retriever=hybrid_retriever,
        vector_retriever=vector_retriever,
        hyde_generator=hyde_generator or HyDEGenerator(None, logger),
        collection_name=collection_name,
        logger=logger,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_results: Dict[str, List[NormalizedResult]] = {}

    # M1: Pure Vectorial
    logger.info("Running M1: Pure Vectorial Search")
    m1_results = methods.m1_pure_vectorial(
        query=query,
        n_results=n_results,
        top_k=top_k,
    )
    all_results["M1"] = m1_results
    save_results_markdown(
        m1_results,
        output_path / f"M1_pure_vectorial_{timestamp}.md",
        "M1 Pure Vectorial",
        collection_name,
        query,
    )

    # M2: Hybrid
    logger.info("Running M2: Hybrid Search")
    m2_results = methods.m2_hybrid_search(
        query=query,
        top_k=top_k,
        n_candidates=n_candidates,
    )
    all_results["M2"] = m2_results
    save_results_markdown(
        m2_results,
        output_path / f"M2_hybrid_{timestamp}.md",
        "M2 Hybrid (Vector + BM25)",
        collection_name,
        query,
    )

    # M3a: Vector + HyDE
    if hyde_generator and hyde_generator.llm_client:
        logger.info("Running M3a: Vector Search with HyDE")
        m3a_results = methods.m3a_vector_hyde(
            query=query,
            n_results=n_results,
            top_k=top_k,
        )
        all_results["M3a"] = m3a_results
        save_results_markdown(
            m3a_results,
            output_path / f"M3a_vector_hyde_{timestamp}.md",
            "M3a Vector + HyDE",
            collection_name,
            query,
            m3a_results[0].sub_queries if m3a_results else [],
        )
    else:
        logger.warning("M3a skipped: no LLM client provided for HyDE generation")

    # M3b: Vector Multi-Query Fusion
    if sub_queries:
        logger.info(f"Running M3b: Vector Multi-Query Fusion ({len(sub_queries)} sub-queries)")
        m3b_results = methods.m3b_vector_multi_query_fusion(
            query=query,
            sub_queries=sub_queries,
            n_results=n_results,
            top_k=top_k,
            final_top_k=top_k,
        )
        all_results["M3b"] = m3b_results
        save_results_markdown(
            m3b_results,
            output_path / f"M3b_vector_multi_query_{timestamp}.md",
            "M3b Vector Multi-Query Fusion",
            collection_name,
            query,
            sub_queries,
        )
    else:
        logger.warning("M3b skipped: no sub-queries provided")

    # M4a: Hybrid Multi-Query Fusion (manual merge)
    if sub_queries:
        logger.info(f"Running M4a: Hybrid Multi-Query Fusion ({len(sub_queries)} sub-queries)")
        m4a_results = methods.m4a_hybrid_multi_query_fusion(
            query=query,
            sub_queries=sub_queries,
            top_k=top_k,
            n_candidates_per_query=top_k,
            n_candidates=n_candidates,
        )
        all_results["M4a"] = m4a_results
        save_results_markdown(
            m4a_results,
            output_path / f"M4a_hybrid_multi_query_{timestamp}.md",
            "M4a Hybrid Multi-Query Fusion",
            collection_name,
            query,
            sub_queries,
        )
    else:
        logger.warning("M4a skipped: no sub-queries provided")

    # M4b: Hybrid + HyDE
    if hyde_generator and hyde_generator.llm_client:
        logger.info("Running M4b: Hybrid Search with HyDE")
        m4b_results = methods.m4b_hybrid_hyde(
            query=query,
            top_k=top_k,
            n_candidates=n_candidates,
        )
        all_results["M4b"] = m4b_results
        save_results_markdown(
            m4b_results,
            output_path / f"M4b_hybrid_hyde_{timestamp}.md",
            "M4b Hybrid + HyDE",
            collection_name,
            query,
            m4b_results[0].sub_queries if m4b_results else [],
        )
    else:
        logger.warning("M4b skipped: no LLM client provided for HyDE generation")

    # M4c: Hybrid Multi-Query (search_multi_query)
    if sub_queries:
        logger.info(f"Running M4c: Hybrid Multi-Query ({len(sub_queries)} sub-queries)")
        m4c_results = methods.m4c_hybrid_multi_query(
            query=query,
            sub_queries=sub_queries,
            top_k=top_k,
            n_candidates_per_query=top_k,
            n_candidates=n_candidates,
        )
        all_results["M4c"] = m4c_results
        save_results_markdown(
            m4c_results,
            output_path / f"M4c_hybrid_multi_query_{timestamp}.md",
            "M4c Hybrid Multi-Query",
            collection_name,
            query,
            sub_queries,
        )
    else:
        logger.warning("M4c skipped: no sub-queries provided")

    logger.info(f"✅ All methods completed. Results saved to {output_path}")
    return all_results


# ============================================================================
# DEMO
# ============================================================================

# if __name__ == "__main__":
#     logging.basicConfig(
#         level=logging.INFO,
#         format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     )
#     logger = logging.getLogger(__name__)

#     chroma = ChromaManager(persist_directory="data/chromadb")
#     collection_name = "hotellerie_saas"

#     vector_config = VectorRetrievalConfig()
#     vector_retriever = Retriever(chroma, vector_config, logger)

#     hybrid_config = HybridSearchConfig()
#     hybrid_retriever = HybridRetriever(chroma, hybrid_config, logger)

#     llm_client = OpenRouterLLMClient(model="openai/gpt-4.1-mini")
#     hyde_generator = HyDEGenerator(llm_client, logger)

#     methods = RetrievalMethods(
#         chroma_manager=chroma,
#         hybrid_retriever=hybrid_retriever,
#         vector_retriever=vector_retriever,
#         hyde_generator=hyde_generator,
#         collection_name=collection_name,
#         logger=logger,
#     )

#     query = "How is the current demand and client segments for the PMS SaaS market for independent hotels?"
#     sub_queries = [
#         "demande actuelle PMS SaaS hôtels indépendants",
#         "segments de clientèle PMS cloud hôtellerie",
#         "adoption solutions SaaS hôtellerie indépendante",
#     ]

#     print("\n" + "=" * 70)
#     print("🧪 TESTING ALL RETRIEVAL METHODS")
#     print("=" * 70)
#     valeurs_k = [10, 12, 15, 20]
#     for k in valeurs_k:
#         # M1
#         print(f"\n[M1] Pure Vectorial Search for k = {k}")
#         m1 = methods.m1_pure_vectorial(query, top_k=k)
#         print(f"   -> {len(m1)} results")
#         save_results_markdown(
#             m1, f"reteiver/results/M1_pure_vectorial_k_{k}.md",
#             "M1 Pure Vectorial", collection_name, query,
#         )





#     # # M2
#     # print("[M2] Hybrid Search")
#     # m2 = methods.m2_hybrid_search(query, top_k=10)
#     # print(f"   -> {len(m2)} results")
#     # save_results_markdown(
#     #     m2, "retreiver/results/M2_hybrid.md",
#     #     "M2 Hybrid (Vector + BM25)", collection_name, query,
#     # )



    

#     # # M3a
#     # print("[M3a] Vector + HyDE")
#     # m3a = methods.m3a_vector_hyde(query, top_k=10)
#     # print(f"   -> {len(m3a)} results")
#     # save_results_markdown(
#     #     m3a, "data/search_results/M3a_vector_hyde.md",
#     #     "M3a Vector + HyDE", collection_name, query,
#     #     m3a[0].sub_queries if m3a else [],
#     # )


#     # # M3b
#     # print("[M3b] Vector Multi-Query Fusion")
#     # m3b = methods.m3b_vector_multi_query_fusion(query, sub_queries, top_k=10, final_top_k=10)
#     # print(f"   -> {len(m3b)} results")
#     # save_results_markdown(
#     #     m3b, "data/search_results/M3b_vector_multi_query.md",
#     #     "M3b Vector Multi-Query Fusion", collection_name, query, sub_queries,
#     # )

#     # # M4a
#     # print("[M4a] Hybrid Multi-Query Fusion (manual)")
#     # m4a = methods.m4a_hybrid_multi_query_fusion(query, sub_queries, top_k=10)
#     # print(f"   -> {len(m4a)} results")
#     # save_results_markdown(
#     #     m4a, "data/search_results/M4a_hybrid_multi_query.md",
#     #     "M4a Hybrid Multi-Query Fusion", collection_name, query, sub_queries,
#     # )

#     # # M4b
#     # print("[M4b] Hybrid + HyDE")
#     # m4b = methods.m4b_hybrid_hyde(query, top_k=10)
#     # print(f"   -> {len(m4b)} results")
#     # save_results_markdown(
#     #     m4b, "data/search_results/M4b_hybrid_hyde.md",
#     #     "M4b Hybrid + HyDE", collection_name, query,
#     #     m4b[0].sub_queries if m4b else [],
#     # )

#     # # M4c
#     # print("[M4c] Hybrid Multi-Query")
#     # m4c = methods.m4c_hybrid_multi_query(query, sub_queries, top_k=10)
#     # print(f"   -> {len(m4c)} results")
#     # save_results_markdown(
#     #     m4c, "data/search_results/M4c_hybrid_multi_query.md",
#     #     "M4c Hybrid Multi-Query", collection_name, query, sub_queries,
#     # )

#     # print("\n" + "=" * 70)
#     # print("✅ All methods tested successfully!")
#     # print("=" * 70)
