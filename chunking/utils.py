# chunking/utils.py
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from chunking.models import Chunk, ChunkType
from scraping_cleaning.models import CleaningResult
from utils.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    'cleaning_result_to_document',
    'log_results',
    'save_consolidated_chunks',
]


# ------------------------------------------------------------------
# Conversion
# ------------------------------------------------------------------

def cleaning_result_to_document(result: CleaningResult) -> Dict[str, Any]:
    return {
        "content": result.cleaned_content,
        "metadata": result.metadata
    }


# ------------------------------------------------------------------
# Logging et reporting
# ------------------------------------------------------------------

def log_results(
    total_docs: int,
    total_chunks: int,
    filtered_chunks: List[Chunk],
    validation: Dict[str, Any]
) -> None:
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ CHUNKING TERMINÉ")
    logger.info("=" * 80)
    logger.info("📊 Résultats:")
    logger.info(f"   - Documents traités: {total_docs}")
    logger.info(f"   - Chunks générés: {total_chunks}")
    logger.info(f"   - Chunks conservés: {len(filtered_chunks)}")
    logger.info(f"   - Score qualité: {validation['quality_score']:.1f}/100")
    logger.info(
        "   - Validation: "
        f"{'✅ OK' if validation['valid'] else '⚠️ Problèmes'}"
    )

    if validation.get('issues'):
        logger.info(f"   - Problèmes: {', '.join(validation['issues'])}")
    if validation.get('warnings'):
        logger.info(f"   - Avertissements: {', '.join(validation['warnings'])}")


# ------------------------------------------------------------------
# Export / sauvegarde
# ------------------------------------------------------------------

