"""
Vector Retrieval Module
Provides document retrieval using ChromaDB vector search with optional cross-encoder reranking
"""

import json
import logging
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

import numpy as np

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = lambda x, **kwargs: x

from embedding.chroma_manager import ChromaManager
from chunking.utils import save_results_to_markdown


# =============================================================================
# CONFIGURATION
# =============================================================================

class VectorRetrievalConfig:
    """Configuration for vector retrieval operations."""
    
    # Default search parameters
    N_RESULTS = 30
    TOP_K = 20
    
    # Score weights for final scoring
    VECTOR_WEIGHT_FINAL = 0.3
    RERANK_WEIGHT_FINAL = 0.7
    
    # Reranking
    RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    # Thresholds
    MIN_SCORE_THRESHOLD = 0.0
    
    # Cache
    USE_CACHE = True
    MAX_CACHE_SIZE = 100


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_scores(values: Any) -> np.ndarray:
    """
    Normalize scores to [0, 1] range using min-max normalization.
    
    Args:
        values: Array-like of scores to normalize
        
    Returns:
        Normalized scores as numpy array
    """
    values = np.asarray(values, dtype=np.float32)
    min_val = values.min()
    max_val = values.max()
    
    if max_val > min_val:
        normalized = (values - min_val) / (max_val - min_val)
    else:
        normalized = np.ones_like(values)
    
    return normalized


def format_chunks(chunks: List[str]) -> str:
    """
    Format chunks with numbered references for LLM citation.
    
    Args:
        chunks: List of text chunks to format
        
    Returns:
        Formatted string with numbered chunks
    """
    if not chunks:
        return "Aucun extrait de document fourni."
    
    blocs = [
        f"[Extrait {i}]\n{chunk.strip()}"
        for i, chunk in enumerate(chunks, start=1)
    ]
    return "\n\n".join(blocs)


# =============================================================================
# RESULT CLASSES
# =============================================================================

@dataclass
class RetrievalResult:
    """Single retrieval result with scores."""
    
    id: str
    text: str
    metadata: Dict[str, Any]
    vector_score: float
    rerank_score: Optional[float] = None
    final_score: Optional[float] = None
    
    def __post_init__(self):
        """Set final score if not provided."""
        if self.final_score is None:
            self.final_score = self.vector_score
    
    @property
    def score(self) -> float:
        """Return the final score."""
        return self.final_score if self.final_score is not None else self.vector_score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "vector_score": float(self.vector_score),
            "rerank_score": float(self.rerank_score) if self.rerank_score is not None else None,
            "final_score": float(self.final_score) if self.final_score is not None else None,
        }


@dataclass
class RetrievalResponse:
    """Complete retrieval response for a query."""
    
    query: str
    results: List[RetrievalResult]
    total_results: int
    retrieval_time: float
    reranking_time: Optional[float] = None
    total_time: float = field(init=False)
    
    def __post_init__(self):
        """Calculate total time."""
        self.total_time = self.retrieval_time + (self.reranking_time or 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query": self.query,
            "total_results": self.total_results,
            "retrieval_time": self.retrieval_time,
            "reranking_time": self.reranking_time,
            "total_time": self.total_time,
            "results": [r.to_dict() for r in self.results]
        }
    
    def to_markdown(self, collection_name: str = "unknown") -> str:
        """
        Generate a detailed markdown report.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Markdown formatted report
        """
        if not self.results:
            return f"# 🔍 Résultats de Recherche\n\nAucun résultat trouvé pour: **{self.query}**"
        
        scores = [r.score for r in self.results]
        avg_score = np.mean(scores)
        max_score = np.max(scores)
        min_score = np.min(scores)
        std_score = np.std(scores)
        
        lines = [
            "# 🔍 Résultats de Recherche Vectorielle",
            "",
            f"**Collection:** `{collection_name}`",
            f"**Requête:** {self.query}",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Nombre de résultats:** {len(self.results)}",
            "",
            "## 📊 Statistiques",
            "",
            f"- **Score moyen:** {avg_score:.4f}",
            f"- **Score maximum:** {max_score:.4f}",
            f"- **Score minimum:** {min_score:.4f}",
            f"- **Écart-type:** {std_score:.4f}",
            "",
            "---",
            "",
            "## 📄 Résultats Détaillés",
            "",
        ]
        
        for idx, result in enumerate(self.results, start=1):
            score = result.score
            percent = int(score * 100)
            bar_length = 20
            filled = int(score * bar_length)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            lines.extend([
                f"### Résultat {idx}",
                "",
                f"**ID:** `{result.id}`",
                "",
                f"**Score:** `{score:.4f}`  `{percent}%`  `[{bar}]`",
                "",
            ])
            
            # Show individual scores if reranking was used
            if result.rerank_score is not None:
                lines.extend([
                    "**Scores détaillés:**",
                    f"- Vectoriel: `{result.vector_score:.4f}`",
                    f"- Rerank: `{result.rerank_score:.4f}`",
                    "",
                ])
            
            lines.extend([
                "**Texte:**",
                "",
                "> " + result.text.replace("\n", "\n> "),
                "",
            ])
            
            # Metadata
            if result.metadata:
                lines.append("**Métadonnées:**")
                lines.append("")
                lines.append("| Clé | Valeur |")
                lines.append("|-----|-------|")
                
                for key, value in result.metadata.items():
                    if isinstance(value, (list, dict)):
                        value = str(value)
                    value = str(value).replace("\n", " ")
                    lines.append(f"| {key} | {value} |")
                lines.append("")
            
            if "source_url" in result.metadata:
                lines.append(f"**Source:** `{result.metadata['source_url']}`")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_chunks(self) -> List[str]:
        """
        Extract text chunks from results for LLM consumption.
        
        Returns:
            List of text chunks
        """
        return [result.text for result in self.results]


