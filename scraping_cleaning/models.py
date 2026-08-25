



from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScrapingStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    files: List[str] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)
    urls_scraped: List[str] = field(default_factory=list)
    contents: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "files": self.files,
            "durations": self.durations,
            "urls_scraped": self.urls_scraped,
            "contents": self.contents
        }  




@dataclass
class CleaningResult:
    file_name: str
    original_content: str
    cleaned_content: str
    metadata: Dict[str, Any]
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "file_name": self.file_name,
            "original_content": self.original_content,
            "cleaned_content": self.cleaned_content,
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: object) -> bool:
        return hasattr(self, key)

    def keys(self):
        return ["file_name", "original_content", "cleaned_content", "metadata", "success", "error"]

    def items(self):
        return [(k, getattr(self, k)) for k in self.keys()]

    def get(self, key: str, default=None):
        return getattr(self, key, default)