def save_consolidated_chunks(
    chunks: List[Chunk],
    output_dir: Path,
    include_metadata: bool = True
) -> Path:
    consolidated = []

    for chunk in chunks:
        chunk_data = {
            "chunk_id": chunk.metadata.chunk_id,
            "content": chunk.content,
        }

        if include_metadata:
            chunk_data["metadata"] = {
                "parent_doc": chunk.metadata.parent_doc,
                "doc_title": chunk.metadata.doc_title,
                "source_url": chunk.metadata.source_url,
                "section": chunk.metadata.section,
                "question": chunk.metadata.question,
                "query_context": chunk.metadata.query_context,
                "angle": chunk.metadata.angle,
                "heading_path": chunk.metadata.heading_path,
                "section_title": chunk.metadata.section_title,
                "heading_level": chunk.metadata.heading_level,
                "chunk_type": (
                    chunk.metadata.chunk_type.value
                    if isinstance(chunk.metadata.chunk_type, ChunkType)
                    else str(chunk.metadata.chunk_type)
                ),
                "token_count": chunk.metadata.token_count,
                "character_count": chunk.metadata.character_count,
                "has_code": chunk.metadata.has_code,
                "has_tables": chunk.metadata.has_tables,
                "has_lists": chunk.metadata.has_lists,
                "has_numbers": chunk.metadata.has_numbers,
                "has_dates": chunk.metadata.has_dates,
                "extraction_date": chunk.metadata.extraction_date
            }

        consolidated.append(chunk_data)

    json_file = output_dir / (
        f"all_chunks_consolidated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(consolidated, f, ensure_ascii=False, indent=4)

    logger.info(f"💾 Chunks consolidés (JSON): {json_file}")

    text_file = output_dir / (
        f"all_chunks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CHUNKS CONSOLIDÉS - EXPORT POUR RAG\n")
        f.write(f"Date: {datetime.now().isoformat()}\n")
        f.write(f"Total chunks: {len(chunks)}\n")
        f.write("=" * 80 + "\n\n")

        for i, chunk in enumerate(chunks, 1):
            f.write(f"\n{'=' * 80}\n")
            f.write(f"CHUNK #{i}\n")
            f.write(f"ID: {chunk.metadata.chunk_id}\n")
            f.write(
                f"Document: {chunk.metadata.doc_title or chunk.metadata.parent_doc}\n"
            )
            f.write(f"Source: {chunk.metadata.source_url}\n")
            f.write(f"Section: {chunk.metadata.section}\n")
            f.write(f"Question: {chunk.metadata.question}\n")
            f.write(f"Angle: {chunk.metadata.angle}\n")
            f.write(f"Chemin: {' > '.join(chunk.metadata.heading_path)}\n")
            chunk_type = (
                chunk.metadata.chunk_type.value
                if isinstance(chunk.metadata.chunk_type, ChunkType)
                else str(chunk.metadata.chunk_type)
            )
            f.write(f"Type: {chunk_type}\n")
            f.write(f"\nTokens: {chunk.metadata.token_count}\n")
            f.write(f"Caractères: {chunk.metadata.character_count}\n")
            f.write("-" * 80 + "\n")
            f.write(chunk.content)
            f.write("\n")

    logger.info(f"💾 Chunks texte: {text_file}")

    rag_file = output_dir / (
        f"all_chunks_rag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    with open(rag_file, 'w', encoding='utf-8') as f:
        for chunk in chunks:
            rag_entry = {
                "id": chunk.metadata.chunk_id,
                "text": chunk.content,
                "metadata": {
                    "source_url": chunk.metadata.source_url,
                    "doc_title": chunk.metadata.doc_title,
                    "section": chunk.metadata.section,
                    "question": chunk.metadata.question,
                    "angle": chunk.metadata.angle,
                    "heading_path": ' > '.join(chunk.metadata.heading_path),
                    "chunk_type": (
                        chunk.metadata.chunk_type.value
                        if isinstance(chunk.metadata.chunk_type, ChunkType)
                        else str(chunk.metadata.chunk_type)
                    ),
                    "token_count": chunk.metadata.token_count
                }
            }
            f.write(json.dumps(rag_entry, ensure_ascii=False) + "\n")

    logger.info(f"💾 Chunks format RAG (JSONL): {rag_file}")

    return json_file




def save_results_to_markdown(
    results: List[Dict[str, Any]],
    query: str,
    collection_name: str,
    output_file: str = "search_results.md"
) -> str:
    """Sauvegarde les résultats de recherche dans un fichier Markdown."""
    from datetime import datetime
    from pathlib import Path
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    md_content = []
    
    # En-tête
    md_content.append(f"# 🔍 Résultats de Recherche ChromaDB")
    md_content.append(f"")
    md_content.append(f"**Collection:** `{collection_name}`")
    md_content.append(f"**Requête:** {query}")
    md_content.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_content.append(f"**Nombre de résultats:** {len(results)}")
    md_content.append(f"")
    md_content.append("---")
    md_content.append(f"")
    
    if not results:
        md_content.append("❌ **Aucun résultat trouvé**")
        md_content.append("")
        md_content.append("Veuillez essayer avec une autre requête ou vérifier que la collection contient des documents.")
    else:
        # Calcul des statistiques
        scores = [r['score'] for r in results]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        
        # Calcul de l'écart-type
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        
        md_content.append("## 📊 Statistiques")
        md_content.append(f"")
        md_content.append(f"- **Score moyen:** {avg_score:.4f}")
        md_content.append(f"- **Score maximum:** {max_score:.4f}")
        md_content.append(f"- **Score minimum:** {min_score:.4f}")
        md_content.append(f"- **Écart-type:** {std_dev:.4f}")
        md_content.append(f"")
        md_content.append("---")
        md_content.append(f"")
        
        # Résultats détaillés
        md_content.append("## 📄 Résultats Détaillés")
        md_content.append(f"")
        
        for i, r in enumerate(results, 1):
            # Score avec barre de progression visuelle
            score_percent = int(r['score'] * 100)
            bar_length = 20
            filled = int(score_percent / 5)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            md_content.append(f"### Résultat {i}")
            md_content.append(f"")
            md_content.append(f"**ID:** `{r['id']}`")
            md_content.append(f"")
            md_content.append(f"**Score:** `{r['score']:.4f}`  `{score_percent}%`  `[{bar}]`")
            md_content.append(f"")
            
            # Texte complet
            md_content.append(f"**Texte:**")
            md_content.append(f"")
            md_content.append(f"> {r['text']}")
            md_content.append(f"")
            
            # Métadonnées
            if r.get('metadata'):
                md_content.append(f"**Métadonnées:**")
                md_content.append(f"")
                md_content.append("| Clé | Valeur |")
                md_content.append("|-----|-------|")
                for key, value in r['metadata'].items():
                    if value:
                        md_content.append(f"| {key} | {value} |")
                md_content.append(f"")
            
            # Source
            source = r['metadata'].get('source_url', r['metadata'].get('source_file', 'N/A'))
            md_content.append(f"**Source:** `{source}`")
            md_content.append(f"")
            
            if i < len(results):
                md_content.append("---")
                md_content.append(f"")
    
    # Pied de page
    md_content.append("---")
    md_content.append(f"")
    md_content.append(f"*Rapport généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    md_content.append(f"*Système: ChromaDB avec BGE-M3*")
    
    # Écrire le fichier
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))
    
    print(f"✅ Résultats sauvegardés dans: {output_path}")
    return str(output_path)






