       

import json
from agents.models import QuestionInput, SubQueryHyde
from queries_generator.models import AnalysisOutput, QuestionQueries, SearchQuery
from utils.files import specialize_questions
from utils.logger import get_logger

logger = get_logger(__name__)




# ===========================================================
# Logging step
# ===========================================================

def log_step(step_number: int, step_name: str) -> None:
    """Log a step in the pipeline."""
    logger.info("=" * 80)
    logger.info("=" * 80)
    logger.info(f"🔍 ÉTAPE {step_number} : {step_name.upper()}")
    logger.info("=" * 80)
    logger.info("=" * 80)





# ===========================================================
# Get failed urls
# ===========================================================

def get_failed_urls(scraped_data):
    """
    Extrait les URLs des éléments qui ont échoué lors du scraping.
    
    Args:
        scraped_data (list): Liste de chaînes de caractères contenant les données de scraping.
        
    Returns:
        list: Liste des URLs qui ont échoué.
    """
    failed_urls = []
    
    for item in scraped_data:
        # Extraire le statut et l'URL de chaque chaîne
        lines = item.strip().split('\n')
        url = ""
        status = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("url:"):
                url = line.replace("url:", "").strip()
            elif line.startswith("status:"):
                status = line.replace("status:", "").strip()
        
        # Si le statut est "failed", ajouter l'URL à la liste
        if status.lower() == "failed" and url:
            failed_urls.append(url)
    
    return failed_urls






# ===========================================================
# Get results from json 
# ===========================================================

def get_res(path:str=r"outputs\projects\20260810_160435_je_souhaite_lancer_une_plateforme_saas_d\scraped\scraping_stats.json"):
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data



# ==========================================================
# Create queries
# ==========================================================

def create_queries(path:str=r"outputs\projects\20260811_121003_je_souhaite_lancer_une_plateforme_saas_d\queries\all_queries.json"):
    quries=get_res(path)
    dict_queries={}

    for sec , data in quries.items():
        list_qr=[]
        for q in data.get("question_queries"):
            question=q.get("question")
            queries=[]
            for qr in q.get("queries"):
                quer=SearchQuery(query=qr.get("query"),angle=qr.get("angle"),relevance_score=qr.get("relevance_score"))
                queries.append(quer)
            ques_input=QuestionQueries(question=question,queries=queries)
            list_qr.append(ques_input)

        analysis_out=AnalysisOutput(section=sec ,question_queries=list_qr)
        dict_queries[sec]=analysis_out
    return dict_queries



# ==========================================================
# Create Question inputs for expert agents
# ==========================================================

def analysis_outputs_to_question_inputs(
    outputs: AnalysisOutput | dict | None, project=dict
) -> list[QuestionInput]:
    if not outputs:
        return []

    if isinstance(outputs, dict):
        question_queries = outputs.get("question_queries", [])
    else:
        question_queries = getattr(outputs, "question_queries", [])

    question_inputs: list[QuestionInput] = []
    for qq in question_queries:
        if isinstance(qq, dict):
            question = qq.get("question", "")
            queries = qq.get("queries", [])
        else:
            question = qq.question
            queries = qq.queries

        sub_queries = [
            SubQueryHyde(
                sub_query=sq.get("query", "") if isinstance(sq, dict) else sq.query,
                hyde_answer=sq.get("angle", "") if isinstance(sq, dict) else (sq.angle or ""),
                source_url=None,
            )
            for sq in queries
        ]
        qt = [question]
        question_inputs.append(
            QuestionInput(
                question=specialize_questions(project_info=project, questions=qt)[0],
                sub_queries=sub_queries,
            )
        )

    return question_inputs


