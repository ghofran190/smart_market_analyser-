"""
Section Analysis Agent — package public API.

Ce package regroupe l'analyse de section (macro-marché, demande,
concurrence, SWOT) avec une stratégie de récupération dynamique
configurable (M1 à M4c).

Organisation:
    - Retrieval_strategy.py : configuration de la stratégie de récupération
    - models.py              : structures de données (dataclasses)
    - Persistence.py         : sauvegarde disque + export RAGAS
    - base_agent.py          : classe abstraite BaseSectionAgent (pipeline complet)
    - Agents.py              : agents concrets (Macro, Demande, Concurrence, SWOT)
    - main.py                : script de démonstration / point d'entrée CLI
"""

from .Retrieval_strategy import RetrievalStrategy
from .models import SubQueryHyde, QuestionInput, QuestionAnalysis, SectionAnalysis
from .Persistence  import (
    save_section_analysis,
    build_ragas_dataset,
    save_ragas_dataset,
)
from .base_agent import BaseSectionAgent
from .Agents import (
    MacroAgent,
    DemandAgent,
    CompetitionAgent,
    SwotAgent,
    SECTION_AGENTS,
    get_section_agent,
)
from .report_synthesis_agent import ReportSynthesisAgent, synthesize_report
from .report_evaluator import ReportSynthesisEvaluator, evaluate_synthesis

__all__ = [
    "RetrievalStrategy",
    "SubQueryHyde",
    "QuestionInput",
    "QuestionAnalysis",
    "SectionAnalysis",
    "save_section_analysis",
    "build_ragas_dataset",
    "save_ragas_dataset",
    "BaseSectionAgent",
    "MacroAgent",
    "DemandAgent",
    "CompetitionAgent",
    "SwotAgent",
    "SECTION_AGENTS",
    "get_section_agent",
    "ReportSynthesisAgent",
    "synthesize_report",
    "ReportSynthesisEvaluator",
    "evaluate_synthesis",
]