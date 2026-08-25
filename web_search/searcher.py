"""
Web Search Engine
=================
Moteur de recherche web utilisant Tavily API avec filtrage, scoring et déduplication.
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from tavily import TavilyClient


from web_search.utils import (
    calculate_comprehensive_score,
    calculate_french_context_score,
    calculate_reliability_score,
    is_duplicate_url,
    save_search_results,
)

from clients import APIClients
logger = logging.getLogger(__name__)


class WebSearchEngine:
    """Moteur de recherche web utilisant Tavily API avec filtrage et ranking."""

    def __init__(self,client) -> None:
        self.client = client
        self._seen_urls: set = set()
        self._all_unique_results: List[Dict[str, Any]] = []

    def reset_url_cache(self) -> None:
        """Reinitialise le cache d'URLs."""
        self._seen_urls.clear()
        self._all_unique_results.clear()
        print("cache d'urls irenitialisé")

    def filter_and_rank_results(
        self, results: List[Dict[str, Any]]
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Filtre et rank les résultats de recherche avec déduplication des URLs."""
        ranked_results = []

        for result in results:
            url = result.get("url", "")

            if is_duplicate_url(url, self._seen_urls):
                print(f"  - URL dupliquée ignorée: {url[:80]}...")
                continue

            score = calculate_comprehensive_score(result)

            if score >= 0.4:
                ranked_results.append((result, score))

        ranked_results.sort(key=lambda x: x[1], reverse=True)
        return ranked_results

    def search_query(
        self, query: str, angle: str, max_results: int = 5
    ) -> Dict[str, Any]:
        """Exécute une recherche via Tavily et retourne les résultats classés."""
        print(f"recherche: {query}")

        try:
            response = self.client.search(
                query=query,
                include_answer="basic",
                search_depth="advanced",
                max_results=max_results,
            )

            results = {
                "answer": response.get("answer", ""),
                "results": response.get("results", []),
            }

            if not results:
                print("Aucun résultat trouvé pour la requête.")
                return {
                    "query": query,
                    "results": [],
                    "answer": "",
                    "duplicates_filtered": 0,
                }

            ranked_results = self.filter_and_rank_results(results["results"])
            duplicates_filtered = len(results["results"]) - len(ranked_results)

            top_results = ranked_results[:max_results]

            search_result = []
            for res, score in top_results:
                search_result.append(
                    {
                        "url": res.get("url", ""),
                        "title": res.get("title", ""),
                        "content": res.get("content", ""),
                        "score": score,
                        "tavily_score": res.get("score", 0),
                        "french_context_score": calculate_french_context_score(
                            res.get("url", ""),
                            res.get("title", ""),
                            res.get("content", ""),
                        ),
                        "reliability_score": calculate_reliability_score(
                            res.get("url", "")
                        ),
                        "final_score": calculate_comprehensive_score(res),
                    }
                )

            result_summary = {
                "query": query,
                "answer": results.get("answer", ""),
                "angle": angle,
                "results": search_result,
            }
            return result_summary

        except Exception as e:
            print(f"Erreur lors de la recherche pour la requête '{query}': {e}")
            return {
                "query": query,
                "error": str(e),
                "total_found": 0,
                "relevant_found": 0,
                "duplicates_filtered": 0,
                "results": [],
            }

    def search_batch(
        self, all_output: Dict[str, Any], max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Effectue une recherche pour un lot de requêtes en respectant la structure JSON imbriquée."""
        self.reset_url_cache()

        batch_results = {}

        for part, part_data in all_output.items():
            batch_results[part] = {
                "section": part_data["section"],
                "questions": [],
            }

            if not part_data:
                continue

            question_queries = part_data.get("question_queries", [])

            for qq in question_queries:
                question_text = qq.get("question", "")
                question_result = {
                    "question": question_text,
                    "queries": [],
                }

                queries_list = qq.get("queries", [])

                for q_data in queries_list:
                    query_text = q_data.get("query", "")
                    angle_text = q_data.get("angle", "")

                    if query_text:
                        result = self.search_query(query_text, angle_text, max_results)
                        question_result["queries"].append(result)

                batch_results[part]["questions"].append(question_result)

        if batch_results:
            save_search_results(batch_results)

        return batch_results


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    search_engine = WebSearchEngine(client=APIClients().tavily_client)

    with open("outputs/global_output.json", "r", encoding="utf-8") as fichier:
        donnees = json.load(fichier)

    batch_results = search_engine.search_batch(donnees, max_results=3)
