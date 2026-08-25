"""
ReportSynthesisAgent — combines expert section analyses into a
complete, coherent, and professional market research report.

Usage:
    synthesizer = ReportSynthesisAgent(llm_client=llm_client, logger=logger)
    report = synthesizer.synthesize([macro, demand, competition, swot])
    report.save("data/reports/market_report.md")
"""

import json
import logging
from utils.logger import get_logger
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clients import APIClients, OpenRouterConfig

from .models import SectionAnalysis

logger = get_logger(__name__)
# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class SynthesisSection:
    """A section of the synthesized report with its title and content."""

    title: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"title": self.title, "content": self.content}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SynthesisSection":
        return cls(
            title=str(data.get("title", "")).strip(),
            content=str(data.get("content", "")).strip(),
        )


@dataclass
class ReportSynthesisResult:
    """Complete synthesized market research report."""

    project_info: Dict[str, Any]
    sections: List[SynthesisSection]
    retrieval_method: str = "M4c"
    generated_at: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime

        if not self.generated_at:
            self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_info": self.project_info,
            "retrieval_method": self.retrieval_method,
            "generated_at": self.generated_at,
            "sections": [s.to_dict() for s in self.sections],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append("# Rapport d'analyse de marché — SaaS Hospitality")
        lines.append("")
        lines.append(f"**Date de génération:** {self.generated_at}")
        lines.append(f"**Méthode de récupération:** {self.retrieval_method}")
        lines.append("")

        for k, v in self.project_info.items():
            lines.append(f"- **{k}:** {v}")

        lines.append("")
        lines.append("---")
        lines.append("")

        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def save(
        self,
        output_path: str,
        also_json: bool = True,
        logger: Optional[logging.Logger] = logger,
    ) -> None:
        save_synthesis_report(self, output_path, also_json=also_json, logger=logger)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportSynthesisResult":
        sections = [
            SynthesisSection.from_dict(s) for s in data.get("sections", [])
        ]
        return cls(
            project_info=data.get("project_info", {}),
            sections=sections,
            retrieval_method=str(data.get("retrieval_method", "M4c")).strip(),
            generated_at=str(data.get("generated_at", "")).strip(),
        )

    @classmethod
    def failed(cls, reason: str) -> "ReportSynthesisResult":
        return cls(
            project_info={},
            sections=[
                SynthesisSection(
                    title="Erreur de synthèse",
                    content=f"La génération du rapport a échoué : {reason}",
                )
            ],
        )


# ============================================================================
# PERSISTENCE
# ============================================================================