# =============================================================================
# FUSION FUNCTIONS
# =============================================================================

def merge_retrieval_responses(
    responses: Dict[str, RetrievalResponse],
    original_query: str,
    top_k: Optional[int] = None,
) -> RetrievalResponse:
    """
    Merge multiple RetrievalResponse objects into a single RetrievalResponse.
    
    This function:
    1. Aggregates results from all sub-queries
    2. Keeps the highest score for duplicate document IDs
    3. Sorts by score in descending order
    4. Optionally truncates to top_k results
    
    Args:
        responses: Dictionary mapping sub-query to its RetrievalResponse
        original_query: Original user query for the merged response
        top_k: Optional number of final chunks to keep
        
    Returns:
        Merged RetrievalResponse containing consolidated results
    """
    if not responses:
        return RetrievalResponse(
            query=original_query,
            results=[],
            total_results=0,
            retrieval_time=0,
            reranking_time=0
        )
    
    # Track unique results with highest scores
    merged_results = {}
    total_retrieval_time = 0.0
    total_reranking_time = 0.0
    
    # Aggregate all results
    for response in responses.values():
        total_retrieval_time += response.retrieval_time
        total_reranking_time += response.reranking_time or 0.0
        
        for result in response.results:
            if (result.id not in merged_results or 
                result.score > merged_results[result.id].score):
                merged_results[result.id] = result
    
    # Sort by score descending
    sorted_results = sorted(
        merged_results.values(),
        key=lambda x: x.score,
        reverse=True
    )
    
    # Apply top-k truncation if specified
    if top_k is not None:
        sorted_results = sorted_results[:top_k]
    
    return RetrievalResponse(
        query=original_query,
        results=sorted_results,
        total_results=len(sorted_results),
        retrieval_time=total_retrieval_time,
        reranking_time=total_reranking_time
    )


# =============================================================================
# MAIN RETRIEVER CLASS
# =============================================================================

