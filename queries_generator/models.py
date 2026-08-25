"""
Analysis Sections Configuration
=================================
Defines the 4 market analysis sections and their default major questions.
Questions can be overridden at runtime.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# =============================================================================
# 1. CORE DATA MODELS
# =============================================================================

@dataclass
class AnalysisSection:
    """Represents a market analysis section with its default questions."""
    
    id: str
    name: str
    default_questions: List[str]


@dataclass
class ProjectInfo:
    """
    Comprehensive project information for market analysis.
    
    Groups data into logical categories:
        - Market Segmentation: country, industry, sector, categories
        - Business Model: revenue model, target market, personas
        - Competitive Intelligence: keywords, competitors
        - Source Data: raw description
    """
    
    # ========== MARKET SEGMENTATION ==========
    country: str
    customer_industry: str      # ex: Hôtellerie, Santé, Retail
    product_sector: str         # ex: Hospitality SaaS, HR Tech
    software_category: str      # ex: PMS, CRM, ERP
    market_category: str        # ex: Hospitality SaaS Market
    
    # ========== BUSINESS MODEL ==========
    business_model: str         # ex: B2B SaaS
    target_market: str
    personas: List[str]
    value_proposition: str
    
    # ========== COMPETITIVE INTELLIGENCE ==========
    primary_keywords: List[str]
    secondary_keywords: List[str]
    potential_competitors: List[str]
    
    # ========== SOURCE DATA ==========
    raw_description: str
    
    # ========== EXTENDED FIELDS (Optional) ==========
    # growth_opportunities: Optional[List[str]] = None
    # market_trends: Optional[List[str]] = None
    # key_metrics: Optional[List[str]] = None



@dataclass
class SearchQuery:
    """A single search query with its angle and relevance score."""

    query: str
    angle: str
    relevance_score: float


@dataclass
class QuestionQueries:
    """All search queries generated for a single analysis question."""

    question: str
    queries: list[SearchQuery] = field(default_factory=list)


@dataclass
class AnalysisOutput:
    """Complete query generation output for one analysis section."""

    section: str
    question_queries: list[QuestionQueries] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "section": self.section,
            "questions": [
                {
                    "question": qq.question,
                    "queries": [
                        {
                            "query": sq.query,
                            "angle": sq.angle,
                            "relevance_score": sq.relevance_score,
                        }
                        for sq in qq.queries
                    ],
                }
                for qq in self.question_queries
            ],
        }



# =============================================================================
# 2. DEFAULT CONFIGURATIONS
# =============================================================================

# Default questions for each analysis section
DEFAULT_MACRO_QUESTIONS = [
    "Quelle est la structure du marché en termes de segments, taille et croissance ?",
    "Quelles sont les tendances technologiques et réglementaires qui façonnent le marché ?",
    "Quels facteurs macro-économiques influencent l'adoption des solutions dans ce secteur ?"
]

DEFAULT_DEMAND_QUESTIONS = [
    "Comment est la demande actuelle et les segments de clientèle ?",
    "Quels sont les besoins des clients et les obstacles et frictions dans le processus d'achat actuel ?",
    "Comment les clients évaluent-ils et choisissent-ils leurs solutions actuelles ?"
]

DEFAULT_SUPPLY_QUESTIONS = [
    "Qui sont les acteurs majeurs du marché et quelle est leur position ?",
    "Quelles sont les forces et faiblesses des solutions concurrentes existantes ?",
    "Quels sont les modèles de pricing et les stratégies de différenciation adoptés ?"
]

DEFAULT_SWOT_QUESTIONS = [
    "Quelles sont les opportunités et avantages exploitables à court et moyen terme ?",
    "Quelles menaces externes et risques de marché doivent être anticipés ?",
    "Quelles forces internes peuvent être capitalisées et quelles faiblesses doivent être corrigées ?"
]


# =============================================================================
# 3. ANALYSIS SECTIONS REGISTRY
# =============================================================================

ANALYSIS_SECTIONS = {
    "macro": AnalysisSection(
        id="macro",
        name="Analyse macro marché et tendances",
        default_questions=DEFAULT_MACRO_QUESTIONS
    ),
    "demand": AnalysisSection(
        id="demand",
        name="Analyse de la demande et pain points",
        default_questions=DEFAULT_DEMAND_QUESTIONS
    ),
    "supply": AnalysisSection(
        id="supply",
        name="Analyse de l'offre et concurrence",
        default_questions=DEFAULT_SUPPLY_QUESTIONS
    ),
    "swot": AnalysisSection(
        id="swot",
        name="Analyse SWOT",
        default_questions=DEFAULT_SWOT_QUESTIONS
    )
}


# =============================================================================
# 4. HELPER FUNCTIONS
# =============================================================================

def get_section(section_id: str) -> Optional[AnalysisSection]:
    """Retrieve an analysis section by its ID."""
    return ANALYSIS_SECTIONS.get(section_id)


def get_all_sections() -> List[AnalysisSection]:
    """Get all analysis sections as a list."""
    return list(ANALYSIS_SECTIONS.values())


def get_section_names() -> List[str]:
    """Get the names of all analysis sections."""
    return [section.name for section in ANALYSIS_SECTIONS.values()]


def get_default_questions(section_id: str) -> Optional[List[str]]:
    """Get default questions for a specific section."""
    section = get_section(section_id)
    return section.default_questions if section else None



