"""
Spécialisation de questions génériques vers le secteur précis du projet.

Contexte : on dispose souvent d'une banque de questions génériques
("quelle est la taille du marché ?", "comment est la demande ?"...),
et on veut les reformuler pour qu'elles pointent explicitement vers
le secteur/produit étudié (ex: "Hospitality SaaS - Property Management
System (PMS)"), à partir d'un dictionnaire project_info.
"""

import re
from typing import Dict, List, Optional, Sequence


# Mots-clés après lesquels on insère le libellé de secteur, par ordre de priorité.
_INSERTION_KEYWORDS = ["marché", "marche", "secteur", "domaine", "industrie"]


def _build_sector_label(
    project_info: Dict[str, Optional[str]],
    fields: Sequence[str] = ("product_sector", "software_category"),
    separator: str = " - ",
    fallback_fields: Sequence[str] = ("market_category", "customer_industry"),
) -> str:
    """
    Construit le libellé de secteur à partir de project_info.

    Combine les champs de `fields` (dans l'ordre, en ignorant les valeurs
    vides/None) avec `separator`. Si aucun n'est disponible, retombe sur
    `fallback_fields`.

    Ex: product_sector="Hospitality SaaS", software_category="Property
    Management System (PMS)" -> "Hospitality SaaS - Property Management
    System (PMS)"
    """
    parts = [project_info.get(f) for f in fields]
    parts = [p.strip() for p in parts if p and str(p).strip()]

    if not parts:
        for f in fallback_fields:
            value = project_info.get(f)
            if value and str(value).strip():
                parts = [str(value).strip()]
                break

    if not parts:
        raise ValueError(
            "Impossible de construire un libellé de secteur : aucun des champs "
            f"{list(fields) + list(fallback_fields)} n'est renseigné dans project_info."
        )

    return separator.join(parts)


def _insert_sector_into_question(question: str, sector_label: str) -> str:
    """
    Insère le libellé de secteur dans une question, juste après le premier
    mot-clé pertinent trouvé (marché/secteur/domaine/industrie).

    Si aucun mot-clé n'est trouvé, ajoute le libellé en fin de question,
    juste avant le point d'interrogation final s'il existe.
    """
    for keyword in _INSERTION_KEYWORDS:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        match = pattern.search(question)
        if match:
            insert_at = match.end()
            return f"{question[:insert_at]} de {sector_label}{question[insert_at:]}"

    # Aucun mot-clé trouvé : on ajoute le contexte avant le "?" final si présent.
    stripped = question.rstrip()
    if stripped.endswith("?"):
        return f"{stripped[:-1].rstrip()} pour {sector_label} ?"
    return f"{stripped} (secteur : {sector_label})"


def specialize_questions(
    project_info: Dict[str, Optional[str]],
    questions: List[str],
    sector_fields: Sequence[str] = ("product_sector", "software_category"),
    separator: str = " - ",
) -> List[str]:
    """
    Transforme une liste de questions génériques en questions spécifiques
    au secteur/produit décrit dans project_info.

    Args:
        project_info: dictionnaire de contexte projet (voir exemple dans le module).
        questions: liste de questions génériques à spécialiser.
        sector_fields: champs de project_info à combiner pour former le
            libellé de secteur (par défaut: product_sector + software_category).
        separator: séparateur utilisé entre les champs combinés.

    Returns:
        Liste de questions reformulées, dans le même ordre que `questions`.

    Example:
        >>> project_info = {
        ...     "product_sector": "Hospitality SaaS",
        ...     "software_category": "Property Management System (PMS)",
        ... }
        >>> specialize_questions(project_info, ["quelle est la taille de marché ?"])
        ['quelle est la taille de marché de Hospitality SaaS - Property Management System (PMS) ?']
    """
    sector_label = _build_sector_label(project_info, fields=sector_fields, separator=separator)
    return [_insert_sector_into_question(q, sector_label) for q in questions]


if __name__ == "__main__":
    project_info = {
    "country": "France",
    "customer_industry": "Restauration",
    "product_sector": "Hospitality SaaS",
    "software_category": "Restaurant Management System (RMS)",
    "market_category": "Restaurant Management SaaS Market",
    "business_model": "B2B SaaS (abonnement mensuel/annuel)",
    "target_market": "Restaurants indépendants en France, de petite à moyenne taille (1‑10 employés), situés en zones urbaines, recherchant une transformation digitale et une optimisation opérationnelle.",
    "personas": "- Propriétaire de restaurant\n- Gestionnaire opérationnel\n- Chef cuisinier\n- Responsable finance/achats\n- Responsable informatique/IT",
    "value_proposition": "Simplifiez la gestion quotidienne et augmentez la rentabilité de votre restaurant indépendant grâce à une plateforme AI‑intelligente qui centralise commandes, réservations, stocks et analyses de ventes.",
    "primary_keywords": "Restaurant SaaS, AI restaurant management, French independent restaurants, restaurant POS, restaurant inventory software",
    "secondary_keywords": "order management, reservation system, inventory control, sales analytics, artificial intelligence, cloud-based, mobile app, data-driven decisions, restaurant profitability, tech adoption",
    "potential_competitors": "Lightspeed Restaurant, Toast, TouchBistro, Square for Restaurants, Restaurant365, OpenTable (reservations), Resy, Zeropark, MaitreD, Qonto (finance), Sage Restaurant",
    "raw_description": "Je souhaite lancer une plateforme SaaS destinée aux restaurants indépendants en France permettant de gérer les commandes, les réservations, les stocks et l'analyse des ventes grâce à l'intelligence artificielle."
}

    generic_questions = [
        "quelle est la taille de marché ?",
        "comment est la demande dans ce marché ?",
        "quels sont les principaux concurrents ?",
        "quelles sont les tendances technologiques ?",
    ]

    for q in specialize_questions(project_info, generic_questions):
        print("-", q)