class Retriever:
    """
    Document retriever using ChromaDB vector search with optional reranking.
    
    Features:
        - Vector search using ChromaDB
        - Optional cross-encoder reranking
        - Result caching
        - Batch processing
        - Result fusion for multi-query searches
        - Multiple output formats (Markdown, JSON)
    
    Usage:
        retriever = VectorRetriever(chroma_manager)
        response = retriever.search(
            query="your query",
            collection_name="your_collection",
            top_k=10,
            use_reranking=True
        )
        retriever.save_results(response, "output.md")
    """
    
    def __init__(
        self,
        chroma_manager: ChromaManager,
        config: Optional[VectorRetrievalConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the retriever.
        
        Args:
            chroma_manager: ChromaManager instance
            config: Optional configuration
            logger: Optional logger instance
        """
        self.chroma_manager = chroma_manager
        self.config = config or VectorRetrievalConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize cross-encoder for reranking
        self.reranker = None
        self._init_reranker()
        
        # Cache for retrieved results
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Statistics
        self.stats = {
            "total_retrievals": 0,
            "total_rerankings": 0,
            "average_retrieval_time": 0.0,
            "average_rerank_time": 0.0
        }
        
        self.logger.info(f"VectorRetriever initialized with model: {self.config.RERANK_MODEL}")
    
    # -------------------------------------------------------------------------
    # Reranker Management
    # -------------------------------------------------------------------------
    
    def _init_reranker(self) -> None:
        """Initialize the cross-encoder reranker if available."""
        if not CROSS_ENCODER_AVAILABLE:
            self.logger.warning("CrossEncoder not available. Reranking disabled.")
            return
        
        try:
            self.logger.info(f"Loading reranker model: {self.config.RERANK_MODEL}")
            self.reranker = CrossEncoder(
                self.config.RERANK_MODEL,
                max_length=512
            )
            self.logger.info("Reranker loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load reranker: {e}")
            self.reranker = None
    
    def set_reranker(self, model_name: str) -> bool:
        """
        Change the reranker model.
        
        Args:
            model_name: Name of the reranker model
            
        Returns:
            True if successful, False otherwise
        """
        self.config.RERANK_MODEL = model_name
        self._init_reranker()
        return self.reranker is not None
    
    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------
    
    def _get_cache_key(
        self,
        query: str,
        collection_name: str,
        n_results: int,
        where_filter: Optional[Dict[str, Any]] = None,
        use_reranking: bool = True,
    ) -> str:
        """
        Generate a cache key for a query.
        
        Args:
            query: Search query
            collection_name: Collection name
            n_results: Number of results
            where_filter: Optional filter
            use_reranking: Whether reranking was used
            
        Returns:
            Cache key hash
        """
        key_parts = [
            query.strip(),
            collection_name,
            str(n_results),
            json.dumps(where_filter or {}, sort_keys=True),
            str(use_reranking)
        ]
        key_string = "||".join(key_parts)
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def _manage_cache(self) -> None:
        """Manage cache size to prevent memory issues."""
        if len(self._cache) > self.config.MAX_CACHE_SIZE:
            # Remove oldest entries (FIFO)
            keys_to_remove = list(self._cache.keys())[
                :len(self._cache) - self.config.MAX_CACHE_SIZE
            ]
            for key in keys_to_remove:
                del self._cache[key]
            self.logger.debug(f"Cache trimmed: removed {len(keys_to_remove)} entries")
    
    def clear_cache(self) -> int:
        """
        Clear the result cache.
        
        Returns:
            Number of cache entries cleared
        """
        cache_size = len(self._cache)
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self.logger.info(f"Cache cleared: {cache_size} entries removed")
        return cache_size
    
    # -------------------------------------------------------------------------
    # Core Search Methods
    # -------------------------------------------------------------------------
    
    def _rerank_results(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        """
        Rerank results using cross-encoder.
        
        Args:
            query: Search query
            results: List of retrieval results
            top_k: Number of results to return
            
        Returns:
            Reranked results
        """
        if not self.reranker or not results:
            return results[:top_k]
        
        try:
            # Prepare pairs for cross-encoder
            pairs = [(query, result.text) for result in results]
            
            # Get cross-encoder scores
            rerank_scores = self.reranker.predict(pairs)
            rerank_scores = normalize_scores(rerank_scores)
            
            # Update results with rerank scores
            for result, score in zip(results, rerank_scores):
                result.rerank_score = float(score)
                # Combine vector score and rerank score
                result.final_score = (
                    self.config.VECTOR_WEIGHT_FINAL * result.vector_score +
                    self.config.RERANK_WEIGHT_FINAL * float(score)
                )
            
            # Sort by final score
            results.sort(key=lambda x: x.final_score, reverse=True)
            
            return results[:top_k]
            
        except Exception as e:
            self.logger.error(f"Reranking failed: {e}")
            return results[:top_k]
    
    # -------------------------------------------------------------------------
    # Public Search Methods
    # -------------------------------------------------------------------------
    
    def search(
        self,
        query: str,
        collection_name: str,
        n_results: Optional[int] = None,
        top_k: Optional[int] = None,
        where_filter: Optional[Dict[str, Any]] = None,
        use_reranking: bool = True,
        use_cache: Optional[bool] = False,
        min_score_threshold: Optional[float] = None,
    ) -> RetrievalResponse:
        """
        Perform vector search with optional reranking.
        
        Args:
            query: Search query
            collection_name: ChromaDB collection name
            n_results: Number of initial results from vector search
            top_k: Number of final results
            where_filter: Optional filter
            use_reranking: Whether to use reranking
            use_cache: Whether to use cache
            min_score_threshold: Minimum score threshold
            
        Returns:
            RetrievalResponse with results
        """
        # Use config defaults
        n_results = n_results or self.config.N_RESULTS
        top_k = top_k or self.config.TOP_K
        use_cache = use_cache if use_cache is not None else self.config.USE_CACHE
        min_score_threshold = min_score_threshold or self.config.MIN_SCORE_THRESHOLD
        
        start_time = time.time()
        self.stats["total_retrievals"] += 1
        
        # Check cache
        cache_key = None
        if use_cache:
            cache_key = self._get_cache_key(
                query, collection_name, n_results, where_filter, use_reranking
            )
            if cache_key in self._cache:
                self._cache_hits += 1
                self.logger.debug(f"Cache hit for query: {query[:50]}...")
                cached = self._cache[cache_key]
                
                return RetrievalResponse(
                    query=query,
                    results=[RetrievalResult(**r) for r in cached["results"]],
                    total_results=len(cached["results"]),
                    retrieval_time=time.time() - start_time,
                    reranking_time=cached.get("reranking_time", 0)
                )
            self._cache_misses += 1
        
        # Perform vector search
        retrieval_start = time.time()
        raw_results = self.chroma_manager.search(
            collection_name=collection_name,
            query=query,
            n_results=n_results,
            where_filter=where_filter
        )
        retrieval_time = time.time() - retrieval_start
        
        # Convert to RetrievalResult objects
        results = [
            RetrievalResult(
                id=r["id"],
                text=r["text"],
                metadata=r["metadata"],
                vector_score=r["score"],
                final_score=r["score"]
            )
            for r in raw_results
        ]
        
        # Apply score threshold
        if min_score_threshold > 0:
            results = [r for r in results if r.vector_score >= min_score_threshold]
        
        # Reranking
        reranking_time = 0
        if use_reranking and self.reranker:
            rerank_start = time.time()
            results = self._rerank_results(query, results, top_k)
            reranking_time = time.time() - rerank_start
            self.stats["total_rerankings"] += 1
        else:
            results = results[:top_k]
        
        # Update statistics
        total_time = time.time() - start_time
        self.stats["average_retrieval_time"] = (
            (self.stats["average_retrieval_time"] * (self.stats["total_retrievals"] - 1) + retrieval_time)
            / self.stats["total_retrievals"]
        )
        if reranking_time > 0:
            self.stats["average_rerank_time"] = (
                (self.stats["average_rerank_time"] * (self.stats["total_rerankings"] - 1) + reranking_time)
                / self.stats["total_rerankings"]
            )
        
        # Create response
        response = RetrievalResponse(
            query=query,
            results=results,
            total_results=len(results),
            retrieval_time=retrieval_time,
            reranking_time=reranking_time if use_reranking else None
        )
        
        # Cache results
        if use_cache and cache_key:
            self._cache[cache_key] = {
                "results": [r.to_dict() for r in results],
                "retrieval_time": retrieval_time,
                "reranking_time": reranking_time if use_reranking else 0
            }
            self._manage_cache()
        
        self.logger.info(
            f"Retrieval complete: {len(results)} results in {total_time:.3f}s "
            f"(retrieval: {retrieval_time:.3f}s, reranking: {reranking_time:.3f}s)"
        )
        
        return response
    
    def search_batch(
        self,
        queries: List[str],
        collection_name: str,
        n_results: Optional[int] = None,
        top_k: Optional[int] = None,
        where_filter: Optional[Dict[str, Any]] = None,
        use_reranking: bool = True,
        use_cache: Optional[bool] = None,
        min_score_threshold: Optional[float] = None,
        show_progress: bool = True,
    ) -> Dict[str, RetrievalResponse]:
        """
        Perform vector search for multiple queries.
        
        Args:
            queries: List of search queries
            collection_name: ChromaDB collection name
            n_results: Number of initial results from vector search
            top_k: Number of final results
            where_filter: Optional filter
            use_reranking: Whether to use reranking
            use_cache: Whether to use cache
            min_score_threshold: Minimum score threshold
            show_progress: Whether to show progress bar
            
        Returns:
            Dictionary mapping query to RetrievalResponse
        """
        results = {}
        
        iterator = tqdm(queries, desc="Retrieving", unit="query") if show_progress else queries
        
        for query in iterator:
            try:
                response = self.search(
                    query=query,
                    collection_name=collection_name,
                    n_results=n_results,
                    top_k=top_k,
                    where_filter=where_filter,
                    use_reranking=use_reranking,
                    use_cache=use_cache,
                    min_score_threshold=min_score_threshold,
                )
                results[query] = response
            except Exception as e:
                self.logger.error(f"Error retrieving for query '{query[:50]}...': {e}")
                results[query] = RetrievalResponse(
                    query=query,
                    results=[],
                    total_results=0,
                    retrieval_time=0,
                    reranking_time=0
                )
        
        return results
    
    def search_with_fusion(
        self,
        sub_queries: List[str],
        original_query: str,
        collection_name: str,
        n_results: Optional[int] = None,
        top_k: Optional[int] = None,
        final_top_k: Optional[int] = None,
        where_filter: Optional[Dict[str, Any]] = None,
        use_reranking: bool = True,
        use_cache: Optional[bool] = None,
        min_score_threshold: Optional[float] = None,
        show_progress: bool = True,
    ) -> RetrievalResponse:
        """
        Perform multi-query search with result fusion.
        
        This method:
        1. Searches for each sub-query individually
        2. Merges results from all sub-queries
        3. Returns a single fused response
        
        Args:
            sub_queries: List of sub-queries to search
            original_query: Original query for the fused response
            collection_name: ChromaDB collection name
            n_results: Number of initial results from vector search per query
            top_k: Number of final results per query before fusion
            final_top_k: Number of final fused results
            where_filter: Optional filter
            use_reranking: Whether to use reranking
            use_cache: Whether to use cache
            min_score_threshold: Minimum score threshold
            show_progress: Whether to show progress bar
            
        Returns:
            Fused RetrievalResponse
        """
        if not sub_queries:
            return RetrievalResponse(
                query=original_query,
                results=[],
                total_results=0,
                retrieval_time=0,
                reranking_time=0
            )
        
        # Use config defaults
        final_top_k = final_top_k or top_k or self.config.TOP_K
        
        # Perform batch search
        responses = self.search_batch(
            queries=sub_queries,
            collection_name=collection_name,
            n_results=n_results,
            top_k=top_k,
            where_filter=where_filter,
            use_reranking=use_reranking,
            use_cache=use_cache,
            min_score_threshold=min_score_threshold,
            show_progress=show_progress,
        )
        
        # Merge results
        fused_response = merge_retrieval_responses(
            responses=responses,
            original_query=original_query,
            top_k=final_top_k
        )
        
        self.logger.info(
            f"Fusion complete: {len(responses)} queries merged into "
            f"{fused_response.total_results} results"
        )
        
        return fused_response
    
    # -------------------------------------------------------------------------
    # Save Methods
    # -------------------------------------------------------------------------
    
    def save_results(
        self,
        response: RetrievalResponse,
        output_path: Union[str, Path],
        collection_name: str = "",
        format: str = "markdown",
    ) -> Path:
        """
        Save retrieval results to file.
        
        Args:
            response: RetrievalResponse to save
            output_path: Output file path
            collection_name: Collection name for metadata
            format: Output format ('markdown', 'json', 'both', 'legacy')
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        
        # Save as markdown
        if format in ["markdown", "both"]:
            md_path = output_path.with_suffix(".md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(response.to_markdown(collection_name))
            saved_files.append(md_path)
            self.logger.info(f"Results saved to markdown: {md_path}")
        
        # Save as JSON
        if format in ["json", "both"]:
            json_path = output_path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)
            saved_files.append(json_path)
            self.logger.info(f"Results saved to JSON: {json_path}")
        
        # Save using legacy function
        if format == "legacy":
            legacy_path = save_results_to_markdown(
                results=[r.to_dict() for r in response.results],
                query=response.query,
                collection_name=collection_name,
                output_file=str(output_path)
            )
            saved_files.append(legacy_path)
        
        return saved_files[0] if saved_files else output_path
    
    def save_batch_results(
        self,
        responses: Dict[str, RetrievalResponse],
        output_dir: Union[str, Path],
        collection_name: str = "",
        format: str = "markdown",
    ) -> List[Path]:
        """
        Save batch retrieval results to files.
        
        Args:
            responses: Dictionary mapping query to RetrievalResponse
            output_dir: Output directory
            collection_name: Collection name for metadata
            format: Output format
            
        Returns:
            List of saved file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        
        for query, response in responses.items():
            # Create safe filename from query
            safe_name = "".join(c for c in query[:50] if c.isalnum() or c in " _-").strip()
            if not safe_name:
                safe_name = f"query_{len(saved_files)}"
            
            file_path = output_dir / safe_name
            saved = self.save_results(
                response=response,
                output_path=file_path,
                collection_name=collection_name,
                format=format,
            )
            saved_files.append(saved)
        
        # Also save a combined report
        combined_path = output_dir / "_combined_results.md"
        combined_content = "\n\n---\n\n".join([
            r.to_markdown(collection_name)
            for r in responses.values()
        ])
        with open(combined_path, "w", encoding="utf-8") as f:
            f.write("# Combined Retrieval Results\n\n")
            f.write(combined_content)
        saved_files.append(combined_path)
        
        self.logger.info(f"Saved {len(responses)} batch results to {output_dir}")
        return saved_files
    
    def save_fusion_results(
        self,
        fused_response: RetrievalResponse,
        sub_queries: List[str],
        output_path: Union[str, Path],
        collection_name: str = "",
        format: str = "markdown",
    ) -> Path:
        """
        Save fused retrieval results with additional metadata.
        
        Args:
            fused_response: Fused RetrievalResponse
            sub_queries: List of sub-queries used for fusion
            output_path: Output file path
            collection_name: Collection name for metadata
            format: Output format
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate markdown with fusion info
        if format in ["markdown", "both"]:
            md_path = output_path.with_suffix(".md")
            
            # Custom markdown with fusion info
            content = [
                "# 🔍 Résultats Fusionnés",
                "",
                f"**Collection:** `{collection_name}`",
                f"**Requête globale:** {fused_response.query}",
                f"**Sous-requêtes:** {len(sub_queries)}",
                f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Nombre de résultats:** {fused_response.total_results}",
                "",
                "## 📋 Sous-requêtes",
                "",
            ]
            
            for i, q in enumerate(sub_queries, 1):
                content.append(f"{i}. {q[:100]}...")
                if len(q) > 100:
                    content.append(f"   {q[100:]}...")
            
            content.extend([
                "",
                "---",
                "",
                fused_response.to_markdown(collection_name)
            ])
            
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
            
            saved_files = [md_path]
            self.logger.info(f"Fusion results saved to markdown: {md_path}")
            
            # Also save JSON
            if format in ["json", "both"]:
                json_path = output_path.with_suffix(".json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "original_query": fused_response.query,
                        "sub_queries": sub_queries,
                        "total_sub_queries": len(sub_queries),
                        "results": fused_response.to_dict()
                    }, f, ensure_ascii=False, indent=2)
                saved_files.append(json_path)
                self.logger.info(f"Results saved to JSON: {json_path}")
            
            return saved_files[0]
        
        # Fallback to regular save
        return self.save_results(
            response=fused_response,
            output_path=output_path,
            collection_name=collection_name,
            format=format,
        )
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get retriever statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            **self.stats,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "reranker_available": self.reranker is not None,
            "rerank_model": self.config.RERANK_MODEL,
        }


