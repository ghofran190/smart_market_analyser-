"""
Modèles de données (dataclasses) pour l'analyse de section.

Ces classes sont volontairement "anémiques" côté logique métier
(pas d'appel LLM ni de retrieval ici) : elles ne font que représenter
et sérialiser l'état, ce qui les rend faciles à tester isolément.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Dict, List, Optional



@dataclass
class SubQueryHyde:
    """Une sous-requête associée à sa réponse hypothétique (technique HyDE)."""

    sub_query: str
    hyde_answer: str
    source_url: Optional[str] = None


@dataclass
class QuestionInput:
    """Une question principale avec ses sous-requêtes HyDE associées."""

    question: str
    sub_queries: List[SubQueryHyde] = field(default_factory=list)



@dataclass
class QuestionAnalysis:
    """Résultat du traitement d'une question."""

    question: str
    refined_queries: List[str]
    chunks: List[Any]  # NormalizedResult ou MergedHybridResult
    answer: str
    retrieval_strategy: str = "hybrid"
    retrieval_method: str = "M1"
    evaluation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "refined_queries": self.refined_queries,
            "chunks": [c.to_dict() for c in self.chunks] if self.chunks else [],
            "answer": self.answer,
            "retrieval_strategy": self.retrieval_strategy,
            "retrieval_method": self.retrieval_method,
            "evaluation": self.evaluation,
        }



@dataclass
class SectionAnalysis:
    """Résultat complet de l'analyse d'une section du rapport."""

    section_name: str
    project_info: Dict[str, Any]
    question_analyses: List[QuestionAnalysis]
    synthesis: str
    retrieval_strategy: str = "hybrid"
    retrieval_method: str = "M1"
    evaluation: Optional[Dict[str, Any]] = None
    generated_at: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Exporte l'analyse de section en Markdown."""
        lines = [
            f"# Analyse de section — {self.section_name}",
            "",
            f"**Date:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Stratégie de recherche:** {self.retrieval_strategy.upper()}",
            f"**Méthode de récupération:** {self.retrieval_method}",
            "",
            "## 📋 Informations projet",
            "",
        ]
        for k, v in self.project_info.items():
            lines.append(f"- **{k}:** {v}")

        lines.extend(["", "---", "", "## ❓ Réponses aux questions clés", ""])
        for i, qa in enumerate(self.question_analyses, 1):
            lines.extend(
                [
                    f"### Question {i} — {qa.question}",
                    "",
                    qa.answer,
                    "",
                    f"*Récupération : {len(qa.chunks)} chunk(s) via {len(qa.refined_queries)} "
                    f"requête(s) raffinée(s) ({qa.retrieval_strategy}, méthode {qa.retrieval_method}).*",
                    "",
                ]
            )

        lines.extend(["---", "", "## 🧩 Synthèse de la section", "", self.synthesis, ""])

        if self.evaluation:
            lines.extend(["---", "", "## 📊 Évaluation de la récupération", ""])
            eval_data = self.evaluation
            lines.append(f"- **Score composite:** {eval_data.get('composite_score', 'N/A')}")
            lines.append(f"- **Relevance:** {eval_data.get('relevance_score', 'N/A')}")
            lines.append(f"- **Coverage:** {eval_data.get('coverage_score', 'N/A')}")
            lines.append(f"- **Diversity:** {eval_data.get('diversity_score', 'N/A')}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_name": self.section_name,
            "project_info": self.project_info,
            "generated_at": self.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "retrieval_strategy": self.retrieval_strategy,
            "retrieval_method": self.retrieval_method,
            "evaluation": self.evaluation,
            "question_analyses": [qa.to_dict() for qa in self.question_analyses],
            "synthesis": self.synthesis,
        }

    def save(
        self,
        output_path: str,
        also_json: bool = True,
        logger: Optional[Any] = None,
    ) -> None:
        """Sauvegarde l'analyse de section sur disque (délègue à persistence.py)."""
        # Import local pour éviter un cycle d'import (persistence importe models).
        from .Persistence import save_section_analysis

        save_section_analysis(self, output_path, also_json=also_json, logger=logger)




# ============================================================================
# MODÈLES DE RÉSULTAT DE REWIEWER
# ============================================================================




VALID_STATUSES = {"ok", "needs_revision"}
VALID_SEVERITIES = {"low", "medium", "high"}

# Statut de repli utilisé quand le LLM ne renvoie rien d'exploitable.
_FALLBACK_CORRECTION = (
    "La réponse du LLM n'a pas pu être interprétée comme du JSON valide. "
    "Une revue manuelle des sections est requise."
)






@dataclass
class Contradiction:
    """Une contradiction détectée entre deux sections."""

    issue: str
    section1: str
    section2: str
    severity: str = "medium"

    def to_dict(self) -> Dict[str, str]:
        return {
            "issue": self.issue,
            "section1": self.section1,
            "section2": self.section2,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contradiction":
        severity = str(data.get("severity", "medium")).strip().lower()
        if severity not in VALID_SEVERITIES:
            severity = "medium"
        return cls(
            issue=str(data.get("issue", "")).strip(),
            section1=str(data.get("section1", "")).strip(),
            section2=str(data.get("section2", "")).strip(),
            severity=severity,
        )





@dataclass
class CoherenceReviewResult:
    """Résultat validé de la revue de cohérence."""

    status: str
    contradictions: List[Contradiction] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "corrections": list(self.corrections),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CoherenceReviewResult":
        """Construit et VALIDE le résultat à partir d'un dict brut (issu du LLM)."""
        status = str(data.get("status", "needs_revision")).strip().lower()
        if status not in VALID_STATUSES:
            status = "needs_revision"

        raw_contradictions = data.get("contradictions") or []
        contradictions = [
            Contradiction.from_dict(c) for c in raw_contradictions if isinstance(c, dict)
        ]

        raw_corrections = data.get("corrections") or []
        corrections = [str(c).strip() for c in raw_corrections if str(c).strip()]

        # Garde-fou de cohérence interne : s'il y a des contradictions,
        # le statut ne peut pas rester "ok".
        if contradictions and status == "ok":
            status = "needs_revision"

        return cls(status=status, contradictions=contradictions, corrections=corrections)


    @classmethod
    def failed(cls, reason: str) -> "CoherenceReviewResult":
        """Résultat de repli en cas d'échec (parsing ou appel LLM)."""
        return cls(status="needs_revision", contradictions=[], corrections=[reason])

