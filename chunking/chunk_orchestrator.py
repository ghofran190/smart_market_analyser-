# chunking/chunk_orchestrator.py
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from chunking.markdown_chunker import MarkdownChunker, Chunk, ChunkMetadata, ChunkType
from chunking.chunk_processor import ChunkProcessor
from chunking.utils import (
    cleaning_result_to_document,
    log_results,
    save_consolidated_chunks,
)
from scraping.models import CleaningResult
from config import ChunkerConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class ChunkOrchestrator:
    """
    Orchestrateur pour le pipeline complet de chunking.
    Gère le découpage, le traitement et l'export des chunks.
    """

    def __init__(self, config: ChunkerConfig):
        self.chunker = MarkdownChunker(
            max_chunk_size=config.max_chunk_size,
            min_chunk_size=config.min_chunk_size,
            overlap_size=config.overlap_size,
            preserve_headers=config.preserve_headers,
            preserve_intro=config.preserve_intro,
            remove_empty_chunks=config.remove_empty_chunks
            )
        self.processor = ChunkProcessor(
            min_quality_score=config.min_quality_score,
            min_tokens=config.min_tokens,
            max_tokens=config.max_tokens,
            min_chunk_size=config.min_chunk_size
        )
        self.logger = logger
        self.config = config

    def log(self, message: str):
        self.logger.info(message)

    def _process_chunks_pipeline(
        self,
        all_chunks: List[Chunk],
        output_dir: Path,
        save_output: bool,
        generate_report: bool,
        document_name: str = "all_documents",
        chunks_by_key: Optional[Dict[str, List[Chunk]]] = None
    ) -> Dict[str, Any]:
        if not all_chunks:
            self.log("⚠️ Aucun chunk généré")
            return {
                "chunks_by_doc": chunks_by_key or {},
                "all_chunks": [],
                "total_chunks": 0,
                "output_dir": str(output_dir)
            }

        self.log(f"📊 {len(all_chunks)} chunks générés au total")

        processed_result = self.processor.process_chunks(
            chunks=all_chunks,
            filter_enabled=True,
            merge_enabled=True,
            generate_report_enabled=generate_report,
            output_dir=str(output_dir) if save_output else None,
            document_name=document_name
        )

        filtered_chunks = processed_result["chunks"]
        validation = processed_result["validation"]
        stats = processed_result["statistics"]

        if save_output:
            save_consolidated_chunks(filtered_chunks, output_dir, include_metadata=True)

        return {
            "chunks_by_doc": chunks_by_key or {},
            "all_chunks": filtered_chunks,
            "total_chunks": len(filtered_chunks),
            "validation": validation,
            "statistics": stats,
            "output_dir": str(output_dir),
            "chunks_file": None,
            "config": self.config,
            "processed_result": processed_result
        }

    def process_documents(
        self,
        cleaning_results: List[CleaningResult],
        project_dir: Optional[str] = None,
        save_output: bool = True,
        generate_report: bool = True
    ) -> Dict[str, Any]:
        """
        Traite une liste de CleaningResult (sortie du module de nettoyage).

        Args:
            cleaning_results: Liste de CleaningResult (output de ContentCleaner)
            project_dir: Répertoire du projet pour sauvegarder les résultats
            save_output: Sauvegarder les chunks sur disque
            generate_report: Générer un rapport détaillé

        Returns:
            Dict[str, Any]: Résultats du traitement
        """
        successful = [r for r in cleaning_results if r.success]
        failed = [r for r in cleaning_results if not r.success]

        if not successful:
            raise ValueError("Aucun document nettoyé à traiter")

        if failed:
            self.log(f"⚠️ {len(failed)} résultat(s) de nettoyage échoué(s) ignoré(s)")

        documents = [
            cleaning_result_to_document(r) for r in successful
        ]

        if project_dir:
            output_dir = Path(project_dir) / "chunks"
        else:
            output_dir = Path("data/chunks")
        output_dir.mkdir(parents=True, exist_ok=True)

        self.log("=" * 80)
        self.log("🚀 DÉMARRAGE DU CHUNKING HIÉRARCHIQUE")
        self.log("=" * 80)
        self.log(f"📁 Documents à traiter: {len(documents)}")
        self.log(f"📁 Répertoire de sortie: {output_dir}")
        self.log("")

        all_chunks_by_doc = self.chunker.chunk_documents(
            documents=documents,
            output_dir=str(output_dir) if save_output else None,
            save_output=save_output
        )

        all_chunks = []
        for doc_chunks in all_chunks_by_doc.values():
            all_chunks.extend(doc_chunks)

        result = self._process_chunks_pipeline(
            all_chunks=all_chunks,
            output_dir=output_dir,
            save_output=save_output,
            generate_report=generate_report,
            document_name="all_documents",
            chunks_by_key=all_chunks_by_doc
        )

        log_results(
            total_docs=len(all_chunks_by_doc),
            total_chunks=len(all_chunks),
            filtered_chunks=result["all_chunks"],
            validation=result["validation"]
        )

        return result

    def process_directory(
        self,
        clean_files: List[str],
        project_dir: str,
        save_output: bool = True,
        generate_report: bool = True
    ) -> Dict[str, Any]:
        """
        Traite tous les fichiers Markdown d'un répertoire (méthode legacy).

        Args:
            clean_files: Liste des chemins vers les fichiers markdown nettoyés
            project_dir: Répertoire du projet
            save_output: Sauvegarder les chunks sur disque
            generate_report: Générer un rapport détaillé

        Returns:
            Dict[str, Any]: Résultats du traitement
        """
        if not clean_files:
            raise ValueError("Aucun fichier à traiter")

        output_dir = Path(project_dir) / "chunks"
        output_dir.mkdir(parents=True, exist_ok=True)

        self.log("=" * 80)
        self.log("🚀 DÉMARRAGE DU CHUNKING (MODE FICHIERS)")
        self.log("=" * 80)
        self.log(f"📁 Fichiers à traiter: {len(clean_files)}")
        self.log(f"📁 Répertoire de sortie: {output_dir}")
        self.log("")

        all_chunks_by_file = self.chunker.chunk_directory(
            clean_files=clean_files,
            project_dir=project_dir
        )

        all_chunks = []
        for file_chunks in all_chunks_by_file.values():
            all_chunks.extend(file_chunks)

        result = self._process_chunks_pipeline(
            all_chunks=all_chunks,
            output_dir=output_dir,
            save_output=save_output,
            generate_report=generate_report,
            document_name="all_documents",
            chunks_by_key=all_chunks_by_file
        )

        log_results(
            total_docs=len(all_chunks_by_file),
            total_chunks=len(all_chunks),
            filtered_chunks=result["all_chunks"],
            validation=result["validation"]
        )

        return result

    def get_chunks_for_rag(
        self,
        chunks_file: Optional[str] = None,
        chunks: Optional[List[Chunk]] = None
    ) -> List[Dict[str, Any]]:
        rag_chunks = []

        if chunks:
            for chunk in chunks:
                rag_chunks.append({
                    "id": chunk.metadata.chunk_id,
                    "text": chunk.content,
                    "metadata": {
                        "source": chunk.metadata.source_url,
                        "doc_title": chunk.metadata.doc_title,
                        "section": chunk.metadata.section,
                        "question": chunk.metadata.question,
                        "angle": chunk.metadata.angle,
                        "heading_path": ' > '.join(chunk.metadata.heading_path),
                        "chunk_type": chunk.metadata.chunk_type.value
                        if isinstance(chunk.metadata.chunk_type, ChunkType)
                        else str(chunk.metadata.chunk_type),
                        "token_count": chunk.metadata.token_count
                    }
                })

        elif chunks_file:
            chunks_file = Path(chunks_file)
            if not chunks_file.exists():
                raise FileNotFoundError(f"Fichier de chunks non trouvé: {chunks_file}")

            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data:
                rag_chunks.append({
                    "id": item.get("chunk_id", ""),
                    "text": item.get("content", ""),
                    "metadata": {
                        "source": item.get("source_url", ""),
                        "doc_title": item.get("doc_title", ""),
                        "section": item.get("section", ""),
                        "question": item.get("question", ""),
                        "angle": item.get("angle", ""),
                        "heading_path": ' > '.join(item.get("heading_path", [])),
                        "chunk_type": item.get("chunk_type", ""),
                        "token_count": item.get("token_count", 0)
                    }
                })

        return rag_chunks

    def export_chunks_to_jsonl(
        self,
        chunks: List[Chunk],
        output_file: str
    ) -> Path:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                entry = {
                    "id": chunk.metadata.chunk_id,
                    "text": chunk.content,
                    "metadata": {
                        "source_url": chunk.metadata.source_url,
                        "doc_title": chunk.metadata.doc_title,
                        "section": chunk.metadata.section,
                        "question": chunk.metadata.question,
                        "angle": chunk.metadata.angle,
                        "query_context": chunk.metadata.query_context,
                        "heading_path": ' > '.join(chunk.metadata.heading_path),
                        "section_title": chunk.metadata.section_title,
                        "heading_level": chunk.metadata.heading_level,
                        "chunk_type": chunk.metadata.chunk_type.value
                        if isinstance(chunk.metadata.chunk_type, ChunkType)
                        else str(chunk.metadata.chunk_type),
                        "token_count": chunk.metadata.token_count,
                        "character_count": chunk.metadata.character_count,
                        "has_numbers": chunk.metadata.has_numbers,
                        "has_dates": chunk.metadata.has_dates,
                        "extraction_date": chunk.metadata.extraction_date
                    }
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self.log(f"💾 Chunks exportés en JSONL: {output_path}")
        return output_path

