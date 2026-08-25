"""
Agents concrets d'analyse de section.

Chaque agent ne définit que ses métadonnées (nom, libellé, questions
par défaut) et son prompt de synthèse : tout le pipeline générique
(HyDE, retrieval, réponse) est hérité de BaseSectionAgent.
"""

from typing import Dict, List, Tuple

from embedding.chroma_manager import ChromaManager

from .base_agent import BaseSectionAgent
from .models import QuestionAnalysis


class MacroAgent(BaseSectionAgent):
    """Analyse Macro-Marché."""

    SECTION_NAME = "macro"
    SECTION_LABEL = "Analyse Macro-Marché"
    DEFAULT_QUESTIONS = [
        "quelle est la structure du marché en termes de segments, taille et croissance ?",
        "Quelles sont les tendances technologiques et réglementaires qui façonnent le marché",
        "Quels facteurs macro-économiques influencent l'adoption des solutions dans ce secteur?",
    ]

    def _build_synthesis_prompt(self, question_analyses: List[QuestionAnalysis]) -> Tuple[str, str]:
        system = (
        "Tu es un consultant senior en stratégie, rédigeant l'analyse SWOT "
        "d'un rapport d'étude de marché professionnel destiné à un client.\n\n"
        "RÈGLE ABSOLUE — ANCRAGE AUX DONNÉES FOURNIES :\n"
        "- Tu t'appuies STRICTEMENT sur les réponses fournies ci-dessous et "
        "les informations projet, sans ajouter aucune connaissance externe "
        "même si elle te semble exacte.\n"
        "- N'invente et n'extrapole jamais un chiffre, un fait ou une "
        "statistique absent des réponses fournies.\n"
        "- Si les données disponibles sont insuffisantes pour un quadrant, "
        "formule les points de façon qualitative à partir de ce qui est "
        "disponible plutôt que d'inventer un point non étayé.\n\n"
        "RÈGLE MÉTHODOLOGIQUE SWOT (à respecter strictement) :\n"
        "- Forces et Faiblesses = facteurs INTERNES au projet/à l'entreprise "
        "(ressources, positionnement, produit, équipe, coûts...).\n"
        "- Opportunités et Menaces = facteurs EXTERNES liés au marché/à "
        "l'environnement (réglementation, concurrence, tendances, "
        "macro-économie...).\n"
        "- Ne classe jamais un facteur externe en Force/Faiblesse, ni un "
        "facteur interne en Opportunité/Menace.\n"
        "- Un même fait ne doit apparaître que dans UN SEUL quadrant, jamais "
        "reformulé dans plusieurs quadrants à la fois.\n\n"
        "RÈGLE DE SOURÇAGE DES CHIFFRES :\n"
        "- Tout chiffre cité doit reprendre exactement la valeur telle "
        "qu'elle apparaît dans les réponses fournies, sans arrondi ni "
        "reformulation.\n\n"
        "STYLE ATTENDU :\n"
        "- Ton factuel, professionnel, synthétique — style rapport client.\n"
        "- Pas de première personne, pas de méta-commentaire sur la tâche.\n"
        "- Chaque point doit être une affirmation concrète et actionnable, "
        "jamais une généralité vague (éviter 'bonne image de marque' sans "
        "précision, préférer une formulation appuyée sur un fait des "
        "réponses fournies)."
    
               )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)

        user = (
        f"## Informations projet\n{self._format_project_info()}\n\n"
        f"## Réponses obtenues\n{qa_block}\n\n"
        f"## Consigne\n"
        f"Rédige l'analyse 'Macro-Marché' structurée EXACTEMENT en 3 "
        f"sous-parties, avec ces titres en gras (format Markdown '**Titre**'), "
        f"dans cet ordre :\n\n"
        f"1. **Taille & croissance** — taille actuelle du marché, taux de "
        f"croissance (CAGR ou annuel), projections chiffrées si disponibles.\n"
        f"2. **Facteurs macro-économiques et réglementaires** — contexte "
        f"économique, réglementations, politiques publiques influençant le "
        f"marché, avec chiffres ou dates à l'appui si disponibles.\n"
        f"3. **Tendances structurantes** — évolutions de fond (technologiques, "
        f"sociétales, concurrentielles) qui redessinent le marché à moyen "
        f"ou long terme.\n\n"
        f"Mets en avant systématiquement les CHIFFRES CLÉS disponibles dans "
        f"chaque sous-partie (pourcentages, montants, taux, dates).\n\n"
        f"Longueur cible : 300 à 500 mots au total, répartis de façon "
        f"équilibrée entre les 3 sous-parties. Rédige uniquement le texte de "
        f"l'analyse, sans préambule ni commentaire supplémentaire."
    )

        return system, user










