from dataclasses import dataclass, field
import re
import json
from typing import Dict, Any, List


# ============================================================================
# Extracteur de metadata
# ============================================================================


class MetadataExtractor:
    """Extrait et parse les métadonnées YAML du frontmatter Markdown"""
    
    @staticmethod
    def extract_useful_metadata(markdown_content: str) -> Dict[str, Any]:
    
        metadata_pattern = r'^\s*---\s*\n(.*?)\n\s*---\s*\n'
        
        match = re.search(metadata_pattern, markdown_content, re.DOTALL | re.MULTILINE)
        
        if not match:
            return {}
        
        metadata_block = match.group(1)
        metadata = {}
        
        line_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*):\s*(.+?)\s*$'
        
        for line in metadata_block.split('\n'):
            if not line.strip():
                continue
                
            match_line = re.match(line_pattern, line)
            if match_line:
                key = match_line.group(1)
                value = match_line.group(2).strip()
                
                # Nettoyer les guillemets si présents
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Convertir les types si nécessaire
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.lower() == 'null' or value.lower() == 'none':
                    value = None
                elif value.isdigit():
                    value = int(value)
                elif re.match(r'^\d+\.\d+$', value):
                    value = float(value)
                # Vérifier si c'est une date/heure (format ISO)
                elif re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
                    # Garder comme chaîne pour l'instant
                    pass
                
                metadata[key] = value
        
        return metadata
    




    
    @staticmethod
    def _parse_value(value: str) -> Any:
        """Parse et convertit la valeur selon son type"""
        value_lower = value.lower()
        
        if value_lower == 'true':
            return True
        elif value_lower == 'false':
            return False
        elif value_lower in ('null', 'none'):
            return None
        elif value.isdigit():
            return int(value)
        elif re.match(r'^\d+\.\d+$', value):
            return float(value)
        # Garder les dates ISO comme chaînes
        elif re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
            return value
        
        return value
    









# # Exemple d'utilisation
if __name__ == "__main__":
    markdown_example = """---
    url: https://anandsystems.com/fr/third-party-integrations
    title: Intégrations ASI PMS - OTAs, GDS, Paiements et autres
    section: Analyse de la demande et pain points
    angle: technical integration frictions
    question: Quels sont les besoins des clients et les obstacles  et frictions dans le processus d'achat actuel ?
    query: frictions d'intégration entre OTA et PMS pour les petites chaînes hôtelières françaises
    scraped_at: 2026-07-07T09:03:35.334168+00:00
    scraping_duration_seconds: 27.68
    status: success
    ---

    hi evry one !
"""
    extractor = MetadataExtractor()
    meta = extractor.extract_useful_metadata(markdown_example)
    print(meta["url"])
    print(meta["section"])