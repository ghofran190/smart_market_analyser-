


import os
import re
import time
import json
import uuid
from pathlib import Path
from datetime import datetime, UTC
from urllib.parse import urlparse, quote
from typing import List, Dict, Optional, Tuple
from firecrawl import FirecrawlApp
from utils.logger import get_logger
from scraping_cleaning.models import ScrapingStats
from clients import APIClients
import random


logger = get_logger(__name__)


class FirecrawlMarkdownCollector:
    """Collecteur de contenu Markdown via Firecrawl avec gestion robuste des erreurs."""

    def __init__(self, client:FirecrawlApp, max_retries: int = 3, timeout: int = 60000  ):
        """
        Initialise le collecteur Firecrawl.

        Args:
            api_key: Clé API Firecrawl
            max_retries: Nombre maximum de tentatives par URL
            timeout: Timeout en secondes pour chaque requête
        """
        self.app = client
        self.max_retries = max_retries
        self.timeout = timeout
        self.output_dir = "outputs"
        self.failed_urls_log = []  # Pour tracer les URLs échouées
        logger.info("Firecrawl initialisé avec max_retries=%d, timeout=%d", max_retries, timeout)

    def _clean_url(self, url: str) -> str:
        """
        Nettoie et encode une URL.

        Args:
            url: URL à nettoyer

        Returns:
            URL nettoyée
        """
        try:
            parsed = urlparse(url)
            # Encode le chemin et les paramètres
            path = quote(parsed.path, safe='/:')
            query = quote(parsed.query, safe='=&')
            clean_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            if query:
                clean_url += f"?{query}"
            return clean_url
        except Exception as e:
            logger.warning("Impossible de nettoyer l'URL %s: %s", url, e)
            return url

    def load_urls(self, search_result: dict) -> Tuple[List[Dict], List[Dict]]:
        """
        Extrait les URLs et réponses des résultats de recherche.

        Args:
            search_result: Dictionnaire des résultats de recherche

        Returns:
            Tuple (liste des URLs avec métadonnées, liste des réponses)
        """
        logger.info("Extraction des URLs depuis les résultats de recherche...")
        urls = []
        answers = []

        for part, part_data in search_result.items():
            section = part_data.get("section", "")
            questions = part_data.get("questions", [])
            for q in questions:
                question = q.get("question", "")
                queries = q.get("queries", [])
                for query in queries:
                    answers.append({
                        "query": query.get("query", ""),
                        "answer": query.get("answer", "")
                    })
                    angle = query.get("angle", "")
                    for link in query.get("results", []):
                        url = link.get("url", "")
                        # Nettoyer l'URL immédiatement
                        clean_url = self._clean_url(url)
                        urls.append({
                            "url": clean_url,
                            "original_url": url,  # Garder l'original pour référence
                            "title": link.get("title", ""),
                            "section": section,
                            "query": query.get("query", ""),
                            "angle": angle,
                            "question": question
                        })

        logger.info("Extraction terminée : %d URLs, %d réponses.", len(urls), len(answers))
        if urls:
            logger.debug("Première URL : %s", urls[0]["url"])
        return urls, answers

    def save_markdown(self, url_data: dict, markdown: str, success: bool = True) -> str:
        """
        Sauvegarde le contenu markdown dans un fichier.

        Args:
            url_data: Données de l'URL
            markdown: Contenu markdown
            success: Indique si le scraping a réussi

        Returns:
            Chemin du fichier sauvegardé
        """
        url = url_data.get("original_url", url_data["url"])
        url_clean = "".join(c if c.isalnum() else "_" for c in url)[:60]
        unique_id = uuid.uuid4().hex[:8]
        status = "success" if success else "failed"
        filename = f"{url_clean}_{unique_id}_{status}.md"

        out_path = Path(self.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        filepath = out_path / filename
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info("Markdown sauvegardé : %s", filepath)
            return str(filepath)
        except Exception as e:
            logger.exception("Impossible de sauvegarder %s", url)
            raise

    def _scrape_with_retry(self, url_data: Dict) -> Dict:
        """
        Scrape une URL avec système de retry et backoff exponentiel.

        Args:
            url_data: Données de l'URL

        Returns:
            Résultat du scraping avec métadonnées
        """
        url = url_data["url"]
        start = time.time()
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("Tentative %d/%d pour %s", attempt, self.max_retries, url)

                # Ajouter un petit délai aléatoire pour éviter de frapper trop fort
                if attempt > 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.debug("Attente de %.2fs avant tentative %d", wait_time, attempt)
                    time.sleep(wait_time)

                # Scraping avec timeout explicite
                result = self.app.scrape(
                    url,
                    formats=["markdown"],
                    timeout=self.timeout
                )

                # Extraction du markdown
                if isinstance(result, dict):
                    markdown = result.get("markdown", "")
                else:
                    markdown = getattr(result, "markdown", "")

                # Vérifier si le contenu est valide
                if not markdown or len(markdown.strip()) < 10:
                    logger.warning("Contenu markdown très court pour %s (%d caractères)", url, len(markdown))
                    if attempt < self.max_retries:
                        continue  # Réessayer si contenu suspect

                duration = round(time.time() - start, 2)

                # Métadonnées enrichies
                metadata = f"""---
url: {url}
title: {url_data.get('title', '')}
section: {url_data.get('section', 'unknown')}
angle: {url_data.get('angle', '')}
question: {url_data.get('question', '')}
query: {url_data.get('query', '')}
scraped_at: {datetime.now(UTC).isoformat()}
scraping_duration_seconds: {duration}
attempts: {attempt}
status: success
---

"""
                final_markdown = metadata + markdown

                return {
                    "success": True,
                    "url": url,
                    "markdown": final_markdown,
                    "duration": duration,
                    "attempts": attempt,
                    "content_length": len(markdown)
                }

            except Exception as e:
                last_error = e
                logger.warning(
                    "Tentative %d/%d échouée pour %s: %s",
                    attempt, self.max_retries, url, str(e)
                )

                if attempt < self.max_retries:
                    continue
                else:
                    # Dernière tentative échouée
                    duration = round(time.time() - start, 2)
                    error_markdown = f"""---
url: {url}
title: {url_data.get('title', '')}
query: {url_data.get('query', '')}
scraped_at: {datetime.now(UTC).isoformat()}
scraping_duration_seconds: {duration}
attempts: {attempt}
status: failed
error: {str(last_error)}
---

# Scraping Failed

L'URL suivante n'a pas pu être scrapée après {attempt} tentatives :

- **URL**: {url}
- **Erreur**: {str(last_error)}
- **Tentatives**: {attempt}

### Métadonnées
- Section: {url_data.get('section', 'unknown')}
- Question: {url_data.get('question', '')}
- Angle: {url_data.get('angle', '')}
"""

                    # Log l'échec pour analyse
                    self.failed_urls_log.append({
                        "url": url,
                        "error": str(last_error),
                        "attempts": attempt,
                        "duration": duration
                    })

                    return {
                        "success": False,
                        "url": url,
                        "markdown": error_markdown,
                        "duration": duration,
                        "attempts": attempt,
                        "error": str(last_error)
                    }

        # Cas improbable (ne devrait jamais arriver)
        return {
            "success": False,
            "url": url,
            "markdown": f"# Erreur critique pour {url}",
            "duration": 0,
            "attempts": 0,
            "error": "Maximum retries exceeded"
        }

    def scrape_all(self, data: dict, delay_between_requests: float = 1.0) -> ScrapingStats:
        """
        Scrape toutes les URLs extraites du JSON avec gestion robuste.

        Args:
            data: Données de recherche
            delay_between_requests: Délai entre chaque requête (en secondes)

        Returns:
            Statistiques du scraping
        """
        urls, answers = self.load_urls(search_result=data)
        stats = ScrapingStats(total=len(urls))

        print(f"\n📊 {len(urls)} URLs à scraper")
        print("=" * 60)
        print(f"⚙️  Max retries: {self.max_retries}, Timeout: {self.timeout}s, Delay: {delay_between_requests}s\n")

        for i, url_data in enumerate(urls, start=1):
            url_display = url_data['url'][:80] + "..." if len(url_data['url']) > 80 else url_data['url']
            print(f"\n[{i}/{len(urls)}] Scraping: {url_display}")

            # Scraper avec retry
            result = self._scrape_with_retry(url_data)

            # Sauvegarder (succès ou échec)
            filepath = self.save_markdown(
                url_data,
                result["markdown"],
                success=result["success"]
            )

            # Mettre à jour les statistiques
            stats.files.append(filepath)
            stats.durations.append(result["duration"])
            stats.urls_scraped.append(result["url"])
            stats.contents.append(result["markdown"])

            if result["success"]:
                stats.success += 1
                print(f"  ✅ Succès ({result['duration']:.2f}s) - {len(result.get('markdown', ''))} caractères")
            else:
                stats.failed += 1
                error_msg = result.get('error', 'Unknown error')[:60]
                print(f"  ❌ Échec ({result['duration']:.2f}s) - {error_msg}")

            # Pause entre les requêtes (sauf pour la dernière)
            if i < len(urls):
                time.sleep(delay_between_requests)

            # Log périodique
            if i % 10 == 0:
                logger.info(
                    "Progression: %d/%d (succès: %d, échecs: %d)",
                    i, len(urls), stats.success, stats.failed
                )

        # Résumé final
        print("\n" + "=" * 60)
        print("📊 RÉSULTATS FINAUX")
        print("=" * 60)
        print(f"✅ Succès: {stats.success}/{stats.total} ({stats.success/stats.total*100:.1f}%)")
        print(f"❌ Échecs: {stats.failed}/{stats.total} ({stats.failed/stats.total*100:.1f}%)")
        print(f"📁 Fichiers sauvegardés: {len(stats.files)}")
        print(f"⏱️  Durée totale: {sum(stats.durations):.2f}s")
        print(f"⏱️  Durée moyenne: {sum(stats.durations)/len(stats.durations):.2f}s")

        # Afficher quelques URLs échouées pour analyse
        if self.failed_urls_log:
            print("\n🔍 URLs échouées (premières 5):")
            for failed in self.failed_urls_log[:5]:
                print(f"  - {failed['url'][:60]}... (erreur: {failed['error'][:40]})")

        return stats


# if __name__ == "__main__":
#     # Exemple d'utilisation
#     cls_api = APIClients()
#     cl_fire=cls_api.firecrawl_client
#     crawler = FirecrawlMarkdownCollector(
#         client=cl_fire,
#         max_retries=3,  # 3 tentatives par URL
#         timeout=60000  # 60 secondes de timeout
#     )

#     with open('outputs/projects/20260809_225043_je_souhaite_lancer_une_plateforme_saas_d/search/search_results.json', 'r', encoding='utf-8') as fichier:
#         donnees = json.load(fichier)

#     # Scraper avec délai de 1.5s entre chaque requête
#     result = crawler.scrape_all(
#         donnees,
#         delay_between_requests=1.5  # Délai entre les requêtes
#     )
