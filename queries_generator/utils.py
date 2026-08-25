
from datetime import datetime
import json
import re
from zipfile import Path
from queries_generator.models import AnalysisOutput, SearchQuery

from utils import logger





# ============================================================================
# Utilities
# ============================================================================


def _sanitize_json_escapes(raw: str) -> str:
    r"""
    Fix invalid backslash escapes produced by less reliable LLMs.

    JSON only allows \" \\ \/ \b \f \n \r \t \uXXXX after a backslash.
    Any other \X (e.g. \%, \-, \(, \e) gets its backslash escaped so
    it becomes a literal backslash instead of breaking the parser.
    """
    valid_escapes = set('"\\/bfnrtu')

    def fix(match: re.Match) -> str:
        char = match.group(1)
        if char in valid_escapes:
            return match.group(0)
        return "\\\\" + char

    return re.sub(r"\\(.)", fix, raw)


def parse_search_queries(raw: str) -> list["SearchQuery"]:
    """Shared, defensive parser for LLM-generated query JSON."""
    original = raw
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    data = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass

    if not data:
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.warning("First JSON parse failed (%s); attempting escape repair", e)
                try:
                    data = json.loads(_sanitize_json_escapes(match.group(0)))
                except json.JSONDecodeError:
                    pass

    if not data:
        lines = raw.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                items = json.loads(line)
                if isinstance(items, list):
                    data.extend(items)
                else:
                    data.append(items)
            except json.JSONDecodeError:
                continue

    if not data:
        logger.error("Could not parse LLM output as JSON.\nRAW OUTPUT:\n%s", original)
        raise ValueError(f"Could not parse LLM output as JSON.\nRAW OUTPUT:\n{original}")

    return [
        SearchQuery(
            query=item["query"],
            angle=item.get("angle", ""),
            relevance_score=float(item.get("relevance_score", 0.8)),
        )
        for item in data
    ]




# ============================================================================
# Output Helpers
# ============================================================================


def print_output(output: AnalysisOutput) -> None:
    print(f"\n{'═'*70}")
    print(f"  SECTION: {output.section}")
    print(f"{'═'*70}")
    for i, qq in enumerate(output.question_queries, 1):
        print(f"\n❓ Question {i}: {qq.question}")
        print(f"{'─'*60}")
        for j, q in enumerate(qq.queries, 1):
            print(f"  {j}. [{q.relevance_score:.2f}] {q.query}")
            print(f"       Angle: {q.angle}")
    print()




def save_output(output: AnalysisOutput, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    section_slug = output.section.lower().replace(" ", "_")[:30]
    path = output_dir / f"{section_slug}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"✓ Output saved → {path}")
    return path