# =============================================================================
# DEMO / MAIN
# =============================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    
    # Initialize
    chroma = ChromaManager(persist_directory="data/chromadb")
    config = VectorRetrievalConfig()
    retriever = Retriever(chroma, config, logger)
    
    collection = "hotellerie_saas"
    
    # Define sub-queries for HyDE-style search
    sub_queries = [
        "En 2024, le marché des PMS SaaS pour les hôtels indépendants en France "
        "s'est étendu, avec une croissance soutenue et une part de marché dominée "
        "par des fournisseurs cloud comme Mews et Cloudbeds. Les PMS SaaS ont permis "
        "une flexibilité accrue et une meilleure gestion des opérations pour les "
        "hôtels indépendants. Le marché a atteint environ 1,68 milliard USD en 2025.",
        
        "A PMS cloud is ideal for small to medium-sized hotel chains in France "
        "with 10 to 200 rooms, offering streamlined operations and enhanced guest "
        "experience. HotelFriend and Mews are recommended solutions. These systems "
        "provide essential features like booking engines and channel management.",
        
        "Independent hoteliers in France are increasingly adopting dynamic pricing "
        "SaaS PMS to optimize revenue and streamline pricing adjustments. These "
        "systems integrate with existing PMS, automate pricing rules, and enhance "
        "revenue management. Studies show a 15-30% revenue increase compared to "
        "static pricing.",
        
        "Independent hotel directors in France often face pain points like manual "
        "processes and lack of real-time data; they need PMS with strong integration "
        "and multilingual support. Essential PMS features include real-time inventory "
        "management and revenue optimization tools. A well-chosen PMS can significantly "
        "reduce administrative tasks and improve guest satisfaction."
    ]
    
    original_query = [
        "quelles sont les differeances entre les PMS SaaS pour les hôtels indépendants en France(cloud_beds , Mews, HotelFriend ....) ?",
    ]
    
    # ========================================================================
    # TEST 1: Batch Search (Individual Results)
    # ========================================================================
    print("\n" + "=" * 70)
    print("🧪 TEST 1: Recherche Vectorielle - Batch (Résultats Individuels)")
    print("=" * 70)
    
    responses = retriever.search_batch(
        queries=original_query,
        collection_name=collection,
        n_results=30,
        top_k=20,
        use_reranking=True,
        show_progress=True,
    )
    
    # Save individual results
    for query, response in responses.items():
        safe_name = "".join(c for c in query[:20] if c.isalnum() or c in " _-").strip()
        if not safe_name:
            safe_name = "query"
        
        output_file = retriever.save_results(
            response=response,
            output_path=f"data/searching/{safe_name}",
            collection_name=collection,
            format="markdown",
        )
        print(f"💾 Results saved to: {output_file}")
    
    # # ========================================================================
    # # TEST 2: Fusion Search (Merged Results)
    # # ========================================================================
    # print("\n" + "=" * 70)
    # print("🧪 TEST 2: Recherche Vectorielle - Fusion des Résultats")
    # print("=" * 70)
    
    # fused_response = retriever.search_with_fusion(
    #     sub_queries=sub_queries,
    #     original_query=original_query,
    #     collection_name=collection,
    #     n_results=30,
    #     top_k=20,
    #     final_top_k=20,
    #     use_reranking=True,
    #     show_progress=True,
    # )
    
    # print(f"\n✅ Résultats fusionnés: {fused_response.total_results} documents")
    # print(f"   Temps total: {fused_response.total_time:.3f}s")
    # print(f"   Requêtes fusionnées: {len(sub_queries)}")
    
    # # Show top fused results
    # print("\n📊 Top résultats fusionnés:")
    # for i, r in enumerate(fused_response.results[:5], 1):
    #     print(f"{i}. Score: {r.score:.4f}")
    #     print(f"   {r.text[:100]}...")
    
    # # Save fused results with metadata
    # output_file = retriever.save_fusion_results(
    #     fused_response=fused_response,
    #     sub_queries=sub_queries,
    #     output_path="data/searching/fused_demande_hyde",
    #     collection_name=collection,
    #     format="markdown",
    # )
    # print(f"\n💾 Fused results saved to: {output_file}")
    
    # # ========================================================================
    # # TEST 3: Statistics
    # # ========================================================================
    # print("\n" + "=" * 70)
    # print("📊 Statistiques du Retriever")
    # print("=" * 70)
    
    # stats = retriever.get_stats()
    # for key, value in stats.items():
    #     print(f"   {key}: {value}")
    
    # print("\n✅ Tous les tests terminés avec succès!")