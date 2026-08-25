# chunking/markdown_chunker.py
import json
import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
# from chunking.chunk_processor import ChunkProcessor
# from scraping.content_cleaner import ContentCleaner
from chunking.models import Chunk, ChunkMetadata, ChunkType
from utils.cleaner_utils import CleanerConfig
from scraping.models import ScrapingStats


class MarkdownChunker:
    """
    Chunker hiérarchique pour documents Markdown nettoyés
    Segmentation basée sur les titres et sous-titres
    """
    
    def __init__(
        self,
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
        overlap_size: int = 50,
        preserve_headers: bool = True,
        remove_empty_chunks: bool = True,
        preserve_intro: bool = True
    ):
        
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size
        self.preserve_headers = preserve_headers
        self.remove_empty_chunks = remove_empty_chunks
        self.preserve_intro = preserve_intro
        self.logger = logging.getLogger(__name__)
        
        # Patterns pour l'analyse Markdown
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.code_block_pattern = re.compile(r'```[\s\S]*?```', re.MULTILINE)
        self.table_pattern = re.compile(r'^\|.+|\|$.*', re.MULTILINE)
        self.list_pattern = re.compile(r'^[\s]*[-*+]\s+', re.MULTILINE)
        self.quote_pattern = re.compile(r'^>\s+', re.MULTILINE)
        
        # Patterns pour l'extraction des métadonnées
        self.number_pattern = re.compile(r'\d+(?:[.,]\d+)?%?|\d+(?:[.,]\d+)?\s*(?:millions?|milliards?|M|€|\$|euros?)', re.IGNORECASE)
        self.date_pattern = re.compile(r'\b(19\d{2}|20\d{2})\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b')
    
    def log(self, message: str):
        self.logger.info(message)
    
    def extract_numbers_and_dates(self, content: str) -> Tuple[bool, bool]:
        """
        Vérifie la présence de nombres et de dates dans le contenu
        """
        has_numbers = bool(self.number_pattern.search(content))
        has_dates = bool(self.date_pattern.search(content))
        return has_numbers, has_dates
    
    def parse_headings(self, content: str) -> List[Tuple[int, str, int]]:
        """Parse les titres du document"""
        headings = []
        for match in self.heading_pattern.finditer(content):
            level = len(match.group(1))
            title = match.group(2).strip()
            position = match.start()
            headings.append((level, title, position))
        
        return headings
    
    def extract_intro_section(self, content: str, first_heading_pos: int) -> Optional[str]:
        """Extrait la section d'introduction avant le premier titre"""
        if first_heading_pos > 0:
            intro_content = content[:first_heading_pos].strip()
            if intro_content and len(intro_content) > 50:
                return intro_content
        return None
    
    def extract_sections(self, content: str, headings: List[Tuple[int, str, int]]) -> List[Dict[str, Any]]:
        """
        Extrait les sections basées sur la hiérarchie des titres
        """
        sections = []
        
        if not headings:
            if len(content.strip()) >= self.min_chunk_size:
                sections.append({
                    'heading_path': [],
                    'heading_level': 0,
                    'heading_title': None,
                    'content': content,
                    'start_pos': 0,
                    'end_pos': len(content),
                    'is_intro': True
                })
            return sections
        
        # Extraire l'introduction
        first_heading_pos = headings[0][2]
        intro_content = self.extract_intro_section(content, first_heading_pos)
        
        if intro_content and self.preserve_intro:
            sections.append({
                'heading_path': ['Introduction'],
                'heading_level': 0,
                'heading_title': 'Introduction',
                'content': intro_content,
                'start_pos': 0,
                'end_pos': first_heading_pos,
                'is_intro': True
            })
        
        # Construire les sections pour chaque titre
        for i, (level, title, start_pos) in enumerate(headings):
            if i + 1 < len(headings):
                end_pos = headings[i + 1][2]
            else:
                end_pos = len(content)
            
            section_content = content[start_pos:end_pos].strip()
            
            if not section_content or len(section_content) < 10:
                continue
            
            heading_path = self._build_heading_path(headings, i)
            
            sections.append({
                'heading_path': heading_path,
                'heading_level': level,
                'heading_title': title,
                'content': section_content,
                'start_pos': start_pos,
                'end_pos': end_pos,
                'is_intro': False
            })
        
        return sections
    
    def _build_heading_path(self, headings: List[Tuple[int, str, int]], current_idx: int) -> List[str]:
        """Construit le chemin hiérarchique des titres"""
        path = []
        current_level, current_title, _ = headings[current_idx]
        
        for i in range(current_idx - 1, -1, -1):
            level, title, _ = headings[i]
            if level < current_level:
                path.insert(0, title)
                current_level = level
        
        path.append(current_title)
        return path
    
    def split_large_section(self, content: str, heading_path: List[str], heading_level: int, is_intro: bool = False) -> List[Dict[str, Any]]:
        """Divise une section trop grande en plusieurs chunks"""
        chunks = []
        
        if len(content) <= self.max_chunk_size:
            chunks.append({
                'heading_path': heading_path,
                'heading_level': heading_level,
                'section_title': heading_path[-1] if heading_path else ('Introduction' if is_intro else ''),
                'content': content,
                'is_subchunk': False,
                'is_intro': is_intro
            })
            return chunks
        
        paragraphs = content.split('\n\n')
        current_chunk = ""
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para)
            
            if para_size > self.max_chunk_size:
                if current_chunk:
                    chunks.append({
                        'heading_path': heading_path,
                        'heading_level': heading_level,
                        'section_title': heading_path[-1] if heading_path else ('Introduction' if is_intro else ''),
                        'content': current_chunk.strip(),
                        'is_subchunk': True,
                        'is_intro': is_intro
                    })
                    current_chunk = ""
                    current_size = 0
                
                sub_chunks = self._split_by_sentences(para)
                for sub_chunk in sub_chunks:
                    if sub_chunk.strip():
                        chunks.append({
                            'heading_path': heading_path,
                            'heading_level': heading_level,
                            'section_title': heading_path[-1] if heading_path else ('Introduction' if is_intro else ''),
                            'content': sub_chunk,
                            'is_subchunk': True,
                            'is_intro': is_intro
                        })
                continue
            
            if current_size + para_size + 2 <= self.max_chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                    current_size += para_size + 2
                else:
                    current_chunk = para
                    current_size = para_size
            else:
                if current_chunk:
                    chunks.append({
                        'heading_path': heading_path,
                        'heading_level': heading_level,
                        'section_title': heading_path[-1] if heading_path else ('Introduction' if is_intro else ''),
                        'content': current_chunk.strip(),
                        'is_subchunk': True,
                        'is_intro': is_intro
                    })
                current_chunk = para
                current_size = para_size
        
        if current_chunk:
            chunks.append({
                'heading_path': heading_path,
                'heading_level': heading_level,
                'section_title': heading_path[-1] if heading_path else ('Introduction' if is_intro else ''),
                'content': current_chunk.strip(),
                'is_subchunk': True,
                'is_intro': is_intro
            })
        
        return chunks
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Divise un texte en phrases pour le chunking fin"""
        sentence_pattern = re.compile(r'[^.!?]+[.!?]+', re.MULTILINE)
        sentences = sentence_pattern.findall(text)
        
        if not sentences:
            words = text.split()
            chunks = []
            current_chunk = ""
            for word in words:
                if len(current_chunk) + len(word) + 1 <= self.max_chunk_size:
                    current_chunk += " " + word if current_chunk else word
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = word
            if current_chunk:
                chunks.append(current_chunk)
            return chunks
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text[:self.max_chunk_size]]
    
    def classify_chunk_type(self, content: str, is_intro: bool = False) -> ChunkType:
        """Classifie le type de chunk basé sur son contenu"""
        if is_intro:
            return ChunkType.INTRODUCTION
        
        if self.code_block_pattern.search(content):
            return ChunkType.CODE_BLOCK
        elif self.table_pattern.search(content):
            return ChunkType.TABLE
        elif self.list_pattern.search(content):
            return ChunkType.LIST
        elif self.quote_pattern.search(content):
            return ChunkType.QUOTE
        elif re.match(r'^#{1,6}\s+', content, re.MULTILINE):
            first_line = content.split('\n')[0]
            if first_line.startswith('#'):
                level = len(re.match(r'^#+', first_line).group())
                return ChunkType(f"h{level}") if level <= 4 else ChunkType.PARAGRAPH
            return ChunkType.PARAGRAPH
        else:
            if len(content.split('\n')) > 3 and len(content) > 200:
                return ChunkType.UNSTRUCTURED
            return ChunkType.PARAGRAPH
    
    def create_chunk_metadata(
        self,
        chunk_content: str,
        doc_metadata: Dict[str, Any],
        heading_path: List[str],
        section_title: str,
        heading_level: int,
        is_intro: bool = False,
        chunk_index: int = 0,
        total_chunks: int = 1
    ) -> ChunkMetadata:
        """Crée les métadonnées enrichies pour un chunk à partir des métadonnées du document"""
        
        # Générer un ID unique pour le chunk
        content_hash = hashlib.md5(f"{doc_metadata.get('url', '')}{section_title}{chunk_content[:100]}".encode()).hexdigest()[:16]
        chunk_id = f"{content_hash}_{chunk_index}" if total_chunks > 1 else content_hash
        
        token_count = len(chunk_content.split())
        character_count = len(chunk_content)
        
        # Détection des éléments spéciaux
        has_code = bool(self.code_block_pattern.search(chunk_content))
        has_tables = bool(self.table_pattern.search(chunk_content))
        has_lists = bool(self.list_pattern.search(chunk_content))
        has_numbers, has_dates = self.extract_numbers_and_dates(chunk_content)
        
        reading_time = token_count / 200.0
        
        # Construction du chemin de section complet
        full_section = ' > '.join(heading_path) if heading_path else section_title
        
        return ChunkMetadata(
            chunk_id=chunk_id,
            parent_doc=doc_metadata.get('title', 'unknown'),
            source_url=doc_metadata.get('url', ''),
            section=doc_metadata.get('section', 'unknown'),
            question=doc_metadata.get('question', ''),
            query_context=doc_metadata.get('query', ''),
            angle=doc_metadata.get('angle', ''),
            heading_path=heading_path,
            section_title=section_title,
            heading_level=heading_level,
            chunk_type=self.classify_chunk_type(chunk_content, is_intro),
            content=chunk_content[:500],  # Extrait pour métadonnées
            token_count=token_count,
            character_count=character_count,
            has_code=has_code,
            has_tables=has_tables,
            has_lists=has_lists,
            has_numbers=has_numbers,
            has_dates=has_dates,
            extraction_date=doc_metadata.get('scraped_at', ''),
        )
    
    def chunk_single_document(
        self,
        document: Dict[str, Any]
    ) -> List[Chunk]:
        """
        Découpe un document Markdown unique avec ses métadonnées
        
        Args:
            document: Dictionnaire contenant 'content' et 'metadata'
                {
                    'content': 'markdown content',
                    'metadata': {
                        'url': '...',
                        'title': '...',
                        'section': '...',
                        'angle': '...',
                        'question': '...',
                        'query': '...',
                        'scraped_at': '...',
                        'scraping_duration_seconds': ...,
                        'status': 'success'
                    }
                }
        
        Returns:
            List[Chunk]: Liste des chunks générés
        """
        
        content = document.get('content', '')
        doc_metadata = document.get('metadata', {})
        
        title = doc_metadata.get('title', 'unknown')
        self.log(f"Découpage du document: {title}")
        
        if not content or len(content.strip()) < 10:
            self.log(f"  ⚠️ Contenu vide ou trop court pour: {title}")
            return []
        
        headings = self.parse_headings(content)
        self.log(f"  - {len(headings)} titres identifiés")
        
        sections = self.extract_sections(content, headings)
        self.log(f"  - {len(sections)} sections extraites")
        
        all_chunks = []
        chunk_counter = 0
        
        for section in sections:
            section_content = section['content']
            heading_path = section['heading_path']
            heading_level = section['heading_level']
            section_title = section['heading_title'] if section['heading_title'] else (heading_path[-1] if heading_path else '')
            is_intro = section.get('is_intro', False)
            
            if not section_content or (self.remove_empty_chunks and len(section_content) < 20 and not is_intro):
                continue
            
            if len(section_content) > self.max_chunk_size:
                self.log(f"    Section '{section_title or 'intro'}' divisée")
                sub_chunks = self.split_large_section(section_content, heading_path, heading_level, is_intro)
                
                for sub_chunk in sub_chunks:
                    sub_content = sub_chunk['content']
                    sub_section_title = sub_chunk.get('section_title', section_title)
                    
                    metadata = self.create_chunk_metadata(
                        chunk_content=sub_content,
                        doc_metadata=doc_metadata,
                        heading_path=heading_path,
                        heading_level=heading_level,
                        section_title=sub_section_title,
                        is_intro=is_intro,
                        chunk_index=chunk_counter,
                        total_chunks=len(sub_chunks) if len(sub_chunks) > 1 else 1
                    )
                    
                    min_size = 20 if is_intro else self.min_chunk_size
                    if not self.remove_empty_chunks or len(sub_content) >= min_size:
                        all_chunks.append(Chunk(
                            content=sub_content,
                            metadata=metadata
                        ))
                        chunk_counter += 1
            else:
                metadata = self.create_chunk_metadata(
                    chunk_content=section_content,
                    doc_metadata=doc_metadata,
                    heading_path=heading_path,
                    heading_level=heading_level,
                    section_title=section_title,
                    is_intro=is_intro,
                    chunk_index=chunk_counter,
                    total_chunks=1
                )
                
                min_size = 20 if is_intro else self.min_chunk_size
                if not self.remove_empty_chunks or len(section_content) >= min_size:
                    all_chunks.append(Chunk(
                        content=section_content,
                        metadata=metadata
                    ))
                    chunk_counter += 1
        
        self.log(f"  - {len(all_chunks)} chunks générés pour: {title}")
        
        if all_chunks:
            avg_size = sum(len(c.content) for c in all_chunks) / len(all_chunks)
            self.log(f"    Taille moyenne: {avg_size:.0f} caractères")
        
        return all_chunks
    
    def chunk_documents(
        self,
        documents: List[Dict[str, Any]],
        output_dir: Optional[str] = None,
        save_output: bool = False
    ) -> Dict[str, List[Chunk]]:
        """
        Découpe une liste de documents Markdown avec leurs métadonnées
        
        Args:
            documents: Liste de dictionnaires contenant 'content' et 'metadata'
            output_dir: Répertoire de sortie pour sauvegarder les chunks (optionnel)
            save_output: Sauvegarder les chunks sur disque
        
        Returns:
            Dict[str, List[Chunk]]: Dictionnaire avec les titres des documents comme clés
        """
        
        self.log(f"📁 Traitement de {len(documents)} documents")
        
        all_results = {}
        
        for idx, doc in enumerate(documents):
            try:
                doc_title = doc.get('metadata', {}).get('title', f'document_{idx}')
                chunks = self.chunk_single_document(doc)
                
                if chunks:
                    all_results[doc_title] = chunks
                    
                    if save_output and output_dir:
                        self._save_chunks(chunks, doc_title, output_dir)
                else:
                    self.log(f"⚠️ Aucun chunk généré pour: {doc_title}")
                    
            except Exception as e:
                doc_title = doc.get('metadata', {}).get('title', f'document_{idx}')
                self.log(f"❌ Erreur avec {doc_title}: {str(e)}")
        
        return all_results
    
    def _save_chunks(self, chunks: List[Chunk], doc_title: str, output_dir: str):
        """Sauvegarde les chunks avec leurs métadonnées enrichies"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Nettoyer le titre pour le nom de fichier
        safe_title = re.sub(r'[^\w\s-]', '', doc_title).strip().replace(' ', '_')
        
        # Sauvegarder les chunks consolidés
        chunks_data = []
        for chunk in chunks:
            chunks_data.append({
                "chunk_id": chunk.metadata.chunk_id,
                "content": chunk.content,
                "metadata": chunk.metadata.to_dict()
            })
        
        # Sauvegarder en JSON
        output_file = output_path / f"{safe_title}_chunks.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=4)
        
        self.log(f"  💾 Chunks sauvegardés: {output_file}")
        
        # Sauvegarder chaque chunk individuellement
        chunks_dir = output_path 
        chunks_dir.mkdir(exist_ok=True)
        path=output_path / f"{safe_title}_chunks.txt"
        with open(path, 'a', encoding='utf-8') as f:
                for chunk in chunks:
                #     chunk_file = chunks_dir / f"{chunk.metadata.chunk_id}.txt"
                        f.write("\n\n\n\n"+"================================================================================")
                        f.write(f"# Source URL: {chunk.metadata.source_url}\n")
                        f.write(f"# Document parent: {chunk.metadata.parent_doc}\n")
                        f.write(f"# Section: {chunk.metadata.section}\n")
                        f.write(f"# Question: {chunk.metadata.question}\n")
                        f.write(f"# Query: {chunk.metadata.query_context}\n")
                        f.write(f"# Angle: {chunk.metadata.angle}\n")
                        f.write(f"# Chemin hiérarchique: {' > '.join(chunk.metadata.heading_path)}\n")
                        f.write(f"# Titre section: {chunk.metadata.section_title}\n")
                        f.write(f"# Type: {chunk.metadata.chunk_type.value}\n")
                        f.write(f"# Taille: {chunk.metadata.character_count} caractères\n")
                        f.write(f"# Tokens: {chunk.metadata.token_count}\n")
                        f.write(f"# Contient chiffres: {chunk.metadata.has_numbers}\n")
                        f.write(f"# Contient dates: {chunk.metadata.has_dates}\n")
                        f.write(f"# Scrapé le: {chunk.metadata.extraction_date}\n")
                        f.write( "."*80 + "\n\n")
                        f.write(chunk.content)


def quick_chunk_documents(
    documents: List[Dict[str, Any]], 
    output_dir: str = "data/chunks", 
    max_chunk_size: int = 800,
    save_output: bool = True
) -> Dict[str, List[Chunk]]:
    """
    Fonction rapide pour chunker des documents avec leurs métadonnées
    
    Args:
        documents: Liste de dictionnaires avec 'content' et 'metadata'
        output_dir: Répertoire de sortie
        max_chunk_size: Taille maximale des chunks
        save_output: Sauvegarder les chunks sur disque
    
    Returns:
        Dict[str, List[Chunk]]: Résultats du chunking
    """
    chunker = MarkdownChunker(
        max_chunk_size=max_chunk_size, 
        preserve_intro=True
    )
    return chunker.chunk_documents(
        documents=documents,
        output_dir=output_dir,
        save_output=save_output
    )