class DemandAgent(BaseSectionAgent):
    """Analyse Demande & Pain Points."""

    SECTION_NAME = "demand"
    SECTION_LABEL = "Analyse Demande & Pain Points"
    DEFAULT_QUESTIONS = [
        "Qui sont les segments de clientèle cibles et quelle est leur taille ?",
        "Quels sont les principaux pain points avec les solutions existantes ?",
        "Quels sont les critères de décision d'achat et la disposition à payer ?",
    ]

    def _build_synthesis_prompt(self, question_analyses: List[QuestionAnalysis]) -> Tuple[str, str]:
        system = (
        "Tu es un analyste senior spécialisé en études de la demande et du "
        "comportement client, rédigeant la section 'Demande & Pain Points' "
        "d'un rapport d'étude de marché professionnel destiné à un client.\n\n"
        "RÈGLE ABSOLUE — ANCRAGE AUX DONNÉES FOURNIES :\n"
        "- Tu t'appuies EXCLUSIVEMENT sur les réponses fournies ci-dessous, "
        "sans ajouter aucune connaissance externe même si elle te semble "
        "exacte.\n"
        "- N'invente et n'extrapole jamais un chiffre, un pourcentage, un "
        "montant ou une statistique absent des réponses fournies.\n"
        "- Si une sous-partie manque de données chiffrées ou qualitatives "
        "suffisantes dans les réponses fournies, rédige-la quand même de "
        "façon qualitative à partir de ce qui est disponible, et signale "
        "brièvement la limite plutôt que de combler par une estimation "
        "(ex. \"les données disponibles ne permettent pas de chiffrer...\").\n\n"
        "RÈGLE DE SOURÇAGE DES CHIFFRES :\n"
        "- Tout chiffre clé cité doit reprendre exactement la valeur telle "
        "qu'elle apparaît dans les réponses fournies (aucun arrondi ni "
        "reformulation de la valeur).\n"
        "- En cas de chiffres contradictoires entre deux réponses, mentionne "
        "les deux valeurs plutôt que d'en choisir une arbitrairement.\n\n"
        "STYLE ATTENDU :\n"
        "- Ton factuel, professionnel, analytique — style rapport client, "
        "jamais conversationnel.\n"
        "- Pas de première personne, pas de méta-commentaire sur la tâche "
        "('d'après les réponses fournies...', 'en tant qu'analyste...') : "
        "écris directement comme un extrait de rapport final.\n"
        "- Privilégie les formulations analytiques ('les données indiquent "
        "que...', 'X% des répondants...') plutôt que descriptives."
    )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
        f"## Informations projet\n{self._format_project_info()}\n\n"
        f"## Réponses obtenues\n{qa_block}\n\n"
        f"## Consigne\n"
        f"Rédige l'analyse 'Demande & Pain Points' structurée EXACTEMENT en "
        f"3 sous-parties, avec ces titres en gras (format Markdown '**Titre**'), "
        f"dans cet ordre :\n\n"
        f"1. **Segments de clientèle** — profils, tailles ou poids relatifs des "
        f"segments identifiés, avec chiffres à l'appui si disponibles.\n"
        f"2. **Principaux pain points** — difficultés, frustrations ou besoins "
        f"non satisfaits les plus significatifs, hiérarchisés par importance "
        f"ou fréquence si les données le permettent.\n"
        f"3. **Critères de décision & disposition à payer** — facteurs "
        f"déterminants dans le choix d'achat et éléments chiffrés sur le "
        f"budget ou la disposition à payer, si disponibles.\n\n"
        f"Mets en avant systématiquement les CHIFFRES CLÉS disponibles dans "
        f"chaque sous-partie (pourcentages, montants, taux, fréquences).\n\n"
        f"Longueur cible : 300 à 500 mots au total, répartis de façon "
        f"équilibrée entre les 3 sous-parties. Rédige uniquement le texte de "
        f"l'analyse, sans préambule ni commentaire supplémentaire."
    )
        return system, user











