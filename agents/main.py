"""
Script de démonstration : exécute l'analyse de sections avec différentes
méthodes de récupération dynamiques (M1-M4c), exporte les résultats
(Markdown, JSON, dataset RAGAS) et génère un rapport de synthèse.

Usage:
    python -m agents.main
"""

import json
from utils.logger import logger 

from agents.report_synthesis_agent import ReportSynthesisAgent, synthesize_report
from agents.report_evaluator import ReportSynthesisEvaluator, evaluate_synthesis
# from llm_config import OpenRouterLLMClient
from embedding.chroma_manager import ChromaManager

from .Agents import MacroAgent, DemandAgent, SwotAgent, CompetitionAgent
from .models import QuestionInput, SubQueryHyde
from .Persistence import build_ragas_dataset, save_ragas_dataset

logger=logger.getLogger(__name__)


PROJECT_INFO = {
    "country": "France",
    "customer_industry": "Hôtellerie",
    "product_sector": "Hospitality SaaS",
    "software_category": "Property Management System (PMS)",
    "market_category": "Hospitality SaaS Market (PMS segment)",
    "business_model": "B2B SaaS (subscription)",
    "target_market": "Petites et moyennes chaînes hôtelières indépendantes, 10‑200 chambres, France",
    "personas": "Propriétaire hôtel, Directeur général, Responsable revenue",
    "value_proposition": (
        "Solution cloud intégrée qui automatise les réservations, optimise la "
        "tarification dynamique et gère la relation client."
    ),
    "primary_keywords": "PMS, dynamic pricing, hotel SaaS, reservation management, independent hotels",
    "secondary_keywords": "cloud‑based, revenue management, OTA integration, channel manager",
}

SECTION_AGENTS = {
    "macro": MacroAgent,
    "demand": DemandAgent,
    "supply": CompetitionAgent,
    "swot": SwotAgent,
}

SECTION_NAMES = {
    "macro": "macro_marche",
    "demand": "demande_et_pain_points",
    "supply": "offre_et_competition",
    "swot": "swot",
}


def build_demo_question(section: str, file_path: str) -> list:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sec_data = data.get(section)
    questions_list = []
    for qu in sec_data.get("questions"):
        q = qu.get("question")
        req = qu.get("queries")
        requetes = []
        for r in req:
            query = r.get("query")
            answer = r.get("answer")
            sub_qu = SubQueryHyde(sub_query=query, hyde_answer=answer)
            requetes.append(sub_qu)

        q_input = QuestionInput(question=q, sub_queries=requetes)
        questions_list.append(q_input)

    return questions_list


def run_demo(
    method: str = "",
    section: str = "demand",
    file_path: str = "outputs/search_result_20260706_094626.json",
) -> object:
    """
    Exécute l'analyse d'une section avec une méthode de récupération dynamique.

    Args:
        method: Méthode de récupération (M1, M2, M3a, M3b, M4a, M4b, M4c).
        section: Section à analyser ('macro', 'demand', 'supply', 'swot').
        file_path: Chemin vers le fichier JSON de questions.

    Returns:
        SectionAnalysis result, or None on failure.
    """
    chroma = ChromaManager(persist_directory="data/chromadb")
    llm_client = OpenRouterLLMClient(model="openai/gpt-4.1-mini")

    agent_cls = SECTION_AGENTS.get(section)
    if agent_cls is None:
        raise ValueError(f"Section inconnue: '{section}'. Disponibles: {list(SECTION_AGENTS.keys())}")

    agent = agent_cls(
        chroma_manager=chroma,
        collection_name="hotellerie_saas",
        llm_client=llm_client,
        project_info=PROJECT_INFO,
        retrieval_strategy=method,
        retrieval_kwargs={"top_k": 20},
        logger=logger,
    )

    questions = build_demo_question(section=section, file_path=file_path)

    print("\n" + "=" * 70)
    print(f"🧪 Analyse de '{section}' avec méthode {method}")
    print("=" * 70)

    result = agent.analyze(questions)
    result.save(f"data_testing/analyses/{section}_{method}.md")

    dataset = build_ragas_dataset(result)
    save_ragas_dataset(dataset, f"data_testing/eval/{method}_{section}_ragas.json")

    print(f"\n✅ Terminé avec succès!")
    print(f"   - Résultats   : data_testing/analyses/{section}_{method}.md")
    print(f"   - Dataset RAGAS: data_testing/eval/{method}_{section}_ragas.json")
    print(f"   - Score composite: {result.evaluation.get('composite_score', 'N/A')}")

    return result


