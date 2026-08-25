"""
Module de nettoyage de contenu Markdown pour systèmes RAG.
Ce module fournit des outils pour extraire les métadonnées et nettoyer le contenu
Markdown en supprimant les éléments indésirables (publicités, navigation, etc.)
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from enum import Enum

from config import CleanerConfig
from scraping_cleaning.utils import MetadataExtractor
from .models import ScrapingStats, CleaningResult
# from chunking.chunk_orchestrator import ChunkOrchestrator


# ============================================================================
# NETTOYEUR DE CONTENU
# ============================================================================

class ContentCleaner:
    """
    Nettoyeur de contenu Markdown pour systèmes RAG.
    Supprime les éléments indésirables et normalise le format.
    """
    
    def __init__(self, project_dir: str, config: Optional[CleanerConfig] = None):
        """
        Initialise le nettoyeur.
        
        Args:
            project_dir: Répertoire du projet contenant les dossiers raw/clean
            config: Configuration du nettoyeur (options)
        """
        self.config = config or CleanerConfig()
        
        # Définir les répertoires
        self.input_dir = Path(project_dir) / self.config.input_dir_name
        self.output_dir = Path(project_dir) / self.config.output_dir_name
        
        # Créer le répertoire de sortie
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compiler les patterns de bruit pour de meilleures performances
        self._compiled_noise_patterns = [
            re.compile(p, re.IGNORECASE) 
            for p in self.config.noise_patterns
        ]
        
        # Compiler les patterns de partage
        self._compiled_share_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.share_patterns
        ]
        
        # Compiler les patterns d'URL encodée
        self._compiled_url_encoding_patterns = [
            re.compile(p)
            for p in self.config.url_encoding_patterns
        ]
    
    # ========================================================================
    # MÉTHODES DE NETTOYAGE INDIVIDUELLES
    # ========================================================================
    
    @staticmethod
    def remove_yaml_metadata(text: str) -> str:
        """Supprime le frontmatter YAML du contenu."""
        return re.sub(
            r"^---.*?---\n",
            "",
            text,
            flags=re.DOTALL | re.MULTILINE
        )
    # -------------------------------------------------------------------------


    @staticmethod
    def remove_html(text: str) -> str:
        """Supprime les balises HTML."""
        return re.sub(r"<[^>]+>", "", text)
    
    # -------------------------------------------------------------------------


    @staticmethod
    def remove_markdown_links(text: str) -> str:
        """Supprime les liens Markdown en gardant uniquement le texte."""
        return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
 
 
    # -------------------------------------------------------------------------


    @staticmethod
    def normalize_spacing(text: str) -> str:
        """Normalise les espaces et les sauts de ligne."""
        # Supprimer les sauts de ligne multiples
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        # Supprimer les espaces multiples
        text = re.sub(r"[ \t]{2,}", " ", text)
        
        # Supprimer les espaces en début/fin de ligne
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    

    # -------------------------------------------------------------------------


    def remove_share_artifacts(self, text: str) -> str:
        """
        Supprime les artefacts de partage (email, réseaux sociaux, etc.)
        et les appels à télécharger des applications.
        """
        lines = text.splitlines()
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Vérifier si la ligne contient des motifs de partage
            is_share_artifact = any(
                pattern.search(line_stripped)
                for pattern in self._compiled_share_patterns
            )
            
            if is_share_artifact:
                continue
            
            cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)
    

    # -------------------------------------------------------------------------

    def decode_and_clean_urls(self, text: str) -> str:
        """
        Décode les URLs encodées et supprime les paramètres de tracking.
        """
        # Décoder les % encodés (comme %20, %0D%0A, etc.)
        for pattern in self._compiled_url_encoding_patterns:
            text = re.sub(pattern, '', text)
        
        # Nettoyer les retours à la ligne encodés
        text = text.replace('%0D%0A', '')
        text = text.replace('%0A', '')
        text = text.replace('%0D', '')
        
        # Supprimer les paramètres UTM et autres paramètres de tracking
        text = re.sub(r'[?&]utm_[a-z_]+=[^&\s]+', '', text)
        text = re.sub(r'[?&]ref=[^&\s]+', '', text)
        text = re.sub(r'[?&]source=[^&\s]+', '', text)
        
        # Nettoyer les URLs qui se terminent par des points ou virgules
        text = re.sub(r'https?://[^\s]+[.,;:!?]+(?=\s|$)', '', text)
        
        return text
    
    # -------------------------------------------------------------------------


    def clean_special_characters(self, text: str) -> str:
        """
        Nettoie les caractères spéciaux et les séquences d'échappement.
        """
        # Supprimer les retours à la ligne en excès
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        # Nettoyer les espaces insécables et autres caractères spéciaux
        text = text.replace('\xa0', ' ')  # Espace insécable
        text = text.replace('\u200b', '')  # Zero-width space
        
        return text
    

    # -------------------------------------------------------------------------


    def remove_urls_except_source(self, text: str, source_url: str) -> str:
        """
        Supprime toutes les URLs sauf l'URL source.
        
        Args:
            text: Texte à nettoyer
            source_url: URL source à conserver
            
        Returns:
            Texte nettoyé
        """
        def replacer(match):
            url = match.group(0)
            return url if url == source_url else ""
        
        return re.sub(r"https?://[^\s)]+", replacer, text)
    

    # -------------------------------------------------------------------------


    def remove_noise_lines(self, text: str) -> str:
        """
        Supprime les lignes contenant des motifs de bruit.
        """
        cleaned_lines = []
        
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            
            lower = line.lower()
            
            # Vérifier si la ligne contient un motif de bruit
            is_noise = any(
                pattern.search(lower) 
                for pattern in self._compiled_noise_patterns
            )
            
            if not is_noise:
                cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)
    

    # -------------------------------------------------------------------------


    def remove_short_lines(self, text: str) -> str:
        """
        Supprime les lignes trop courtes, sauf les titres Markdown.
        """
        kept = []
        
        for line in text.splitlines():
            stripped = line.strip()
            
            # Toujours garder les titres
            if stripped.startswith('#'):
                kept.append(line)
            elif len(stripped) >= self.config.min_line_length:
                kept.append(line)
        
        return "\n".join(kept)
    
    
    # -------------------------------------------------------------------------

    @staticmethod
    def remove_duplicate_lines(text: str) -> str:
        """Supprime les lignes dupliquées."""
        seen = set()
        output = []
        
        for line in text.splitlines():
            key = line.strip().lower()
            if key not in seen:
                seen.add(key)
                output.append(line)
        
        return "\n".join(output)
    

    # ========================================================================
    # MÉTHODE DE NETTOYAGE PRINCIPALE
    # ========================================================================
    
    def clean_markdown(self, markdown: str) -> Dict:
        """
        Nettoie un contenu Markdown complet.
        
        Args:
            markdown: Contenu Markdown à nettoyer
            
        Returns:
            Contenu nettoyé
        """
        if not markdown:
            return ""
        
        # 1. Extraire les métadonnées
        metadata = MetadataExtractor.extract_useful_metadata(markdown)
        
        
        # 2. Supprimer les métadonnées YAML
        content = self.remove_yaml_metadata(markdown)
        
        # 3. Nettoyer les encodages URL et paramètres de tracking
        content = self.decode_and_clean_urls(content)
        
        # 4. Supprimer les artefacts de partage
        content = self.remove_share_artifacts(content)
        
        # 5. Nettoyer les caractères spéciaux
        content = self.clean_special_characters(content)
        
        # 6. Supprimer les éléments indésirables
        content = self.remove_html(content)
        content = self.remove_markdown_links(content)
        content = self.remove_urls_except_source(content, "")
        content = self.remove_noise_lines(content)
        content = self.remove_short_lines(content)
        content = self.remove_duplicate_lines(content)
        content = self.normalize_spacing(content)
        
        return {"content" :content , "metadata":metadata}
    
    # ========================================================================
    # MÉTHODES DE TRAITEMENT DE CONTENU
    # ========================================================================
    
    def process_file(self, file_name: str, content: str) -> CleaningResult:
        """
        Nettoie un contenu Markdown directement.
        
        Args:
            file_name: Nom du fichier (pour référence et sortie)
            content: Contenu Markdown à nettoyer
            source_url: URL source à conserver (optionnel)
            
        Returns:
            CleaningResult
        """
        try:   

            # Nettoyer le contenu
            cleaned = self.clean_markdown(content)
            
            # Écrire le fichier nettoyé
            output_file = self.output_dir / file_name
            output_file.write_text(cleaned["content"], encoding="utf-8")
            
            print(f"✓ Nettoyé: {file_name}")
            # print(f"voila metadata: {cleaned["metadata"]}")
            return CleaningResult(
                file_name=file_name,
                original_content=content,
                cleaned_content=cleaned["content"],
                metadata=cleaned["metadata"],
                success=True,
            )
            
        except Exception as e:
            print(f"✗ Erreur {file_name}: {e}")
            return CleaningResult(
                file_name=file_name,
                original_content=content,
                cleaned_content="",
                metadata={},
                success=False,
                error=str(e),
            )
    




    def process_all(self, stats: ScrapingStats) -> List[CleaningResult]:
        """
        Nettoie toutes les URLs/contenus extraits d'un ScrapingStats.
        
        Args:
            stats: Objet ScrapingStats contenant les fichiers, URLs et contenus
            
        Returns:
            Liste des CleaningResult
        """
        results = []
        
        for i, content in enumerate(stats.contents):
            file_path = stats.files[i] if i < len(stats.files) else f"unknown_{i}.md"
            file_name = Path(file_path).name
            # source_url = stats.urls_scraped[i] if i < len(stats.urls_scraped) else ""
            result = self.process_file(file_name, content)
            results.append(result)
        
        print(f"\n✅ Nettoyage terminé: {len(results)}/{len(stats.contents)} fichiers traités")
        return results
    

    def process_directory(self, pattern: str = "*.md") -> List[CleaningResult]:
        """
        Nettoie tous les fichiers Markdown d'un répertoire.
        
        Args:
            pattern: Pattern de recherche des fichiers
            
        Returns:
            Liste des CleaningResult
        """
        if not self.input_dir.exists():
            print(f"✗ Répertoire non trouvé: {self.input_dir}")
            return []
        
        files = list(self.input_dir.glob(pattern))
        
        if not files:
            print(f"✗ Aucun fichier {pattern} trouvé dans {self.input_dir}")
            return []
        
        print(f"📁 Trouvé {len(files)} fichiers à nettoyer")
        
        contents = []
        urls_scraped = []
        file_paths = []
        for f in files:
            file_paths.append(str(f))
            urls_scraped.append("")
            try:
                contents.append(f.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                contents.append("")
        
        stats = ScrapingStats(
            total=len(files),
            files=file_paths,
            urls_scraped=urls_scraped,
            contents=contents,
        )
        return self.process_all(stats)
    
    # ========================================================================
    # MÉTHODE DE DIAGNOSTIC
    # ========================================================================
    
    def preview_cleaning(self, text: str, max_lines: int = 20) -> None:
        """
        Affiche un aperçu du nettoyage pour déboguer.
        
        Args:
            text: Texte à nettoyer
            max_lines: Nombre maximum de lignes à afficher
        """
        print("\n" + "=" * 80)
        print("📋 APERÇU DU NETTOYAGE")
        print("=" * 80)
        
        print("\n--- TEXTE ORIGINAL (premières lignes) ---")
        original_lines = text.splitlines()[:max_lines]
        for i, line in enumerate(original_lines, 1):
            print(f"{i:3d}: {line}")
        
        cleaned = self.clean_markdown(text)
        
        print("\n--- TEXTE NETTOYÉ (premières lignes) ---")
        cleaned_lines = cleaned.splitlines()[:max_lines]
        for i, line in enumerate(cleaned_lines, 1):
            print(f"{i:3d}: {line}")
        
        print(f"\n📊 Statistiques:")
        print(f"   - Lignes originales: {len(text.splitlines())}")
        print(f"   - Lignes nettoyées: {len(cleaned.splitlines())}")
        print(f"   - Réduction: {len(text.splitlines()) - len(cleaned.splitlines())} lignes")
        print("=" * 80)


# ============================================================================
# FONCTION UTILITAIRE
# ============================================================================

def extract_useful_metadata(markdown_content: str) -> Dict[str, Any]:
    """
    Fonction de compatibilité pour extraire les métadonnées.
    """
    return MetadataExtractor.extract_metadata(markdown_content)


# ============================================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    # Configuration
    PROJECT_DIR = "data/cleaning_cleaning"
    
    # Initialiser le cleaner avec configuration personnalisée
    config = CleanerConfig(
        min_line_length=30,
        output_dir_name="clean_markdown",
        input_dir_name="raw_markdown"
    )
    
    cleaner = ContentCleaner(PROJECT_DIR, config)

    files_to_clean1 = Path(r"C:\Users\ghofr\Downloads\mes_fichier\outputs_exp\raw_markdown\hoteltechinsight_com_Little_Hotelier_vs_Cloudbeds__PMS_comparison__2026____Hotel_Tech_Insight_31490587.md")
    content1 = files_to_clean1.read_text(encoding="utf-8", errors="ignore")
    
    files_to_clean2 = Path(r"C:\Users\ghofr\Downloads\mes_fichier\outputs_exp\raw_markdown\iswtechnosys_com_PMS_Cloud_ou_sur_site_pour_les_hôtels_-_ISW_Technosys_Ltd_55619561.md")
    content2 = files_to_clean2.read_text(encoding="utf-8", errors="ignore")
    
    scrap_res = ScrapingStats(
            total=2,
            success=2,
            failed=0,
            files=[str(files_to_clean1), str(files_to_clean2)],
            durations=[0.0],
            urls_scraped=[""],
            contents=[content1, content2]
        )
    
    results = cleaner.process_all(scrap_res)
    
        # Afficher l'en-tête
    print("=" * 80)
    print("🧹 NETTOYAGE DE MARKDOWN POUR RAG")
    print("=" * 80)
    print(f"📁 Entrée: {cleaner.input_dir}")
    print(f"📁 Sortie: {cleaner.output_dir}")
    print("")
        
    # Afficher les résultats
    if results:
        for i, result in enumerate(results):
            print(f"\n🔹 Fichier {i+1}: {result.file_name}")
            print(f"   - Succès: {result.success}")
            if result.success:
                    print(f"   - Contenu nettoyé (premières 200 caractères):")
                    print(f"     {result.cleaned_content[:200]}...")
                    print(f"   - Métadonnées extraites:")
                    print(json.dumps(result.metadata, indent=2, ensure_ascii=False))
            else:
                    print(f"   - Erreur: {result.error}")
            

