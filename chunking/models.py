


from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ======================================================
#  NIVEAU DE CHUNK
# ======================================================
class ChunkType(Enum):
    """Types de chunks basés sur la hiérarchie"""
    HEADING_1 = "h1"
    HEADING_2 = "h2"
    HEADING_3 = "h3"
    HEADING_4 = "h4"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE_BLOCK = "code"
    QUOTE = "quote"
    INTRODUCTION = "introduction"
    UNSTRUCTURED = "unstructured"




@dataclass
class ChunkMetadata:
    """Métadonnées enrichies pour chaque chunk"""
    
    # Identifiants
    chunk_id: str
    parent_doc: str  # Nom du document parent (fichier source)
    
    # Source
    source_url: str = ""  # URL source (extraite de l'en-tête du markdown)
    section: str = ""  # Catégorie (extraite du markdown)
    doc_title: str = ""
    query_context: str = ""
    question: str = ""
    angle: str = ""
    
    # Structure
    heading_path: List[str] = field(default_factory=list)  # Chemin hiérarchique complet
    section_title: str = ""
    heading_level: int = 0  # Niveau du titre (0 = pas de titre, 1=h1, 2=h2, etc.)
    
    # Contenu
    chunk_type: ChunkType = ChunkType.PARAGRAPH
    content: str = ""  # Pour référence rapide
    token_count: int = 0
    character_count: int = 0  # Correction: int au lieu de int=
    
    # Éléments spéciaux
    has_code: bool = False
    has_tables: bool = False
    has_lists: bool = False
    has_numbers: bool = False  # Présence de chiffres
    has_dates: bool = False    # Présence de dates
    
    # Métadonnées temporelles
    extraction_date: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Métadonnées additionnelles (pour flexibilité)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour sérialisation JSON"""
        return {
            "chunk_id": self.chunk_id,
            "parent_doc": self.parent_doc,
            "source_url": self.source_url,
            "section": self.section,
            "doc_title": self.doc_title,
            "query_context": self.query_context,
            "question": self.question,
            "angle": self.angle,
            "heading_path": self.heading_path,
            "section_title": self.section_title,
            "heading_level": self.heading_level,
            "chunk_type": self.chunk_type.value if isinstance(self.chunk_type, ChunkType) else str(self.chunk_type),
            "content": self.content,
            "token_count": self.token_count,
            "character_count": self.character_count,
            "has_code": self.has_code,
            "has_tables": self.has_tables,
            "has_lists": self.has_lists,
            "has_numbers": self.has_numbers,
            "has_dates": self.has_dates,
            "extraction_date": self.extraction_date,
            "extra": self.extra
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkMetadata':
        """Crée une instance à partir d'un dictionnaire"""
        # Gérer le cas où chunk_type est une chaîne
        if 'chunk_type' in data and isinstance(data['chunk_type'], str):
            try:
                data['chunk_type'] = ChunkType(data['chunk_type'])
            except ValueError:
                data['chunk_type'] = ChunkType.PARAGRAPH
        
        return cls(**data)
    
    @property
    def chunk_size(self) -> int:
        """Alias pour character_count pour compatibilité"""
        return self.character_count
    
    @property
    def heading_path_str(self) -> str:
        """Retourne le chemin hiérarchique comme chaîne"""
        return ' > '.join(self.heading_path) if self.heading_path else self.section_title
    
    def get_summary(self) -> str:
        """Retourne un résumé des métadonnées"""
        return (
            f"Chunk {self.chunk_id} | "
            f"Doc: {self.parent_doc} | "
            f"Section: {self.heading_path_str} | "
            f"Type: {self.chunk_type.value} | "
            f"Tokens: {self.token_count} | "
            f"Chars: {self.character_count}"
        )




@dataclass
class Chunk:
    """Structure d'un chunk avec son contenu et métadonnées"""
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None