def run_synthesis_demo(
    method: str = "M4c",
    file_path: str = "outputs/search_result_20260706_094626.json",
) -> None:
    """
    Exécute l'analyse de toutes les sections puis génère un rapport de synthèse.

    Args:
        method: Méthode de récupération (M1, M2, M3a, M3b, M4a, M4b, M4c).
        file_path: Chemin vers le fichier JSON de questions.
    """
    chroma = ChromaManager(persist_directory="data/chromadb")
    llm_client = OpenRouterLLMClient(model="openai/gpt-4.1-mini")

    section_results = []

    for section_key, agent_cls in SECTION_AGENTS.items():
        print("\n" + "-" * 60)
        print(f"📊 Analyse de '{section_key}' avec méthode {method}")
        print("-" * 60)

        try:
            agent = agent_cls(
                chroma_manager=chroma,
                collection_name="hotellerie_saas",
                llm_client=llm_client,
                project_info=PROJECT_INFO,
                retrieval_strategy=method,
                retrieval_kwargs={"top_k": 20},
                logger=logger,
            )

            questions = build_demo_question(section=section_key, file_path=file_path)
            result = agent.analyze(questions)
            result.save(f"data_testing/analyses/{SECTION_NAMES[section_key]}_{method}.md")
            section_results.append(result)
            print(f"   ✅ {section_key} terminé")

        except Exception as e:
            logger.exception(
                f"Échec de la section '{section_key}' avec la méthode '{method}': {e}"
            )

    if not section_results:
        logger.error("Aucune analyse de section n'a réussi — synthèse impossible.")
        return

    print("\n" + "=" * 70)
    print(f"📋 Génération du rapport de synthèse (méthode {method})")
    print("=" * 70)

    synthesizer = ReportSynthesisAgent(llm_client=llm_client, logger=logger)
    report = synthesizer.synthesize(
        section_results,
        output_path=f"data_testing/reports/synthesis_{method}.md",
    )

    print(f"\n✅ Rapport de synthèse sauvegardé!")
    print(f"   - Rapport     : data_testing/reports/synthesis_{method}.md")
    print(f"   - JSON        : data_testing/reports/synthesis_{method}.json")
    print(f"   - Sections    : {len(report.sections)}")

    print("\n" + "=" * 70)
    print(f"📊 Évaluation du rapport de synthèse (méthode {method})")
    print("=" * 70)

    evaluator = ReportSynthesisEvaluator(llm_client=llm_client, logger=logger)
    eval_result = evaluator.evaluate(
        report,
        section_results,
        project_info=PROJECT_INFO,
        output_path=f"data_testing/eval/synthesis_{method}_eval.json",
    )

    print(f"\n✅ Évaluation terminée!")
    print(f"   - Score global: {eval_result.global_score:.0%}")
    print(f"   - Complétude: {eval_result.completeness.completeness_score:.0%}")
    print(f"   - Cohérence: {eval_result.coherence.score:.0%}")
    print(f"   - Fidélité: {eval_result.faithfulness.score:.0%}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    method = "M4c"

    print("\n" + "#" * 80)
    print(f"### Analyse des 4 sections avec méthode {method}")
    print("#" * 80)

    section_results = []

    for section_key in ["macro", "demand", "supply", "swot"]:
        try:
            result = run_demo(
                method=method,
                section=section_key,
            )
            if result is not None:
                section_results.append(result)
        except Exception as e:
            logger.exception(
                f"Échec de la section '{section_key}' avec la méthode '{method}': {e}"
            )

    if section_results:
        run_synthesis_demo(method=method)

    print("\n🎉 Toutes les analyses, synthèses et évaluations sont terminées.")


    



 