class CompetitionAgent(BaseSectionAgent):
    """Analyse Offre & Concurrence."""

    SECTION_NAME = "supply"
    SECTION_LABEL = "Analyse Offre & Concurrence"
    DEFAULT_QUESTIONS = [
        "Qui sont les principaux acteurs et quel est leur positionnement ?",
        "Quelles sont les parts de marché et la dynamique concurrentielle ?",
        "Quelles sont les barrières à l'entrée et les facteurs différenciants ?",
    ]

    def _build_synthesis_prompt(self, question_analyses: List[QuestionAnalysis]) -> Tuple[str, str]:
        system = (
        "Tu es un analyste senior spécialisé en analyse concurrentielle et "
        "études de marché, rédigeant la section 'Offre & Concurrence' d'un "
        "rapport professionnel destiné à un client.\n\n"
        "RÈGLE ABSOLUE — ANCRAGE AUX DONNÉES FOURNIES :\n"
        "- Tu t'appuies EXCLUSIVEMENT sur les réponses fournies ci-dessous, "
        "sans ajouter aucune connaissance externe même si elle te semble "
        "exacte.\n"
        "- N'invente et n'extrapole jamais un chiffre, un nom d'acteur, une "
        "part de marché ou une statistique absent des réponses fournies.\n"
        "- Si une sous-partie manque de données chiffrées ou qualitatives "
        "suffisantes dans les réponses fournies, rédige-la quand même de "
        "façon qualitative à partir de ce qui est disponible, et signale "
        "brièvement la limite plutôt que de combler par une estimation "
        "(ex. \"les données disponibles ne permettent pas de chiffrer les "
        "parts de marché exactes...\").\n\n"
        "RÈGLE DE SOURÇAGE DES CHIFFRES :\n"
        "- Tout chiffre clé cité (part de marché, chiffre d'affaires, nombre "
        "d'acteurs, taux) doit reprendre exactement la valeur telle qu'elle "
        "apparaît dans les réponses fournies, sans arrondi ni reformulation.\n"
        "- N'attribue jamais une part de marché ou un chiffre à un acteur "
        "s'il n'est pas explicitement associé à cet acteur dans les réponses "
        "fournies.\n"
        "- En cas de chiffres contradictoires entre deux réponses, mentionne "
        "les deux valeurs plutôt que d'en choisir une arbitrairement.\n\n"
        "STYLE ATTENDU :\n"
        "- Ton factuel, professionnel, analytique — style rapport client, "
        "jamais conversationnel.\n"
        "- Pas de première personne, pas de méta-commentaire sur la tâche "
        "('d'après les réponses fournies...', 'en tant qu'analyste...') : "
        "écris directement comme un extrait de rapport final.\n"
        "- Privilégie les formulations analytiques ('l'acteur X détient...', "
        "'le marché reste fragmenté avec...') plutôt que descriptives."
    )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
        f"## Informations projet\n{self._format_project_info()}\n\n"
        f"## Réponses obtenues\n{qa_block}\n\n"
        f"## Consigne\n"
        f"Rédige l'analyse 'Offre & Concurrence' structurée EXACTEMENT en 3 "
        f"sous-parties, avec ces titres en gras (format Markdown '**Titre**'), "
        f"dans cet ordre :\n\n"
        f"1. **Principaux acteurs & positionnement** — identification des "
        f"acteurs majeurs, leur positionnement (prix, gamme, cible), avec "
        f"chiffres à l'appui si disponibles (CA, effectifs, nombre de "
        f"clients).\n"
        f"2. **Parts de marché & dynamique concurrentielle** — répartition "
        f"des parts de marché, niveau de concentration ou de fragmentation, "
        f"mouvements récents (fusions, entrées, sorties) si mentionnés.\n"
        f"3. **Barrières à l'entrée & différenciation** — obstacles à "
        f"l'entrée de nouveaux acteurs (réglementaires, capitalistiques, "
        f"technologiques) et leviers de différenciation identifiés.\n\n"
        f"Mets en avant systématiquement les CHIFFRES CLÉS disponibles dans "
        f"chaque sous-partie (pourcentages, montants, nombre d'acteurs).\n\n"
        f"Longueur cible : 300 à 500 mots au total, répartis de façon "
        f"équilibrée entre les 3 sous-parties. Rédige uniquement le texte de "
        f"l'analyse, sans préambule ni commentaire supplémentaire."
    )

        return system, user





