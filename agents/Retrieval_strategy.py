"""
Configuration de la stratégie de récupération (retrieval).

Centralise les paramètres par défaut des méthodes de récupération
supportées (M1 à M4c) et permet de les surcharger via des kwargs.
"""

from typing import Any, Dict, Literal, Optional


class RetrievalStrategy:
    """Configuration pour une stratégie de récupération donnée."""

    # Identifiants de méthode
    M1 = "M1"
    M2 = "M2"
    M3A = "M3a"
    M3B = "M3b"
    M4A = "M4a"
    M4B = "M4b"
    M4C = "M4c"

    # Anciens identifiants pour compatibilité
    HYBRID = "hybrid"
    VECTOR = "vector"

    # Mapping ancien -> nouveau
    LEGACY_MAP = {
        HYBRID: M4A,
        VECTOR: M1,
    }

    # Paramètres par défaut par méthode
    METHOD_CONFIG: Dict[str, Dict[str, Any]] = {
        M1: {
            "n_results": 30,
            "top_k": 20,
            "use_reranking": True,
            "min_score_threshold": 0.0,
        },
        M2: {
            "top_k": 20,
            "n_candidates": 50,
            "embedding_weight": 0.5,
            "lexical_weight": 0.5,
            "hybrid_weight_final": 0.3,
            "rerank_weight_final": 0.7,
            "use_reranking": True,
            "min_score_threshold": 0.0,
        },
        M3A: {
            "n_results": 30,
            "top_k": 20,
            "use_reranking": True,
            "min_score_threshold": 0.0,
            "hyde_temperature": 0.4,
        },
        M3B: {
            "n_results": 30,
            "top_k": 20,
            "final_top_k": 20,
            "use_reranking": True,
            "min_score_threshold": 0.0,
        },
        M4A: {
            "top_k": 20,
            "n_candidates_per_query": 30,
            "n_candidates": 50,
            "embedding_weight": 0.5,
            "lexical_weight": 0.5,
            "hybrid_weight_final": 0.3,
            "rerank_weight_final": 0.7,
            "use_reranking": True,
            "min_score_threshold": 0.0,
            "merge_strategy": "max",
            "multi_query_bonus": 0.05,
        },
        M4B: {
            "top_k": 20,
            "n_candidates": 50,
            "embedding_weight": 0.5,
            "lexical_weight": 0.5,
            "hybrid_weight_final": 0.3,
            "rerank_weight_final": 0.7,
            "use_reranking": True,
            "min_score_threshold": 0.0,
            "hyde_temperature": 0.4,
        },
        M4C: {
            "top_k": 20,
            "n_candidates_per_query": 30,
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
        },
    }

    def __init__(
        self,
        strategy: Literal["hybrid", "vector", "M1", "M2", "M3a", "M3b", "M4a", "M4b", "M4c"] = "hybrid",
        **kwargs: Any,
    ):
        """
        Args:
            strategy: méthode de récupération (M1-M4c) ou alias legacy.
            **kwargs: paramètres additionnels qui surchargent la config par défaut.
        """
        normalized = str(strategy).strip()
        # Resolve legacy aliases (case-insensitive)
        for legacy_key, new_val in self.LEGACY_MAP.items():
            if normalized.lower() == legacy_key.lower():
                normalized = new_val
                break
        # Case-insensitive match against METHOD_CONFIG keys
        for key in self.METHOD_CONFIG:
            if normalized.lower() == key.lower():
                self.strategy = key
                break
        else:
            raise ValueError(
                f"Méthode de récupération inconnue: '{strategy}'. "
                f"Valeurs autorisées: {list(self.METHOD_CONFIG.keys())}"
            )
        self.params = kwargs

    def get_params(self) -> Dict[str, Any]:
        """Retourne la configuration fusionnée (défauts + surcharges)."""
        base_config = dict(self.METHOD_CONFIG.get(self.strategy, {}))
        return {**base_config, **self.params}



