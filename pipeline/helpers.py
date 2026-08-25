# ============================================================================
# Helpers
# ============================================================================

from dataclasses import asdict
import re
from typing import Any, Dict



def slugify(text: str, max_length: int = 40) -> str:
    """Transforme un texte en identifiant safe pour nom de dossier/collection."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_length] or "project"


def project_info_to_dict(project_info: Any) -> Dict[str, Any]:
    """Convertit un ProjectInfo en dict JSON-compatible."""
    data = asdict(project_info)

    list_fields = [
        "personas",
        "primary_keywords",
        "secondary_keywords",
        "potential_competitors",
    ]

    for field in list_fields:
        value = data.get(field)

        if value is None:
            data[field] = []
            continue

        if isinstance(value, str):
            if "\n" in value:
                data[field] = [
                    item.strip("-• ").strip()
                    for item in value.splitlines()
                    if item.strip()
                ]
            else:
                data[field] = [
                    item.strip()
                    for item in value.split(",")
                    if item.strip()
                ]

    return data