class SwotAgent(BaseSectionAgent):
    """Analyse SWOT."""

    SECTION_NAME = "swot"
    SECTION_LABEL = "Analyse SWOT"
    DEFAULT_QUESTIONS = [
        "Quelles sont les forces et faiblesses internes du projet ?",
        "Quelles opportunités du marché le projet peut-il saisir ?",
        "Quelles menaces pèsent sur le projet ?",
    ]

    def _build_synthesis_prompt(self, question_analyses: List[QuestionAnalysis]) -> Tuple[str, str]:
        system = (
        "Tu es un consultant senior en stratégie, rédigeant l'analyse SWOT "
        "d'un rapport d'étude de marché professionnel destiné à un client.\n\n"
        "RÈGLE ABSOLUE — ANCRAGE AUX DONNÉES FOURNIES :\n"
        "- Tu t'appuies STRICTEMENT sur les réponses fournies ci-dessous et "
        "les informations projet, sans ajouter aucune connaissance externe "
        "même si elle te semble exacte.\n"
        "- N'invente et n'extrapole jamais un chiffre, un fait ou une "
        "statistique absent des réponses fournies.\n"
        "- Si les données disponibles sont insuffisantes pour un quadrant, "
        "formule les points de façon qualitative à partir de ce qui est "
        "disponible plutôt que d'inventer un point non étayé.\n\n"
        "RÈGLE MÉTHODOLOGIQUE SWOT (à respecter strictement) :\n"
        "- Forces et Faiblesses = facteurs INTERNES au projet/à l'entreprise "
        "(ressources, positionnement, produit, équipe, coûts...).\n"
        "- Opportunités et Menaces = facteurs EXTERNES liés au marché/à "
        "l'environnement (réglementation, concurrence, tendances, "
        "macro-économie...).\n"
        "- Ne classe jamais un facteur externe en Force/Faiblesse, ni un "
        "facteur interne en Opportunité/Menace.\n"
        "- Un même fait ne doit apparaître que dans UN SEUL quadrant, jamais "
        "reformulé dans plusieurs quadrants à la fois.\n\n"
        "RÈGLE DE SOURÇAGE DES CHIFFRES :\n"
        "- Tout chiffre cité doit reprendre exactement la valeur telle "
        "qu'elle apparaît dans les réponses fournies, sans arrondi ni "
        "reformulation.\n\n"
        "STYLE ATTENDU :\n"
        "- Ton factuel, professionnel, synthétique — style rapport client.\n"
        "- Pas de première personne, pas de méta-commentaire sur la tâche.\n"
        "- Chaque point doit être une affirmation concrète et actionnable, "
        "jamais une généralité vague (éviter 'bonne image de marque' sans "
        "précision, préférer une formulation appuyée sur un fait des "
        "réponses fournies)."
    )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
        f"## Informations projet\n{self._format_project_info()}\n\n"
        f"## Réponses obtenues\n{qa_block}\n\n"
        f"## Consigne\n"
        f"Rédige l'analyse SWOT au format Markdown STRICT suivant, sans rien "
        f"ajouter avant ou après :\n\n"
        f"## 💪 Forces\n"
        f"- ...\n\n"
        f"## ⚠️ Faiblesses\n"
        f"- ...\n\n"
        f"## 🚀 Opportunités\n"
        f"- ...\n\n"
        f"## ⚡ Menaces\n"
        f"- ...\n\n"
        f"Contraintes :\n"
        f"- 3 à 5 points par quadrant.\n"
        f"- Chaque point en UNE phrase concise (une seule ligne de puce), "
        f"chiffré quand une donnée pertinente est disponible dans les "
        f"réponses fournies.\n"
        f"- Respecte strictement la distinction interne (Forces/Faiblesses) "
        f"vs externe (Opportunités/Menaces).\n"
        f"- N'écris aucun texte hors de cette structure à 4 quadrants (pas "
        f"d'introduction, pas de conclusion, pas de commentaire)."
    )
        return system, user