def save_synthesis_report(
    result: ReportSynthesisResult,
    output_path: str,
    also_json: bool = True,
    logger: Optional[logging.Logger] = logger,
) -> None:
    """Save a synthesis report to disk (Markdown + optional JSON)."""
    if logger is None:
        logger = logging.getLogger(__name__)

    md_path = Path(output_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text(result.to_markdown(), encoding="utf-8")
    logger.info(f"✅ Rapport de synthèse sauvegardé dans: {md_path}")

    if also_json:
        json_path = md_path.with_suffix(".json")
        json_path.write_text(result.to_json(), encoding="utf-8")
        logger.info(f"✅ Détail structuré (JSON) sauvegardé dans: {json_path}")


# ============================================================================
# REPORT SYNTHESIS AGENT
# ============================================================================


class ReportSynthesisAgent:
    """
    Combines expert section analyses into a complete, coherent,
    and professional market research report.

    Inputs:
        - Project information
        - Macro-Market Analysis
        - Demand Analysis
        - Competition Analysis
        - SWOT Analysis

    Output:
        A well-structured Markdown report with evaluation metrics.
    """

    def __init__(
        self,
        llm_client: OpenRouterConfig,
        logger: Optional[logging.Logger] = logger,
        max_llm_retries: int = 2,
        max_chars_per_section: int = 4000,
    ):
        self.llm_client = llm_client
        self.logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.max_llm_retries = max_llm_retries
        self.max_chars_per_section = max_chars_per_section

    def synthesize(
        self,
        sections: List[SectionAnalysis],
        output_path: Optional[str] = None,
        also_markdown: bool = True,
    ) -> ReportSynthesisResult:
        """
        Synthesize expert analyses into a complete market research report.

        Args:
            sections: list of SectionAnalysis objects (macro, demand, competition, swot).
            output_path: optional path to save the report.
            also_markdown: also save a Markdown version.

        Returns:
            ReportSynthesisResult with the full report.
        """
        section_map = {s.section_name: s for s in sections}
        required = ["macro_marche", "demande_et_pain_points", "offre_et_competition", "swot"]
        missing = [s for s in required if s not in section_map]
        if missing:
            self.logger.warning(
                f"ReportSynthesisAgent: sections manquantes: {missing}. "
                f"Disponibles: {list(section_map.keys())}"
            )

        project_info = sections[0].project_info if sections else {}
        retrieval_method = sections[0].retrieval_method if sections else "M4c"

        system, user = self._build_synthesis_prompt(sections)
        result: Optional[ReportSynthesisResult] = None

        for attempt in range(1, self.max_llm_retries + 2):
            raw = self._call_llm(system, user)
            if not raw:
                continue

            parsed = self._try_parse_report(raw)
            if parsed is not None:
                result = parsed
                break

            self.logger.warning(
                f"ReportSynthesisAgent: réponse non-parseable "
                f"(tentative {attempt}/{self.max_llm_retries + 1}), nouvelle tentative..."
            )

        if result is None:
            self.logger.error("ReportSynthesisAgent: échec définitif de la synthèse.")
            result = ReportSynthesisResult.failed(
                "Le LLM n'a pas renvoyé un rapport structuré valide."
            )

        if output_path:
            result.save(output_path, logger=self.logger)

        return result

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_synthesis_prompt(
        self, sections: List[SectionAnalysis]
    ) -> Tuple[str, str]:
        system = (
            "Tu es un consultant senior en études de marché spécialisé dans le secteur "
            "SaaS . Ton rôle est de combiner les analyses de quatre experts "
            "(Macro-Marché, Demande & Pain Points, Offre & Concurrence, SWOT) en un rapport "
            "cohérent, professionnel et actionnable pour des entrepreneurs lançant un business "
            "SaaS dans le secteur de l'hôtellerie.\n\n"
            "Règles strictes :\n"
            "1. N'invente AUCUN fait, chiffre ou conclusion non présent dans les analyses fournies.\n"
            "2. Harmonise les termes et les chiffres entre les sections (pas de contradictions).\n"
            "3. Élimine la redondance — ne copie pas bêtement le contenu original.\n"
            "4. Produis des insights stratégiques fondés sur les preuves des analyses.\n"
            "5. Les recommandations doivent être evidence-based, pas arbitraires.\n"
            "6. Le style doit être professionnel, fluide et non répétitif.\n"
            "7. Le rapport est destiné à des entrepreneurs lançant un SaaS.\n\n"
            "Tu dois répondre STRICTEMENT avec un objet JSON valide au format EXACT :\n\n"
            "{\n"
            '  "project_info": { ... },\n'
            '  "sections": {\n'
            '    "executive_summary": "texte...",\n'
            '    "project_overview": "texte...",\n'
            '    "macro_market": "texte...",\n'
            '    "demand_analysis": "texte...",\n'
            '    "competition_analysis": "texte...",\n'
            '    "swot_strengths": "texte...",\n'
            '    "swot_weaknesses": "texte...",\n'
            '    "swot_opportunities": "texte...",\n'
            '    "swot_threats": "texte...",\n'
            '    "strategic_insights": "texte...",\n'
            '    "recommendations": "texte...",\n'
            '    "conclusion": "texte..."\n'
            "  }\n"
            "}\n\n"
            "Règles importantes :\n"
            "- Chaque section doit faire 150-400 mots.\n"
            "- L'Executive Summary doit faire 200-300 mots et synthétiser les points clés.\n"
            "- Les recommandations doivent être numérotées et directement liées aux analyses.\n"
            "- Ne retourne AUCUN texte en dehors du JSON."
        )

        blocks = []
        for section in sections:
            qa_lines = "\n".join(
                f"- Q: {qa.question}\n  R: {qa.answer[:self.max_chars_per_section]}"
                for qa in section.question_analyses
            )
            block = (
                f"### Section: {section.section_name}\n\n"
                f"**Synthèse:**\n{section.synthesis[:self.max_chars_per_section]}\n\n"
                f"**Réponses détaillées:**\n{qa_lines if qa_lines else '(aucune)'}"
            )
            blocks.append(block)

        user = (
            "## Informations projet\n"
            + "\n".join(f"- **{k}:** {v}" for k, v in (sections[0].project_info if sections else {}).items())
            + "\n\n"
            "## Analyses expertes à synthétiser\n\n"
            + "\n\n---\n\n".join(blocks)
            + "\n\n## Consigne\n"
            "Combine ces quatre analyses en un rapport de marché cohérent et professionnel. "
            "Utilise UNIQUEMENT les informations fournies. Assure-toi que les conclusions "
            "sont cohérentes d'une section à l'autre et que les recommandations sont "
            "directement soutenues par les analyses."
        )
        return system, user

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM with retry logic."""
        last_error = None
        attempts = self.max_llm_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                result = self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=6000,
                )
                if result and result.strip():
                    return result.strip()
                raise ValueError("Réponse LLM vide")
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"ReportSynthesisAgent: LLM call failed "
                    f"(attempt {attempt}/{attempts}): {e}"
                )
                if attempt < attempts:
                    time.sleep(min(2 ** attempt, 8))

        self.logger.error(
            f"ReportSynthesisAgent: LLM call failed after {attempts} attempts: {last_error}"
        )
        return ""

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _try_parse_report(self, raw: str) -> Optional[ReportSynthesisResult]:
        """Extract a valid JSON object from raw LLM response and build ReportSynthesisResult."""
        candidate = raw.strip()
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()

        parsed = None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            pass

        if parsed is None:
            match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None

        if parsed is None or not isinstance(parsed, dict):
            return None

        project_info = parsed.get("project_info", {})
        if not isinstance(project_info, dict):
            project_info = {}

        raw_sections = parsed.get("sections", {})
        if not isinstance(raw_sections, dict):
            return None

        section_titles = {
            "executive_summary": "Résumé exécutif",
            "project_overview": "Aperçu du projet",
            "macro_market": "Analyse Macro-Marché",
            "demand_analysis": "Analyse de la Demande",
            "competition_analysis": "Analyse de la Concurrence",
            "swot_strengths": "SWOT — Forces",
            "swot_weaknesses": "SWOT — Faiblesses",
            "swot_opportunities": "SWOT — Opportunités",
            "swot_threats": "SWOT — Menaces",
            "strategic_insights": "Insights Stratégiques",
            "recommendations": "Recommandations",
            "conclusion": "Conclusion",
        }

        sections = []
        for key, title in section_titles.items():
            content = raw_sections.get(key, "")
            if isinstance(content, str) and content.strip():
                sections.append(SynthesisSection(title=title, content=content.strip()))

        retrieval_method = str(parsed.get("retrieval_method", "M4c")).strip()

        return ReportSynthesisResult(
            project_info=project_info,
            sections=sections,
            retrieval_method=retrieval_method,
        )


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def synthesize_report(
    sections: List[SectionAnalysis],
    llm_client: OpenRouterConfig,
    logger: Optional[logging.Logger] = logger,
    max_llm_retries: int = 2,
    output_path: Optional[str] = None,
    also_markdown: bool = True,
) -> Dict[str, Any]:
    """
    Shortcut: synthesize section analyses into a report and return a serializable dict.

    Example:
        result = synthesize_report(
            [macro, demand, competition, swot],
            llm_client=llm_client,
            output_path="data/reports/market_report.md",
        )
    """
    synthesizer = ReportSynthesisAgent(
        llm_client=llm_client,
        logger=logger,
        max_llm_retries=max_llm_retries,
    )
    return synthesizer.synthesize(
        sections, output_path=output_path, also_markdown=also_markdown
    ).to_dict()












# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":
    from .models import QuestionAnalysis

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    macro = SectionAnalysis(
        section_name="macro_marche",
        project_info={"product": "PMS SaaS", "market": "Hospitality"},
        question_analyses=[
            QuestionAnalysis(
                question="Taille du marché ?",
                refined_queries=[],
                chunks=[],
                answer="Marché estimé à 50M€ en 2024, CAGR 12%.",
            )
        ],
        synthesis="Le marché des PMS SaaS pour l'hôtellerie en France est estimé à 50M€ en 2024, avec un CAGR de 12%.",
    )

    demand = SectionAnalysis(
        section_name="demande_et_pain_points",
        project_info={"product": "PMS SaaS", "market": "Hospitality"},
        question_analyses=[
            QuestionAnalysis(
                question="Quels sont les pain points des hôteliers ?",
                refined_queries=[],
                chunks=[],
                answer="Les hôteliers indépendants souffrent de la fragmentation des outils et du manque de tarification dynamique.",
            )
        ],
        synthesis="Les hôteliers indépendants ont besoin d'outils intégrés et de tarification dynamique.",
    )

    competition = SectionAnalysis(
        section_name="offre_et_competition",
        project_info={"product": "PMS SaaS", "market": "Hospitality"},
        question_analyses=[
            QuestionAnalysis(
                question="Quels sont les principaux concurrents ?",
                refined_queries=[],
                chunks=[],
                answer="Mews, Cloudbeds, Amenitiz, Oracle Hospitality, Fols/Misterbooking.",
            )
        ],
        synthesis="Le marché est dominé par Mews, Cloudbeds, Amenitiz, Oracle Hospitality et Fols.",
    )

    swot = SectionAnalysis(
        section_name="swot",
        project_info={"product": "PMS SaaS", "market": "Hospitality"},
        question_analyses=[
            QuestionAnalysis(
                question="Quelles sont les forces du projet ?",
                refined_queries=[],
                chunks=[],
                answer="Intégration cloud native, pricing dynamique, API ouverte.",
            )
        ],
        synthesis="## Forces\n- Cloud native, pricing dynamique, API ouverte\n\n## Faiblesses\n- Marque peu connue\n\n## Opportunités\n- Marché en croissance 12% CAGR\n\n## Menaces\n- Concurrents établis",
    )

    llm_client = APIClients().lm_client
    synthesizer = ReportSynthesisAgent(llm_client=llm_client, logger=logger)

    report = synthesizer.synthesize(
        [macro, demand, competition, swot],
        output_path="data/reports/market_report.md",
    )

    print("\n📋 Rapport de synthèse :")
    print(report.to_json())