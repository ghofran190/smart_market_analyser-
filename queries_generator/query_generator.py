"""
Market Analysis Query Generator
=================================
Uses DSPy + OpenRouter to generate diversified, relevant search queries
for each major question in a market analysis framework.
"""


from dataclasses import asdict
from pathlib import Path

from clients import APIClients
from queries_generator.DSPy_config import MarketAnalysisQueryPipeline
from queries_generator.models import ANALYSIS_SECTIONS, AnalysisOutput
from queries_generator.utils import print_output
from utils.logger import get_logger

logger = get_logger(__name__)
# api_cls=APIClients()

# ============================================================================
# Pipeline Executor
# ============================================================================


class MarketAnalysisQueryPipelineExecuter:
    """
    Wrapper to run the pipeline with a given LLM model and optional output saving.
    """

    def __init__(self):
        self.pipeline = MarketAnalysisQueryPipeline()
        


    def run_section(
        self,
        project_info: dict,
        section_id: str,
        num_queries: int = 4,
        output_dir: Path = Path("outputs"),
    ) -> AnalysisOutput:
        section = ANALYSIS_SECTIONS[section_id]
        questions = section.default_questions
        logger.info(f"🚀 Processing section: {section.name}")
        logger.info(f"   Questions: {len(questions)} | Queries per question: {num_queries}")

        output = self.pipeline(
            project_info=project_info,
            section=section.name,
            questions=questions,
            num_queries=num_queries,
        )

        logger.info(output)

        return output


    def all_sections(
        self,
        project_info: dict,
        num_queries: int = 4,
        output_dir: Path = Path("outputs"),
    ) -> dict[str, AnalysisOutput]:
        all_outputs = {}
        for section_id in ANALYSIS_SECTIONS.keys():
            output = self.run_section(
                project_info=project_info,
                section_id=section_id,
                num_queries=num_queries,
                output_dir=output_dir,
            )
            all_outputs[section_id] = asdict(output)

        logger.info(f"✅ All sections processed.")

        return all_outputs




# ============================================================================
# Entry Point
# ============================================================================


if __name__ == "__main__":
    api_cls=APIClients()
    sample_project = {
        "country": "France",
        "customer_industry": "Hôtellerie",
        "product_sector": "Hospitality SaaS",
        "software_category": "Property Management System (PMS)",
        "market_category": "Hospitality SaaS Market (PMS segment)",
        "business_model": "B2B SaaS (subscription)",
        "target_market": "Petites et moyennes chaînes hôtelières indépendantes, 10‑200 chambres, France",
        "personas": "Propriétaire hôtel, Directeur général, Responsable revenue, Responsable front‑desk, Responsable IT",
        "value_proposition": "Solution cloud intégrée qui automatise les réservations, optimise la tarification dynamique et gère la relation client, pour augmenter les revenus et réduire les coûts opérationnels des hôtels indépendants.",
        "primary_keywords": "PMS, dynamic pricing, hotel SaaS, reservation management, independent hotels",
        "secondary_keywords": "cloud‑based, revenue management, OTA integration, channel manager, guest CRM, price optimization, OTA distribution, channel distribution, guest engagement, data analytics, API integration",
        "potential_competitors": "Cloudbeds, eZee Absolute, Hotelogix, RMS Cloud, Little Hotelier, HotelRunner, ResNexus, MyHotel, Cloudbeds, Hotelogix, eZee Absolute",
        "raw_description": "Je souhaite développer une plateforme SaaS destinée aux hôtels indépendants permettant de gérer les réservations, la tarification dynamique et la relation clien",
    }

    executer = MarketAnalysisQueryPipelineExecuter()
    output=executer.all_sections(project_info=sample_project, num_queries=4, output_dir=Path("outputs_rxp"))
    