# ============================================================================
# Registre des agents
# ============================================================================

SECTION_AGENTS: Dict[str, type] = {
    MacroAgent.SECTION_NAME: MacroAgent,
    DemandAgent.SECTION_NAME: DemandAgent,
    CompetitionAgent.SECTION_NAME: CompetitionAgent,
    SwotAgent.SECTION_NAME: SwotAgent,
}


def get_section_agent(section_name: str) -> type:
    """Récupère la classe d'agent correspondant à un nom de section."""
    try:
        return SECTION_AGENTS[section_name]
    except KeyError:
        raise ValueError(
            f"Section inconnue: '{section_name}'. Disponibles: {list(SECTION_AGENTS.keys())}"
        )



if __name__ == "__main__":
    chroma=ChromaManager()
    proj={
        "country": "France",
        "customer_industry": "Restauration",
        "product_sector": "Hospitality SaaS",
        "software_category": "Restaurant Management System (RMS)",
        "market_category": "Hospitality SaaS Market",
        "business_model": "B2B SaaS",
        "target_market": "Restaurants indépendants en France, petites et moyennes tailles, cherchant à digitaliser et optimiser leur gestion opérationnelle",
        "personas": [
            "Propriétaires de restaurants indépendants",
            "gérants",
            "responsables opérationnels",
            "chefs de cuisine"
        ],
        "value_proposition": "Une plateforme intégrée et intelligente qui simplifie la gestion des commandes, réservations, stocks et analyse des ventes pour les restaurants indépendants, améliorant ainsi leur efficacité opérationnelle et leur rentabilité.",
        "primary_keywords": [
            "gestion restaurant",
            "réservation restaurant",
            "commande en ligne",
            "gestion des stocks",
            "analyse des ventes"
        ],
        "secondary_keywords": [
            "intelligence artificielle",
            "optimisation opérationnelle",
            "SaaS restauration",
            "digitalisation restaurant",
            "analytics ventes",
            "gestion commandes",
            "gestion réservations",
            "gestion inventaire",
            "performance commerciale",
            "solution intégrée"
        ],
        "potential_competitors": [
            "TouchBistro",
            "Lightspeed Restaurant",
            "Square for Restaurants",
            "Tiller Systems",
            "Zenchef"
        ],
        "raw_description": "Je souhaite lancer une plateforme SaaS destinée aux restaurants indépendants en France permettant de gérer les commandes, les réservations, les stocks et l'analyse des ventes grâce à l'intelligence artificielle."
    }

    collection_aname ="hospitality_saas_restauration_20260812_111238"
    agent= DemandAgent(chroma_manager=chroma,collection_name="")


