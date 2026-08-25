"""
Web Search Utilities
====================
Constants and pure helper functions for web search scoring, URL normalization,
and result persistence.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================


UNRELIABLE_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "tiktok.com",
    "linkedin.com/pulse",
    "reddit.com",
    "quora.com",
    "medium.com",
    "blogspot.com",
    "wordpress.com",
    "wix.com",
    "weebly.com",
    "squarespace.com",
    "hubpages.com",
    "wikihow.com",
    "scribd.com",
    "slideshare.net",
    "issuu.com",
    "pinterest.com",
    "tumblr.com",
    "snapchat.com",
    "whatsapp.com",
    "telegram.org",
}

TRUSTED_DOMAINS = {
    "gouv.fr",
    "legifrance.gouv.fr",
    "insee.fr",
    "economie.gouv.fr",
    "banque-france.fr",
    "europa.eu",
    "european-union.europa.eu",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "who.int",
    "unesco.org",
    "statistiques.developpement-durable.gouv.fr",
    "cairn.info",
    "erudit.org",
    "jstor.org",
    "sciencedirect.com",
    "springer.com",
    "ieee.org",
    "acm.org",
    "arxiv.org",
    "researchgate.net",
    "scholar.google.com",
    "harvard.edu",
    "stanford.edu",
    "mit.edu",
    "ox.ac.uk",
    "cambridge.org",
    "g2.com",
    "capterra.com",
    "trustpilot.com",
    "glassdoor.fr",
    "lesechos.fr",
    "lemonde.fr",
    "lefigaro.fr",
    "ft.com",
    "wsj.com",
    "bloomberg.com",
    "forbes.com",
    "businessinsider.com",
    "techcrunch.com",
    "wired.com",
}


# ============================================================================
# URL Helpers
# ============================================================================


def normalize_url(url: str) -> str:
    """Normalise une URL pour une comparaison fiable (enlève les paramètres inutiles)."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.replace("www.", "")
        normalized = f"{netloc}{parsed.path}".rstrip("/")
        return normalized.lower()
    except Exception:
        return url.lower()


def is_duplicate_url(url: str, seen_urls: set) -> bool:
    """Vérifie si une URL a déjà été vue (déduplication)."""
    normalized = normalize_url(url)
    if normalized in seen_urls:
        return True
    seen_urls.add(normalized)
    return False


# ============================================================================
# Scoring
# ============================================================================


def calculate_french_context_score(url: str, title: str, content: str) -> float:
    """Calcule un score pour la pertinence du contexte français."""
    score = 0.0
    domain = urlparse(url).netloc.lower()

    if domain.endswith(".fr"):
        score += 0.3
    elif "french" in content.lower() or "france" in content.lower():
        score += 0.15

    french_indicators = [
        "france",
        "français",
        "française",
        "paris",
        "lyon",
        "marseille",
        "gouvernement",
        "ministère",
        "loi",
        "règlement",
        "code du travail",
        "pme",
        "startup",
        "saas",
        "paie",
        "ressources humaines",
    ]

    content_lower = content.lower()
    for indicator in french_indicators:
        if indicator in content_lower:
            score += 0.05

    if ".gouv.fr" in domain:
        score += 0.3

    return min(score, 1.0)


def calculate_reliability_score(url: str) -> float:
    """Calcule un score de fiabilité basé sur le domaine."""
    domain = urlparse(url).netloc.lower()

    for unreliable in UNRELIABLE_DOMAINS:
        if unreliable in domain:
            return 0.0

    for trusted in TRUSTED_DOMAINS:
        if trusted in domain:
            return 1.0

    if domain.endswith(".edu") or ".ac." in domain:
        return 0.9

    if domain.endswith(".gov") or ".gouv." in domain:
        return 0.95

    news_sites = [
        "lesechos",
        "lemonde",
        "lefigaro",
        "liberation",
        "lopinion",
        "latribune",
        "usine-nouvelle",
        "journaldunet",
        "siecledigital",
    ]
    for site in news_sites:
        if site in domain:
            return 0.8

    business_sites = ["capterra", "g2", "trustpilot", "getapp", "softwareadvice"]
    for site in business_sites:
        if site in domain:
            return 0.75

    return 0.5


def calculate_comprehensive_score(result: Dict[str, Any]) -> float:
    """Calcule un score complet pour un résultat de recherche."""
    url = result.get("url", "")
    title = result.get("title", "")
    content = result.get("content", "")

    tavily_score = result.get("score", 0.5)
    french_score = calculate_french_context_score(url, title, content)
    reliability_score = calculate_reliability_score(url)

    final_score = (tavily_score * 0.6) + (french_score * 0.2) + (reliability_score * 0.2)
    return final_score



# ============================================================================
# Saving Results
# ============================================================================


def save_search_results(
    batch_results: Any, output_dir: str = "outputs/new"
) -> None:
    """Sauvegarde les résultats de recherche dans un fichier JSON."""
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = output_path / f"search_result_{ts}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(batch_results, f, ensure_ascii=False, indent=2)

        print(f"Sauvegarde réussie : {file_path}")

    except Exception as e:
        print(f"Erreur lors de la sauvegarde des résultats: {e}")
