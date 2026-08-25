# chunking/chunk_processor.py
import json
import logging
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from chunking.markdown_chunker import Chunk, ChunkMetadata, ChunkType


class ChunkProcessor:
    """
    Processeur de chunks: validation, filtrage, statistiques, fusion
    """
    
    def __init__(
        self, 
        min_quality_score: float = 0.3,
        min_tokens: int = 20,
        max_tokens: int = 2000,
        min_chunk_size: int = 50
    ):
        self.min_quality_score = min_quality_score
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.min_chunk_size = min_chunk_size
        self.logger = logging.getLogger(__name__)
        
        # Patterns pour la détection de contenu générique
        self.generic_patterns = [
            r'menu|navigation|cookie|consent',
            r'subscribe|newsletter|footer|copyright',
            r'terms of service|privacy policy|all rights reserved',
            r'click here|read more|learn more|sign up',
            r'advertisement|sponsored|promotion'
        ]
        self.generic_regex = re.compile('|'.join(self.generic_patterns), re.IGNORECASE)
    
    def log(self, message: str):
        self.logger.info(message)
    
    def filter_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Filtre les chunks de faible qualité
        
        Args:
            chunks: Liste des chunks à filtrer
            
        Returns:
            List[Chunk]: Liste filtrée
        """
        filtered = []
        removed_count = 0
        
        for chunk in chunks:
            # Vérifier la taille minimale
            if chunk.metadata.token_count < self.min_tokens:
                removed_count += 1
                continue
            
            # Vérifier le contenu (pas trop de bruit)
            content_lower = chunk.content.lower()
            
            # Exclure les chunks trop génériques
            is_generic = False
            
            # Vérifier les patterns génériques
            if self.generic_regex.search(content_lower):
                # Compter les occurrences
                matches = len(self.generic_regex.findall(content_lower))
                if matches > 2:
                    is_generic = True
            
            # Vérifier si le chunk contient du contenu significatif
            has_substance = (
                len(chunk.content.split()) > 10 and
                any(char.isdigit() for char in chunk.content) or
                any(char in '?!' for char in chunk.content) or
                len(set(chunk.content.split())) > 5
            )
            
            if not is_generic and has_substance:
                filtered.append(chunk)
            else:
                removed_count += 1
        
        self.log(f"Filtrage: {len(chunks)} -> {len(filtered)} chunks (éliminé {removed_count})")
        
        return filtered
    
    def merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Fusionne les chunks trop petits avec le précédent ou le suivant
        
        Args:
            chunks: Liste des chunks à fusionner
            
        Returns:
            List[Chunk]: Liste avec les chunks fusionnés
        """
        if not chunks:
            return []
        
        merged = []
        i = 0
        
        while i < len(chunks):
            chunk = chunks[i]
            
            # Si le chunk est trop petit et qu'il y a un suivant
            if chunk.metadata.token_count < self.min_tokens and i + 1 < len(chunks):
                next_chunk = chunks[i + 1]
                
                # Fusionner avec le suivant
                merged_content = chunk.content + "\n\n" + next_chunk.content
                
                # Créer un nouveau chunk avec les métadonnées combinées
                combined_metadata = ChunkMetadata(
                    chunk_id=f"{chunk.metadata.chunk_id}_{next_chunk.metadata.chunk_id}",
                    parent_doc=chunk.metadata.parent_doc,
                    source_url=chunk.metadata.source_url,
                    section=chunk.metadata.section,
                    doc_title=chunk.metadata.doc_title,
                    query_context=chunk.metadata.query_context,
                    question=chunk.metadata.question,
                    angle=chunk.metadata.angle,
                    heading_path=chunk.metadata.heading_path,
                    section_title=chunk.metadata.section_title,
                    heading_level=chunk.metadata.heading_level,
                    chunk_type=chunk.metadata.chunk_type,
                    content=merged_content[:500],
                    token_count=chunk.metadata.token_count + next_chunk.metadata.token_count,
                    character_count=chunk.metadata.character_count + next_chunk.metadata.character_count,
                    has_code=chunk.metadata.has_code or next_chunk.metadata.has_code,
                    has_tables=chunk.metadata.has_tables or next_chunk.metadata.has_tables,
                    has_lists=chunk.metadata.has_lists or next_chunk.metadata.has_lists,
                    has_numbers=chunk.metadata.has_numbers or next_chunk.metadata.has_numbers,
                    has_dates=chunk.metadata.has_dates or next_chunk.metadata.has_dates
                )
                
                merged.append(Chunk(
                    content=merged_content,
                    metadata=combined_metadata
                ))
                
                i += 2  # Passer les deux chunks fusionnés
            else:
                merged.append(chunk)
                i += 1
        
        self.log(f"Fusion: {len(chunks)} -> {len(merged)} chunks (fusionné {len(chunks)-len(merged)})")
        
        return merged
    
    def compute_statistics(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Calcule des statistiques sur les chunks
        
        Args:
            chunks: Liste des chunks
            
        Returns:
            Dict[str, Any]: Statistiques détaillées
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "error": "No chunks",
                "chunk_types": {},
                "heading_levels": {}
            }
        
        # Statistiques de base
        total_tokens = sum(c.metadata.token_count for c in chunks)
        total_chars = sum(c.metadata.character_count for c in chunks)
        avg_tokens = total_tokens / len(chunks)
        avg_chars = total_chars / len(chunks)
        
        # Distribution des types
        chunk_types = defaultdict(int)
        heading_levels = defaultdict(int)
        sections = defaultdict(int)
        
        # Métadonnées spéciales
        has_code_count = 0
        has_tables_count = 0
        has_lists_count = 0
        has_numbers_count = 0
        has_dates_count = 0
        
        for chunk in chunks:
            # Types
            chunk_type = chunk.metadata.chunk_type.value if isinstance(chunk.metadata.chunk_type, ChunkType) else str(chunk.metadata.chunk_type)
            chunk_types[chunk_type] += 1
            
            # Niveaux de titre
            heading_levels[chunk.metadata.heading_level] += 1
            
            # Sections
            section = chunk.metadata.section or "unknown"
            sections[section] += 1
            
            # Contenu spécial
            if chunk.metadata.has_code:
                has_code_count += 1
            if chunk.metadata.has_tables:
                has_tables_count += 1
            if chunk.metadata.has_lists:
                has_lists_count += 1
            if chunk.metadata.has_numbers:
                has_numbers_count += 1
            if chunk.metadata.has_dates:
                has_dates_count += 1
        
        # Calcul des percentiles
        token_counts = sorted([c.metadata.token_count for c in chunks])
        
        stats = {
            "total_chunks": len(chunks),
            "total_tokens": total_tokens,
            "total_characters": total_chars,
            "avg_tokens_per_chunk": avg_tokens,
            "avg_characters_per_chunk": avg_chars,
            "min_tokens": token_counts[0] if token_counts else 0,
            "max_tokens": token_counts[-1] if token_counts else 0,
            "median_tokens": token_counts[len(token_counts)//2] if token_counts else 0,
            "percentile_25": token_counts[len(token_counts)//4] if len(token_counts) >= 4 else 0,
            "percentile_75": token_counts[3*len(token_counts)//4] if len(token_counts) >= 4 else 0,
            "chunk_types": dict(chunk_types),
            "heading_levels": dict(heading_levels),
            "sections": dict(sections),
            "has_code_count": has_code_count,
            "has_tables_count": has_tables_count,
            "has_lists_count": has_lists_count,
            "has_numbers_count": has_numbers_count,
            "has_dates_count": has_dates_count,
            "unique_documents": len(set(c.metadata.parent_doc for c in chunks)),
            "unique_sections": len(set(c.metadata.section for c in chunks)),
            "unique_questions": len(set(c.metadata.question for c in chunks if c.metadata.question)),
            "unique_angles": len(set(c.metadata.angle for c in chunks if c.metadata.angle))
        }
        
        return stats
    
    def validate_chunks(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Valide la qualité des chunks
        
        Args:
            chunks: Liste des chunks à valider
            
        Returns:
            Dict[str, Any]: Résultats de la validation
        """
        validation = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "quality_score": 100.0,
            "stats": {}
        }
        
        if not chunks:
            validation["valid"] = False
            validation["issues"].append("Aucun chunk généré")
            validation["quality_score"] = 0
            return validation
        
        # Statistiques pour référence
        stats = self.compute_statistics(chunks)
        validation["stats"] = stats
        
        # Vérifier la taille des chunks
        too_small = [c for c in chunks if c.metadata.token_count < self.min_tokens]
        too_large = [c for c in chunks if c.metadata.token_count > self.max_tokens]
        
        if too_small:
            validation["issues"].append(f"{len(too_small)} chunks trop petits (<{self.min_tokens} tokens)")
        
        if too_large:
            validation["warnings"].append(f"{len(too_large)} chunks trop grands (>{self.max_tokens} tokens)")
        
        # Vérifier la diversité des types
        chunk_types = set(c.metadata.chunk_type.value if isinstance(c.metadata.chunk_type, ChunkType) else str(c.metadata.chunk_type) for c in chunks)
        if len(chunk_types) < 2 and len(chunks) > 5:
            validation["warnings"].append(f"Faible diversité des types: {chunk_types}")
        
        # Vérifier les métadonnées manquantes
        missing_metadata = []
        for field in ['section', 'source_url', 'doc_title']:
            missing = sum(1 for c in chunks if not getattr(c.metadata, field, None))
            if missing > len(chunks) * 0.5:  # Plus de 50% manquant
                validation["warnings"].append(f"{missing}/{len(chunks)} chunks sans {field}")
        
        # Vérifier le contenu
        empty_content = [c for c in chunks if not c.content or len(c.content.strip()) < 10]
        if empty_content:
            validation["issues"].append(f"{len(empty_content)} chunks avec contenu vide")
        
        # Calcul du score de qualité (0-100)
        quality = 100.0
        
        # Pénalités pour les chunks trop petits
        if too_small:
            penalty = min(30, len(too_small) / len(chunks) * 50)
            quality -= penalty
        
        # Pénalités pour les chunks trop grands
        if too_large:
            penalty = min(20, len(too_large) / len(chunks) * 30)
            quality -= penalty
        
        # Pénalité pour contenu vide
        if empty_content:
            penalty = min(20, len(empty_content) / len(chunks) * 40)
            quality -= penalty
        
        # Bonus pour la diversité
        if len(chunk_types) >= 3:
            quality = min(100, quality + 5)
        
        validation["quality_score"] = max(0, min(100, quality))
        validation["valid"] = len(validation["issues"]) == 0
        
        return validation
    
    def generate_report(
        self, 
        chunks: List[Chunk], 
        output_dir: str,
        document_name: Optional[str] = None
    ) -> str:
        """
        Génère un rapport détaillé sur le chunking
        
        Args:
            chunks: Liste des chunks
            output_dir: Répertoire de sortie
            document_name: Nom du document (optionnel)
            
        Returns:
            str: Rapport en texte
        """
        if not chunks:
            report = "Aucun chunk à analyser"
            self.log(f"⚠️ {report}")
            return report
        
        stats = self.compute_statistics(chunks)
        validation = self.validate_chunks(chunks)
        
        report_lines = []
        report_lines.append("="*80)
        report_lines.append("RAPPORT DE CHUNKING")
        report_lines.append("="*80)
        report_lines.append(f"Date: {datetime.now().isoformat()}")
        if document_name:
            report_lines.append(f"Document: {document_name}")
        report_lines.append("")
        
        # Statistiques globales
        report_lines.append("📊 STATISTIQUES GLOBALES:")
        report_lines.append("-"*40)
        report_lines.append(f"Total chunks: {stats['total_chunks']:,}")
        report_lines.append(f"Total tokens: {stats['total_tokens']:,}")
        report_lines.append(f"Total caractères: {stats['total_characters']:,}")
        report_lines.append(f"Moyenne tokens/chunk: {stats['avg_tokens_per_chunk']:.1f}")
        report_lines.append(f"Moyenne caractères/chunk: {stats['avg_characters_per_chunk']:.0f}")
        report_lines.append(f"Médiane tokens: {stats['median_tokens']}")
        report_lines.append(f"Min tokens: {stats['min_tokens']}")
        report_lines.append(f"Max tokens: {stats['max_tokens']}")
        report_lines.append("")
        
        # Métadonnées
        report_lines.append("📝 MÉTADONNÉES:")
        report_lines.append("-"*40)
        report_lines.append(f"Documents uniques: {stats['unique_documents']}")
        report_lines.append(f"Sections uniques: {stats['unique_sections']}")
        report_lines.append(f"Questions uniques: {stats['unique_questions']}")
        report_lines.append(f"Angles uniques: {stats['unique_angles']}")
        report_lines.append("")
        
        # Répartition par type
        report_lines.append("📂 RÉPARTITION PAR TYPE:")
        report_lines.append("-"*40)
        for chunk_type, count in sorted(stats['chunk_types'].items(), key=lambda x: -x[1]):
            percentage = count / stats['total_chunks'] * 100
            bar = "█" * int(percentage / 5)  # Barre de progression simple
            report_lines.append(f"  {chunk_type:15} {count:4} ({percentage:5.1f}%) {bar}")
        report_lines.append("")
        
        # Répartition par niveau de titre
        report_lines.append("📑 RÉPARTITION PAR NIVEAU DE TITRE:")
        report_lines.append("-"*40)
        for level, count in sorted(stats['heading_levels'].items()):
            if level > 0:
                percentage = count / stats['total_chunks'] * 100
                report_lines.append(f"  Niveau {level}: {count} ({percentage:.1f}%)")
        report_lines.append("")
        
        # Contenu spécial
        report_lines.append("🔍 CONTENU SPÉCIAL:")
        report_lines.append("-"*40)
        report_lines.append(f"  Avec code:      {stats['has_code_count']}")
        report_lines.append(f"  Avec tableaux:  {stats['has_tables_count']}")
        report_lines.append(f"  Avec listes:    {stats['has_lists_count']}")
        report_lines.append(f"  Avec chiffres:  {stats['has_numbers_count']}")
        report_lines.append(f"  Avec dates:     {stats['has_dates_count']}")
        report_lines.append("")
        
        # Validation
        report_lines.append("✅ VALIDATION:")
        report_lines.append("-"*40)
        report_lines.append(f"Qualité: {validation['quality_score']:.1f}/100")
        report_lines.append(f"Statut: {'✅ VALIDE' if validation['valid'] else '⚠️ PROBLÈMES'}")
        
        if validation['issues']:
            report_lines.append("  ❌ Issues:")
            for issue in validation['issues']:
                report_lines.append(f"     - {issue}")
        
        if validation['warnings']:
            report_lines.append("  ⚠️ Warnings:")
            for warning in validation['warnings']:
                report_lines.append(f"     - {warning}")
        
        report_lines.append("")
        report_lines.append("="*80)
        
        # Sauvegarder le rapport
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        report_filename = f"chunking_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        if document_name:
            safe_name = re.sub(r'[^\w\s-]', '', document_name).strip().replace(' ', '_')
            report_filename = f"chunking_report_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        report_path = output_path / report_filename
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        
        # Sauvegarder les stats en JSON
        stats_filename = f"chunking_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        if document_name:
            safe_name = re.sub(r'[^\w\s-]', '', document_name).strip().replace(' ', '_')
            stats_filename = f"chunking_stats_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        stats_path = output_path / stats_filename
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        
        self.log(f"📄 Rapport sauvegardé: {report_path}")
        self.log(f"📊 Statistiques sauvegardées: {stats_path}")
        
        return "\n".join(report_lines)
    
    def process_chunks(
        self, 
        chunks: List[Chunk],
        filter_enabled: bool = True,
        merge_enabled: bool = True,
        generate_report_enabled: bool = True,
        output_dir: Optional[str] = None,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pipeline complet de traitement des chunks
        
        Args:
            chunks: Liste des chunks à traiter
            filter_enabled: Activer le filtrage
            merge_enabled: Activer la fusion
            generate_report_enabled: Générer un rapport
            output_dir: Répertoire de sortie
            document_name: Nom du document
            
        Returns:
            Dict[str, Any]: Résultats du traitement
        """
        self.log(f"🔄 Traitement de {len(chunks)} chunks")
        
        result = {
            "original_count": len(chunks),
            "filtered_count": 0,
            "merged_count": 0,
            "final_count": 0,
            "chunks": chunks,
            "validation": None,
            "statistics": None,
            "report": None
        }
        
        # Étape 1: Filtrage
        if filter_enabled:
            chunks = self.filter_chunks(chunks)
            result["filtered_count"] = len(chunks)
        
        # Étape 2: Fusion
        if merge_enabled:
            chunks = self.merge_small_chunks(chunks)
            result["merged_count"] = len(chunks)
        
        result["final_count"] = len(chunks)
        result["chunks"] = chunks
        
        # Étape 3: Validation
        result["validation"] = self.validate_chunks(chunks)
        
        # Étape 4: Statistiques
        result["statistics"] = self.compute_statistics(chunks)
        
        # Étape 5: Rapport
        if generate_report_enabled and output_dir:
            result["report"] = self.generate_report(
                chunks=chunks,
                output_dir=output_dir,
                document_name=document_name
            )
        
        self.log(f"✅ Traitement terminé: {result['final_count']} chunks finaux")
        
        return result


# Fonction utilitaire pour un traitement rapide
def quick_process_chunks(
    chunks: List[Chunk],
    output_dir: str = "data/chunks",
    document_name: Optional[str] = None,
    filter_enabled: bool = True,
    merge_enabled: bool = True
) -> Dict[str, Any]:
    """
    Traitement rapide des chunks avec configuration par défaut
    
    Args:
        chunks: Liste des chunks à traiter
        output_dir: Répertoire de sortie
        document_name: Nom du document
        filter_enabled: Activer le filtrage
        merge_enabled: Activer la fusion
        
    Returns:
        Dict[str, Any]: Résultats du traitement
    """
    processor = ChunkProcessor()
    return processor.process_chunks(
        chunks=chunks,
        filter_enabled=filter_enabled,
        merge_enabled=merge_enabled,
        generate_report_enabled=True,
        output_dir=output_dir,
        document_name=document_name
    )