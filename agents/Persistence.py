
"""
Persistance et export des résultats d'analyse.

Regroupe :
    - la sauvegarde disque d'une SectionAnalysis (Markdown + JSON)
    - la construction / sauvegarde d'un dataset RAGAS pour évaluation
"""

import json
from logging import Logger
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import QuestionAnalysis, SectionAnalysis
from utils.logger import get_logger

def save_section_analysis(
    analysis: SectionAnalysis,
    output_path: str,
    also_json: bool = True,
    logger: Optional[Logger] = None,
) -> None:
    """Sauvegarde une analyse de section sur disque (Markdown, + JSON en option)."""
    if logger is None:
        logger = get_logger(__name__)

    md_path = Path(output_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text(analysis.to_markdown(), encoding="utf-8")
    logger.info(f"✅ Analyse de section sauvegardée dans: {md_path}")

    if also_json:
        json_path = md_path.with_suffix(".json")
        json_path.write_text(
            json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"✅ Détail structuré (JSON) sauvegardé dans: {json_path}")



def _collect_question_analyses(
    source: Union[SectionAnalysis, List[SectionAnalysis], List[QuestionAnalysis]]
) -> List[QuestionAnalysis]:
    """Normalise l'entrée en une liste plate de QuestionAnalysis."""
    if isinstance(source, SectionAnalysis):
        return list(source.question_analyses)

    if isinstance(source, list):
        if not source:
            return []
        if isinstance(source[0], SectionAnalysis):
            flat: List[QuestionAnalysis] = []
            for sa in source:
                flat.extend(sa.question_analyses)
            return flat
        if isinstance(source[0], QuestionAnalysis):
            return list(source)

    raise TypeError(
        "`source` doit être une SectionAnalysis, une List[SectionAnalysis], "
        "ou une List[QuestionAnalysis]."
    )




def build_ragas_dataset(
    source: Union[SectionAnalysis, List[SectionAnalysis], List[QuestionAnalysis]],
    ground_truths: Optional[List[str]] = None,
    as_dataset: bool = True,
) -> Union[Any, Dict[str, List[Any]]]:
    """Construit un dataset d'évaluation au format RAGAS."""
    question_analyses = _collect_question_analyses(source)
    if not question_analyses:
        raise ValueError("Aucune QuestionAnalysis trouvée dans `source`.")

    data: Dict[str, List[Any]] = {
        "question": [qa.question for qa in question_analyses],
        "answer": [qa.answer for qa in question_analyses],
        "contexts": [[c.text for c in qa.chunks] for qa in question_analyses],
    }

    if ground_truths is not None:
        if len(ground_truths) != len(question_analyses):
            raise ValueError(
                f"ground_truths contient {len(ground_truths)} élément(s), "
                f"{len(question_analyses)} attendu(s)."
            )
        data["ground_truth"] = ground_truths

    if not as_dataset:
        return data

    try:
        from datasets import Dataset
    except ImportError as e:
        raise ImportError(
            "Le package 'datasets' est requis pour construire un Dataset RAGAS. "
            "Utilisez as_dataset=False pour obtenir un dict brut à la place."
        ) from e

    return Dataset.from_dict(data)



def save_ragas_dataset(
    dataset: Union[Any, Dict[str, List[Any]]],
    output_path: str,
    logger: Optional[Logger] = None,
) -> None:
    """Sauvegarde un dataset RAGAS au format JSON."""
    if logger is None:
        from utils.logger import get_logger
        logger = get_logger(__name__)

    payload = dataset.to_dict() if hasattr(dataset, "to_dict") else dataset

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"✅ Dataset RAGAS sauvegardé dans: {path}")