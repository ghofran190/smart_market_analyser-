


"""
Hybrid Retrieval Module
Combines embedding-based (ChromaDB) and lexical (BM25) search with CrossEncoder reranking
"""

import logging
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

import numpy as np

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    print("Warning: CrossEncoder not available. Install with: pip install sentence-transformers")

from embedding.chroma_manager import ChromaManager


# =============================================================================
# CONFIGURATION
# =============================================================================

class HybridSearchConfig:
    """Configuration for hybrid search operations."""

    # Default search parameters
    TOP_K = 20
    N_CANDIDATES = 50
    RERANK_BATCH_SIZE = 64

    # Score weights
    EMBEDDING_WEIGHT = 0.5
    LEXICAL_WEIGHT = 0.5
    HYBRID_WEIGHT_FINAL = 0.3
    RERANK_WEIGHT_FINAL = 0.7

    # Reranking
    RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Multi-query fusion
    MERGE_STRATEGY = "max"  # max, mean, sum_capped
    MULTI_QUERY_BONUS = 0.05
    MAX_MULTI_QUERY_BONUS = 0.2

    # Thresholds
    MIN_SCORE_THRESHOLD = 0.0
    SIMILARITY_THRESHOLD = 0.85

    # Normalization
    NORMALIZE_SCORES = True


def _coalesce(value, default):
    """
    Return `value` if it was explicitly provided (not None), else `default`.

    IMPORTANT: this is NOT the same as `value or default`. `value or default`
    silently overrides legitimate falsy values like 0.0 (e.g. an explicit
    embedding_weight=0.0 to disable the embedding branch), which was the
    source of several bugs in earlier versions of this module.
    """
    return value if value is not None else default


# =============================================================================
# BM25 IMPLEMENTATION
# =============================================================================

