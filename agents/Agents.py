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
            "Tu es un analyste macro-économique spécialisé en études de marché. "
            "Tu rédiges la section 'Macro-Marché' d'un rapport professionnel. "
            "Cite systématiquement les chiffres clés disponibles. "
            "N'invente aucun chiffre absent des réponses fournies."
        )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
            f"## Informations projet\n{self._format_project_info()}\n\n"
            f"## Réponses obtenues\n{qa_block}\n\n"
            "## Consigne\nRédige une analyse 'Macro-Marché' structurée en 3 sous-parties "
            "(Taille & croissance, Facteurs macro-économiques et réglementaires, "
            "Tendances structurantes), en mettant en avant les CHIFFRES CLÉS. "
            "Longueur cible : 300-500 mots."
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
            "Tu es un analyste spécialisé en études de la demande et du "
            "comportement client. Cite les chiffres clés disponibles. "
            "N'invente aucun chiffre absent des réponses fournies."
        )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
            f"## Informations projet\n{self._format_project_info()}\n\n"
            f"## Réponses obtenues\n{qa_block}\n\n"
            "## Consigne\nRédige une analyse 'Demande & Pain Points' structurée en 3 "
            "sous-parties (Segments de clientèle, Principaux pain points, Critères de "
            "décision & disposition à payer), en mettant en avant les CHIFFRES CLÉS. "
            "Longueur cible : 300-500 mots."
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
            "Tu es un analyste concurrentiel spécialisé en études de marché. "
            "Cite systématiquement les chiffres clés disponibles. "
            "N'invente aucun chiffre absent des réponses fournies."
        )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
            f"## Informations projet\n{self._format_project_info()}\n\n"
            f"## Réponses obtenues\n{qa_block}\n\n"
            "## Consigne\nRédige une analyse 'Offre & Concurrence' structurée en 3 "
            "sous-parties (Principaux acteurs & positionnement, Parts de marché & "
            "dynamique concurrentielle, Barrières à l'entrée & différenciation), en "
            "mettant en avant les CHIFFRES CLÉS. Longueur cible : 300-500 mots."
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
            "Tu es un consultant en stratégie. Tu rédiges une analyse SWOT "
            "structurée en 4 quadrants, basée STRICTEMENT sur les réponses fournies. "
            "N'invente aucun chiffre absent des réponses fournies."
        )
        qa_block = "\n\n".join(f"### {qa.question}\n{qa.answer}" for qa in question_analyses)
        user = (
            f"## Informations projet\n{self._format_project_info()}\n\n"
            f"## Réponses obtenues\n{qa_block}\n\n"
            "## Consigne\nRédige l'analyse SWOT au format Markdown STRICT suivant :\n\n"
            "## 💪 Forces\n- ...\n\n"
            "## ⚠️ Faiblesses\n- ...\n\n"
            "## 🚀 Opportunités\n- ...\n\n"
            "## ⚡ Menaces\n- ...\n\n"
            "3 à 5 points par quadrant, chacun en une phrase concise, chiffré quand "
            "c'est pertinent."
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