class BM25:
    """BM25 implementation for lexical search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = []
        self.doc_lengths = []
        self.avg_doc_length = 0
        self.doc_freqs = defaultdict(int)
        self.idf = {}
        self.doc_count = 0
        self.tokenized_corpus = []

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Simple tokenizer."""
        text = text.lower()
        tokens = []
        current_token = ""
        for char in text:
            if char.isalnum():
                current_token += char
            else:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
        if current_token:
            tokens.append(current_token)
        return tokens

    def fit(self, documents: List[str]) -> None:
        """Build BM25 index."""
        self.corpus = documents
        self.doc_count = len(documents)

        self.tokenized_corpus = [self.tokenize(doc) for doc in documents]
        self.doc_lengths = [len(tokens) for tokens in self.tokenized_corpus]
        self.avg_doc_length = sum(self.doc_lengths) / self.doc_count if self.doc_count else 0

        # Calculate document frequencies
        self.doc_freqs = defaultdict(int)
        for tokens in self.tokenized_corpus:
            for term in set(tokens):
                self.doc_freqs[term] += 1

        # Calculate IDF
        for term, freq in self.doc_freqs.items():
            self.idf[term] = math.log(
                (self.doc_count - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def search(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        """Search using BM25."""
        query_tokens = self.tokenize(query)
        scores = []

        # BUGFIX: guard against division by zero when the corpus is empty
        # or every document is empty (avg_doc_length == 0).
        avg_doc_length = self.avg_doc_length or 1

        for doc_idx, tokens in enumerate(self.tokenized_corpus):
            score = 0
            doc_len = self.doc_lengths[doc_idx]

            term_freqs = defaultdict(int)
            for term in tokens:
                term_freqs[term] += 1

            for term in query_tokens:
                if term not in self.doc_freqs or term not in term_freqs:
                    continue

                tf = term_freqs[term]
                idf = self.idf[term]

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / avg_doc_length)
                score += idf * (numerator / denominator)

            scores.append((doc_idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# =============================================================================
# RESULT CLASSES
# =============================================================================
class HybridResult:
    """Result from a hybrid search (embedding + lexical + rerank)."""

    def __init__(
        self,
        id: str,
        text: str,
        metadata: Dict[str, Any],
        embedding_score: float = 0.0,
        lexical_score: float = 0.0,
        hybrid_score: Optional[float] = None,
        rerank_score: Optional[float] = None,
        final_score: Optional[float] = None,
    ):
        self.id = id
        self.text = text
        self.metadata = metadata
        self.embedding_score = embedding_score
        self.lexical_score = lexical_score
        self.hybrid_score = hybrid_score if hybrid_score is not None else 0.0
        self.rerank_score = rerank_score
        self.final_score = final_score if final_score is not None else self.hybrid_score

    @property
    def score(self) -> float:
        return self.final_score if self.final_score is not None else self.hybrid_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "embedding_score": self.embedding_score,
            "lexical_score": self.lexical_score,
            "hybrid_score": self.hybrid_score,
            "rerank_score": self.rerank_score,
            "final_score": self.final_score,
        }


# =============================================================================
# Résultat obtenu en fusionnant les HybridResult
# =============================================================================

class MergedHybridResult:
    """Result from multi-query fusion."""

    def __init__(
        self,
        id: str,
        text: str,
        metadata: Dict[str, Any],
        per_query_scores: Dict[str, float],
        matched_queries: List[str],
        final_score: float,
    ):
        self.id = id
        self.text = text
        self.metadata = metadata
        self.per_query_scores = per_query_scores
        self.matched_queries = matched_queries
        self.query_count = len(matched_queries)
        # BUGFIX: final_score used to be `base_score + consensus_bonus` with
        # no upper bound, which let scores exceed 1.0 (e.g. 1.0639 / 106%
        # in saved reports) whenever the base score was already close to 1.0.
        # Clamp to [0, 1] so downstream percentage/bar rendering stays correct.
        self.final_score = max(0.0, min(final_score, 1.0))

    @property
    def score(self) -> float:
        return self.final_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "per_query_scores": self.per_query_scores,
            "matched_queries": self.matched_queries,
            "query_count": self.query_count,
            "final_score": self.final_score,
        }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_scores(values: List[float]) -> List[float]:
    """Min-max normalize scores to [0, 1] range."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi > lo:
        return [(v - lo) / (hi - lo) for v in values]
    return [0.5 for _ in values]


def text_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity between two texts."""
    if not text1 or not text2:
        return 0.0

    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    return intersection / union if union > 0 else 0.0


def aggregate_scores(scores: List[float], strategy: str) -> float:
    """Aggregate scores using specified strategy."""
    if not scores:
        return 0.0

    if strategy == "max":
        return max(scores)
    elif strategy == "mean":
        return sum(scores) / len(scores)
    elif strategy == "sum_capped":
        return min(sum(scores), 1.0)
    else:
        raise ValueError(f"Unknown merge strategy: {strategy}")


# =============================================================================
# SEARCH OPERATIONS
# =============================================================================
class HybridRetriever:
    """Main retriever class for hybrid search operations."""

    def __init__(
        self,
        chroma_manager: ChromaManager,
        config: Optional[HybridSearchConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.chroma = chroma_manager
        self.config = config or HybridSearchConfig()
        self.logger = logger or logging.getLogger(__name__)
        self._bm25_index = None
        # BUGFIX: was a single `self._reranker` slot, which meant the
        # `rerank_model` argument passed to search()/search_batch() was
        # accepted but silently ignored (get_reranker() always loaded
        # self.config.RERANK_MODEL). Now cached per model name.
        self._rerankers: Dict[str, Optional["CrossEncoder"]] = {}
        self._documents_cache = {}

    # -------------------------------------------------------------------------
    # Document Loading
    # -------------------------------------------------------------------------

    def load_documents(
        self,
        collection_name: str,
        where_filter: Optional[Dict[str, Any]] = None,
        force_reload: bool = False,
    ) -> List[Dict[str, Any]]:
        """Load documents from a collection."""
        cache_key = f"{collection_name}_{where_filter}"

        if not force_reload and cache_key in self._documents_cache:
            return self._documents_cache[cache_key]

        self.logger.info(f"Loading documents from '{collection_name}'...")

        try:
            collection = self.chroma.get_collection(collection_name)
            if collection is None:
                self.logger.error(f"Collection '{collection_name}' not found")
                return []

            raw_all = collection.get(
                where=where_filter,
                include=["documents", "metadatas"]
            )

            documents = []
            for i, text in enumerate(raw_all["documents"]):
                if text and text.strip():
                    documents.append({
                        "id": raw_all["ids"][i] if raw_all["ids"] else f"doc_{i}",
                        "text": text,
                        "metadata": raw_all["metadatas"][i] if raw_all["metadatas"] else {},
                    })

            if not documents:
                self.logger.warning(f"No documents found in '{collection_name}'")
            else:
                self.logger.info(f"✅ Loaded {len(documents)} documents")

            self._documents_cache[cache_key] = documents
            return documents

        except Exception as e:
            self.logger.error(f"Error loading documents: {e}")
            return []

    # -------------------------------------------------------------------------
    # BM25 Index Management
    # -------------------------------------------------------------------------

    def build_bm25_index(self, documents: List[Dict[str, Any]]) -> BM25:
        """Build BM25 index from documents."""
        self.logger.info("Building BM25 index...")
        bm25 = BM25()
        bm25.fit([doc["text"] for doc in documents])
        self._bm25_index = bm25
        return bm25

    def get_bm25_index(self, documents: List[Dict[str, Any]]) -> BM25:
        """Get or create BM25 index."""
        if self._bm25_index is None:
            self._bm25_index = self.build_bm25_index(documents)
        return self._bm25_index

    # -------------------------------------------------------------------------
    # Reranker Management
    # -------------------------------------------------------------------------

    def get_reranker(self, model_name: Optional[str] = None) -> Optional["CrossEncoder"]:
        """Get or load a reranker model, honoring an explicit override."""
        if not CROSS_ENCODER_AVAILABLE:
            return None

        model_name = model_name or self.config.RERANK_MODEL

        if model_name not in self._rerankers:
            try:
                self.logger.info(f"Loading reranker '{model_name}'...")
                self._rerankers[model_name] = CrossEncoder(model_name, max_length=512)
            except Exception as e:
                self.logger.error(f"Error loading reranker: {e}")
                self._rerankers[model_name] = None

        return self._rerankers[model_name]

    # -------------------------------------------------------------------------
    # Core Search Methods
    # -------------------------------------------------------------------------
    # NOTE: _embedding_search, _lexical_search and _fuse_scores previously
    # existed as two identical copies each in this class (the second silently
    # shadowing the first). Harmless while identical, but risky: editing one
    # copy without the other -- as happened elsewhere in this project with
    # base_agent.py's duplicate class definitions -- would silently break
    # behavior. De-duplicated to a single definition of each below.

    def _embedding_search(
        self,
        query: str,
        collection_name: str,
        n_results: int,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Perform embedding-based search."""
        self.logger.debug(f"Embedding search for: '{query[:60]}...'")

        raw_results = self.chroma.search(
            collection_name=collection_name,
            query=query,
            n_results=n_results,
            where_filter=where_filter,
        )

        results = {}
        for r in raw_results:
            text = r.get("text", "")
            if text and text.strip():
                results[r["id"]] = {
                    "text": text,
                    "metadata": r.get("metadata", {}),
                    "embedding_score": r.get("score", 0.0),
                }

        self.logger.debug(f"✅ {len(results)} embedding results")
        return results

    def _lexical_search(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        bm25: BM25,
        n_results: int,
    ) -> Dict[str, Dict[str, Any]]:
        """Perform lexical search using BM25."""
        self.logger.debug(f"Lexical search for: '{query[:60]}...'")

        bm25_scores = bm25.search(query, top_k=n_results)

        results = {}
        for doc_idx, score in bm25_scores:
            if doc_idx < len(documents):
                doc = documents[doc_idx]
                results[doc["id"]] = {
                    "text": doc["text"],
                    "metadata": doc["metadata"],
                    "lexical_score": score,
                }

        self.logger.debug(f"✅ {len(results)} lexical results")
        return results

    def _fuse_scores(
        self,
        embedding_results: Dict[str, Dict[str, Any]],
        lexical_results: Dict[str, Dict[str, Any]],
        embedding_weight: float,
        lexical_weight: float,
        normalize: bool,
    ) -> List[HybridResult]:
        """Fuse embedding and lexical scores."""
        all_ids = set(embedding_results.keys()) | set(lexical_results.keys())
        if not all_ids:
            return []

        # Merge results
        merged = {}
        for doc_id in all_ids:
            emb = embedding_results.get(doc_id)
            lex = lexical_results.get(doc_id)
            merged[doc_id] = {
                "text": (emb or lex)["text"],
                "metadata": (emb or lex)["metadata"],
                "embedding_score": emb["embedding_score"] if emb else 0.0,
                "lexical_score": lex["lexical_score"] if lex else 0.0,
            }

        # Normalize if needed
        ids_ordered = list(merged.keys())
        if normalize:
            emb_values = [merged[i]["embedding_score"] for i in ids_ordered]
            lex_values = [merged[i]["lexical_score"] for i in ids_ordered]

            emb_norm = normalize_scores(emb_values)
            lex_norm = normalize_scores(lex_values)

            for doc_id, e, l in zip(ids_ordered, emb_norm, lex_norm):
                merged[doc_id]["embedding_score"] = e
                merged[doc_id]["lexical_score"] = l

        # Calculate hybrid scores
        results = []
        for doc_id in ids_ordered:
            d = merged[doc_id]
            hybrid_score = (
                embedding_weight * d["embedding_score"] +
                lexical_weight * d["lexical_score"]
            )
            results.append(
                HybridResult(
                    id=doc_id,
                    text=d["text"],
                    metadata=d["metadata"],
                    embedding_score=d["embedding_score"],
                    lexical_score=d["lexical_score"],
                    hybrid_score=hybrid_score,
                )
            )

        results.sort(key=lambda r: r.hybrid_score, reverse=True)
        return results

    def _rerank_results(
        self,
        query: str,
        results: List[HybridResult],
        reranker: Optional["CrossEncoder"],
    ) -> List[HybridResult]:
        """Apply reranking to results."""
        if not reranker or not results:
            return results

        self.logger.info(f"Reranking {len(results)} candidates...")

        try:
            pairs = [(query, r.text) for r in results]
            rerank_scores = reranker.predict(pairs)

            for r, score in zip(results, rerank_scores):
                r.rerank_score = float(score)

            self.logger.info("✅ Reranking complete")
        except Exception as e:
            self.logger.error(f"Reranking error: {e}")

        return results

    def _finalize_results(
        self,
        results: List[HybridResult],
        hybrid_weight: float,
        rerank_weight: float,
        normalize: bool,
        min_threshold: float,
        top_k: int,
    ) -> List[HybridResult]:
        """Finalize results with scoring and filtering."""
        if not results:
            return []

        # Normalize rerank scores if needed
        if normalize:
            rerank_values = [r.rerank_score for r in results if r.rerank_score is not None]
            if rerank_values:
                norm_values = normalize_scores(rerank_values)
                idx = 0
                for r in results:
                    if r.rerank_score is not None:
                        r.rerank_score = norm_values[idx]
                        idx += 1

        # Calculate final scores
        for r in results:
            if r.rerank_score is not None:
                r.final_score = hybrid_weight * r.hybrid_score + rerank_weight * r.rerank_score
            else:
                r.final_score = r.hybrid_score
            # BUGFIX: clamp defensively. hybrid_weight + rerank_weight should
            # sum to 1.0 by convention, but callers can pass arbitrary
            # weights (e.g. both close to 1.0), which would otherwise let
            # final_score drift above 1.0 just like the multi-query bug.
            r.final_score = max(0.0, min(r.final_score, 1.0))

        # Filter and sort
        if min_threshold > 0:
            results = [r for r in results if r.final_score >= min_threshold]

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:top_k]

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        collection_name: str,
        top_k: int = None,
        n_candidates: int = None,
        where_filter: Optional[Dict[str, Any]] = None,
        embedding_weight: float = None,
        lexical_weight: float = None,
        hybrid_weight_final: float = None,
        rerank_weight_final: float = None,
        rerank_model: str = None,
        normalize: bool = None,
        min_score_threshold: float = None,
        use_reranking: bool = True,
    ) -> List[HybridResult]:
        """
        Perform hybrid search for a single query.

        Returns:
            List of HybridResult objects
        """
        # BUGFIX: use `_coalesce` (checks `is not None`) instead of `or`,
        # so explicit falsy values like weight=0.0 or threshold=0.0 are
        # respected instead of silently replaced by config defaults.
        top_k = _coalesce(top_k, self.config.TOP_K)
        n_candidates = _coalesce(n_candidates, self.config.N_CANDIDATES)
        embedding_weight = _coalesce(embedding_weight, self.config.EMBEDDING_WEIGHT)
        lexical_weight = _coalesce(lexical_weight, self.config.LEXICAL_WEIGHT)
        hybrid_weight_final = _coalesce(hybrid_weight_final, self.config.HYBRID_WEIGHT_FINAL)
        rerank_weight_final = _coalesce(rerank_weight_final, self.config.RERANK_WEIGHT_FINAL)
        normalize = _coalesce(normalize, self.config.NORMALIZE_SCORES)
        min_score_threshold = _coalesce(min_score_threshold, self.config.MIN_SCORE_THRESHOLD)

        # Load documents
        documents = self.load_documents(collection_name, where_filter)
        if not documents:
            return []

        # Build BM25 index
        bm25 = self.get_bm25_index(documents)

        # Embedding search
        embedding_results = self._embedding_search(
            query, collection_name, n_candidates, where_filter
        )

        # Lexical search
        lexical_results = self._lexical_search(
            query, documents, bm25, n_candidates
        )

        # Fuse scores
        results = self._fuse_scores(
            embedding_results, lexical_results,
            embedding_weight, lexical_weight, normalize
        )

        if not results:
            return []

        # Rerank
        if use_reranking and CROSS_ENCODER_AVAILABLE:
            reranker = self.get_reranker(rerank_model)
            if reranker:
                results = self._rerank_results(query, results, reranker)

        # Finalize
        return self._finalize_results(
            results, hybrid_weight_final, rerank_weight_final,
            normalize, min_score_threshold, top_k
        )

    def search_batch(
        self,
        queries: List[str],
        collection_name: str,
        top_k: int = None,
        n_candidates: int = None,
        where_filter: Optional[Dict[str, Any]] = None,
        embedding_weight: float = None,
        lexical_weight: float = None,
        hybrid_weight_final: float = None,
        rerank_weight_final: float = None,
        rerank_model: str = None,
        rerank_batch_size: int = None,
        normalize: bool = None,
        min_score_threshold: float = None,
        use_reranking: bool = True,
    ) -> Dict[str, List[HybridResult]]:
        """
        Returns:
            Dictionary mapping query to list of HybridResult
        """

        if not queries:
            return {}

        top_k = _coalesce(top_k, self.config.TOP_K)
        n_candidates = _coalesce(n_candidates, self.config.N_CANDIDATES)
        embedding_weight = _coalesce(embedding_weight, self.config.EMBEDDING_WEIGHT)
        lexical_weight = _coalesce(lexical_weight, self.config.LEXICAL_WEIGHT)
        hybrid_weight_final = _coalesce(hybrid_weight_final, self.config.HYBRID_WEIGHT_FINAL)
        rerank_weight_final = _coalesce(rerank_weight_final, self.config.RERANK_WEIGHT_FINAL)
        rerank_batch_size = _coalesce(rerank_batch_size, self.config.RERANK_BATCH_SIZE)
        normalize = _coalesce(normalize, self.config.NORMALIZE_SCORES)
        min_score_threshold = _coalesce(min_score_threshold, self.config.MIN_SCORE_THRESHOLD)

        # Deduplicate queries while preserving order
        unique_queries = list(dict.fromkeys(queries))

        # Load documents and build BM25 index (shared)
        documents = self.load_documents(collection_name, where_filter)
        if not documents:
            return {q: [] for q in unique_queries}

        bm25 = self.get_bm25_index(documents)

        # Get reranker (shared)
        reranker = None
        if use_reranking and CROSS_ENCODER_AVAILABLE:
            reranker = self.get_reranker(rerank_model)

        # Process each query
        per_query_pool = {}
        all_pairs = []
        pair_owners = []

        for i, query in enumerate(unique_queries, 1):
            self.logger.info(f"[{i}/{len(unique_queries)}] Processing: '{query[:60]}...'")

            embedding_results = self._embedding_search(
                query, collection_name, n_candidates, where_filter
            )

            lexical_results = self._lexical_search(
                query, documents, bm25, n_candidates
            )

            fused = self._fuse_scores(
                embedding_results, lexical_results,
                embedding_weight, lexical_weight, normalize
            )

            if not fused:
                per_query_pool[query] = []
                continue

            # Prepare for batch reranking
            pool = fused[:max(n_candidates, top_k * 2)]
            per_query_pool[query] = pool

            for r in pool:
                all_pairs.append((query, r.text))
                pair_owners.append(r)

        # Batch reranking
        if reranker and all_pairs:
            self.logger.info(f"Batch reranking {len(all_pairs)} pairs...")
            try:
                scores = reranker.predict(all_pairs, batch_size=rerank_batch_size)
                for r, score in zip(pair_owners, scores):
                    r.rerank_score = float(score)
                self.logger.info("✅ Batch reranking complete")
            except Exception as e:
                self.logger.error(f"Batch reranking error: {e}")

        # Finalize each query's results
        final_results = {}
        for query, pool in per_query_pool.items():
            final_results[query] = self._finalize_results(
                pool, hybrid_weight_final, rerank_weight_final,
                normalize, min_score_threshold, top_k
            )
            self.logger.info(f"✅ '{query[:60]}...' -> {len(final_results[query])} results")

        return final_results

    def search_multi_query(
        self,
        sub_queries: List[str],
        global_query: str,
        collection_name: str,
        top_k: int = None,
        n_candidates_per_query: int = None,
        n_candidates: int = None,
        where_filter: Optional[Dict[str, Any]] = None,
        embedding_weight: float = None,
        lexical_weight: float = None,
        hybrid_weight_final: float = None,
        rerank_weight_final: float = None,
        rerank_model: str = None,
        rerank_batch_size: int = None,
        normalize: bool = None,
        min_score_threshold: float = None,
        merge_strategy: str = None,
        multi_query_bonus: float = None,
        max_multi_query_bonus: float = None,
        use_reranking: bool = True,
    ) -> List[MergedHybridResult]:
        """
        Perform multi-query search with result fusion.

        Returns:
            List of MergedHybridResult objects, each with final_score in [0, 1].
        """
        if not sub_queries:
            return []

        top_k = _coalesce(top_k, self.config.TOP_K)
        n_candidates_per_query = _coalesce(n_candidates_per_query, self.config.TOP_K)
        n_candidates = _coalesce(n_candidates, self.config.N_CANDIDATES)
        merge_strategy = _coalesce(merge_strategy, self.config.MERGE_STRATEGY)
        multi_query_bonus = _coalesce(multi_query_bonus, self.config.MULTI_QUERY_BONUS)
        max_multi_query_bonus = _coalesce(max_multi_query_bonus, self.config.MAX_MULTI_QUERY_BONUS)

        self.logger.info(
            f"Multi-query search with {len(sub_queries)} sub-queries: '{global_query[:60]}...'"
        )

        # Search each sub-query
        results_by_subquery = self.search_batch(
            queries=sub_queries,
            collection_name=collection_name,
            top_k=n_candidates_per_query,
            n_candidates=n_candidates,
            where_filter=where_filter,
            embedding_weight=embedding_weight,
            lexical_weight=lexical_weight,
            hybrid_weight_final=hybrid_weight_final,
            rerank_weight_final=rerank_weight_final,
            rerank_model=rerank_model,
            rerank_batch_size=rerank_batch_size,
            normalize=normalize,
            min_score_threshold=min_score_threshold,
            use_reranking=use_reranking,
        )

        # Merge results by document ID
        merged = {}
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
            self.logger.warning("No results found across all sub-queries")
            return []

        # Aggregate scores and apply consensus bonus
        final_results = []
        for doc_id, entry in merged.items():
            scores = list(entry["per_query_scores"].values())
            matched_queries = list(entry["per_query_scores"].keys())

            base_score = aggregate_scores(scores, merge_strategy)
            consensus_bonus = min(
                multi_query_bonus * (len(matched_queries) - 1),
                max_multi_query_bonus,
            )
            # NOTE: final_score is clamped to [0, 1] inside
            # MergedHybridResult.__init__ (see bugfix note there), so a
            # base_score already near 1.0 plus a consensus bonus no longer
            # produces scores like 1.0639 (106%).
            final_score = base_score + consensus_bonus

            final_results.append(
                MergedHybridResult(
                    id=doc_id,
                    text=entry["text"],
                    metadata=entry["metadata"],
                    per_query_scores=entry["per_query_scores"],
                    matched_queries=matched_queries,
                    final_score=final_score,
                )
            )

        # Sort and truncate
        final_results.sort(key=lambda r: r.final_score, reverse=True)
        top_results = final_results[:top_k]

        self.logger.info(f"✅ {len(top_results)} fused results for '{global_query[:60]}...'")
        return top_results

    def search_deduplicated(
        self,
        query: str,
        collection_name: str,
        top_k: int = None,
        n_candidates: int = None,
        where_filter: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = None,
        use_reranking: bool = True,
        **kwargs,
    ) -> List[HybridResult]:

        top_k = _coalesce(top_k, self.config.TOP_K)
        n_candidates = _coalesce(n_candidates, self.config.N_CANDIDATES)
        similarity_threshold = _coalesce(similarity_threshold, self.config.SIMILARITY_THRESHOLD)

        # Get more candidates for deduplication
        results = self.search(
            query=query,
            collection_name=collection_name,
            top_k=n_candidates,
            n_candidates=n_candidates * 2,
            where_filter=where_filter,
            use_reranking=use_reranking,
            **kwargs,
        )

        if not results:
            return []

        # Deduplicate
        deduplicated = []
        seen_texts = []

        for result in results:
            clean_text = " ".join(result.text.lower().split())

            is_duplicate = False
            for seen in seen_texts[-5:]:  # Check last 5
                if text_similarity(clean_text, seen) > similarity_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                deduplicated.append(result)
                seen_texts.append(clean_text)

        return deduplicated[:top_k]


# =============================================================================
# REPORT GENERATION
# =============================================================================

class HybridResultReporter:
    """Generate Markdown reports for hybrid search results."""

    @staticmethod
    def render_report(
        collection_name: str,
        query: str,
        results: List[Any],
        score_lines_fn,
        text_len: int = 500,
    ) -> str:
        """Render results as Markdown."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "# 🔍 Recherche Hybride (Embedding + Lexical) avec Reranking",
            "",
            f"**Collection:** `{collection_name}`",
            f"**Requête:** {query}",
            f"**Date:** {now}",
            f"**Nombre de résultats:** {len(results)}",
            "",
            "## 📊 Statistiques",
            "",
        ]

        if results:
            scores = [r.final_score for r in results if r.final_score is not None]
            if scores:
                lines.extend([
                    f"- **Score moyen:** {sum(scores) / len(scores):.4f}",
                    f"- **Score maximum:** {max(scores):.4f}",
                    f"- **Score minimum:** {min(scores):.4f}",
                ])

        lines.extend([
            "",
            "---",
            "",
            "## 📄 Résultats Détaillés",
            "",
        ])

        for i, result in enumerate(results, 1):
            # BUGFIX: clamp score_pct to [0, 100] defensively as a second
            # line of defense even though final_score is now clamped upstream.
            score_pct = int(max(0.0, min(result.final_score or 0.0, 1.0)) * 100)
            bar = "█" * min(score_pct // 5, 20) + "░" * max(20 - score_pct // 5, 0)

            lines.extend([
                f"### Résultat {i}",
                "",
                f"**ID:** `{result.id}`",
                "",
                f"**Score:** `{result.final_score:.4f}`  `{score_pct}%`  `[{bar}]`",
                "",
                "**Scores:**",
            ])
            lines.extend(score_lines_fn(result))
            lines.extend([
                "",
                "**Texte:**",
                "",
                f"> {result.text[:text_len]}...",
                "",
                "**Métadonnées:**",
                "",
            ])

            if result.metadata:
                lines.append("| Clé | Valeur |")
                lines.append("|-----|-------|")
                for key, value in list(result.metadata.items())[:8]:
                    lines.append(f"| {key} | {value} |")

            lines.extend([
                "",
                "---",
                "",
            ])

        return "\n".join(lines)

    @staticmethod
    def hybrid_result_scores(result: HybridResult) -> List[str]:
        """Score lines for HybridResult."""
        return [
            f"- Embedding: `{result.embedding_score:.4f}`",
            f"- Lexical: `{result.lexical_score:.4f}`",
            f"- Hybride (pré-rerank): `{result.hybrid_score:.4f}`",
            f"- Rerank: `{result.rerank_score if result.rerank_score is not None else 'N/A'}`",
        ]

    @staticmethod
    def merged_result_scores(result: MergedHybridResult) -> List[str]:
        """Score lines for MergedHybridResult."""
        lines = [
            f"- {sq}: `{sc:.4f}`"
            for sq, sc in result.per_query_scores.items()
        ]
        lines.append(f"- Consensus (sous-requêtes): `{result.query_count}`")
        return lines

    @staticmethod
    def save_results(
        results: List[Any],
        query: str,
        output_path: str,
        collection_name: str = "",
        is_merged: bool = False,
    ) -> None:
        """Save results to Markdown file."""
        if is_merged:
            score_fn = HybridResultReporter.merged_result_scores
        else:
            score_fn = HybridResultReporter.hybrid_result_scores

        content = HybridResultReporter.render_report(
            collection_name, query, results, score_fn
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ Results saved to: {output_path}")

    @staticmethod
    def save_batch_results(
        results_by_query: Dict[str, List[HybridResult]],
        output_path: str,
        collection_name: str = "",
    ) -> None:
        """Save batch results to Markdown file."""
        reports = []
        for query, results in results_by_query.items():
            report = HybridResultReporter.render_report(
                collection_name, query, results,
                HybridResultReporter.hybrid_result_scores
            )
            reports.append(report)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(reports))

        print(f"✅ Batch results saved to: {output_path}")


# =============================================================================
# DEMO / MAIN
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    chroma = ChromaManager(persist_directory="data/chromadb")
    retriever = HybridRetriever(chroma, logger=logger)
    config = HybridSearchConfig()
    reporter = HybridResultReporter()

    collection = "hotellerie_saas"

    # ========================================================================
    # TEST 1: Single Query Search
    # ========================================================================
    print("\n" + "=" * 70)
    print("🧪 TEST 1: Recherche Hybride - Requête Unique")
    print("=" * 70)

    query_single = "quelles sont les differences entre cloud_beds et  Mews ?"

    results_single = retriever.search(
        query=query_single,
        collection_name=collection,
        top_k=20,
        n_candidates=50,
        use_reranking=True,
    )

    print(f"\n✅ {len(results_single)} résultats trouvés\n")
    for i, r in enumerate(results_single[:3], 1):
        print(f"{i}. Score: {r.final_score:.4f}")
        print(f"   {r.text[:100]}...")

    reporter.save_results(
        results=results_single,
        query=query_single,
        output_path="data/searching/hybrid_single_query.md",
        collection_name=collection,
        is_merged=False,
    )

    # # ========================================================================
    # # TEST 2: Batch Search
    # # ========================================================================
    # print("\n" + "=" * 70)
    # print("🧪 TEST 2: Recherche Hybride - Batch")
    # print("=" * 70)

    # batch_queries = [
    #     "quelles sont les différences entre les PMS SaaS pour les hôtels indépendants en France (CloudBeds, Mews, HotelFriend ....) ?",
    #     "taille du marché SaaS PMS hôtellerie France 2024",
    #     "croissance CAGR PMS SaaS hôtels indépendants France 2020-2028",
    #     "segmentation du marché des PMS cloud par taille d'hôtel",
    #     "impact des régulations sur l'adoption du cloud hôtelier",
    # ]

    # results_batch = retriever.search_batch(
    #     queries=batch_queries,
    #     collection_name=collection,
    #     top_k=10,
    #     n_candidates=50,
    #     use_reranking=True,
    # )

    # for q, res in results_batch.items():
    #     print(f"\n📝 {q[:60]}...")
    #     if res:
    #         print(f"   -> {len(res)} résultats, meilleur score: {res[0].final_score:.4f}")
    #     else:
    #         print("   -> 0 résultat")

    # reporter.save_batch_results(
    #     results_by_query=results_batch,
    #     output_path="data/search_results/hybrid_batch_results.md",
    #     collection_name=collection,
    # )

    # # ========================================================================
    # # TEST 3: Multi-Query Fusion
    # # ========================================================================
    # print("\n" + "=" * 70)
    # print("🧪 TEST 3: Recherche Hybride - Multi-Requêtes Fusionnées")
    # print("=" * 70)

    # sub_queries = [
    #     "En 2024, le marché des PMS SaaS pour les hôtels indépendants en France "
    #     "s'est étendu, avec une croissance soutenue et une part de marché dominée "
    #     "par des fournisseurs cloud comme Mews et Cloudbeds.",

    #     "A PMS cloud is ideal for small to medium-sized hotel chains in France "
    #     "with 10 to 200 rooms, offering streamlined operations.",

    #     "Independent hoteliers in France are increasingly adopting dynamic "
    #     "pricing SaaS PMS to optimize revenue.",

    #     "Independent hotel directors in France often face pain points like "
    #     "manual processes and lack of real-time data."
    # ]

    # global_query = "comment est la demande actuelle et les segments de clientèle pour le marché PMS SaaS hôtels indépendants?"

    # results_multi = retriever.search_multi_query(
    #     sub_queries=sub_queries,
    #     global_query=global_query,
    #     collection_name=collection,
    #     top_k=20,
    #     n_candidates_per_query=30,
    #     n_candidates=50,
    #     merge_strategy="max",
    #     multi_query_bonus=0.05,
    #     use_reranking=True,
    # )

    # print(f"\n✅ {len(results_multi)} résultats fusionnés\n")
    # for i, r in enumerate(results_multi[:5], 1):
    #     print(f"{i}. Score: {r.final_score:.4f} (retrouvé par {r.query_count} sous-requêtes)")
    #     print(f"   {r.text[:100]}...")

    # reporter.save_results(
    #     results=results_multi,
    #     query=global_query,
    #     output_path="data/search_results/hybrid_multi_query_results.md",
    #     collection_name=collection,
    #     is_merged=True,
    # )

    # print("\n" + "=" * 70)
    # print("✅ Tous les tests terminés avec succès!")
    # print("=" * 70)