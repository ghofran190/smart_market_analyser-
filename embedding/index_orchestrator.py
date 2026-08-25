# embedding/index_orchestrator.py
import os
import json
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# from .embedder import EmbeddingService, EmbeddingConfig
from .chroma_manager import ChromaManager



class IndexOrchestrator:
    """
    Orchestrateur pour le pipeline complet d'indexation avec BGE-M3
    """

    def __init__(
        self,
        embedding_model: str = "BAAI/bge-m3",
        persist_directory: str = "data/chromadb",
        # project_dir: str = None,
        # batch_size: int = 16,
        # use_openai: bool = False,
        # openai_api_key: str = None,
        # use_fp16: bool = True,
        
    ):
        
        self.persist_directory = Path(persist_directory)
        # self.use_openai = use_openai
        # if project_dir:
        #     self.output_dir = Path(f"{project_dir}/index")
        # else:
        #     self.output_dir = self.persist_directory / "results"
        
        # self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.chroma = ChromaManager()
        self.logger = logging.getLogger(__name__)




    # CHARGER LES CHUNKS:
    # ========================================

    def load_chunks_from_json(self,chunks_file:str)->List[Dict[str,Any]]:
        chunks_path = Path(chunks_file)
        
        if not chunks_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {chunks_file}")
            
        with open(chunks_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f) 
            
        self.logger.info(f"Chargé {len(chunks)} chunks depuis {chunks_file}")
        return chunks
    



    def generate_embeddings(self,chunks:List[Dict]):
        chunks_with_embeddings=[]
        if chunks :
            for chunk in chunks:
                embedding = self.chroma._get_embedding(text=chunk.get("content"))
                chunk["embedding"]=embedding
                chunks_with_embeddings.append(chunk)
            
            return chunks_with_embeddings
        else:
            self.logger.error("Aucun chunk  trouvé")
            return chunks 
        
    




    def index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        collection_name: str = "new_col",
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """Indexe les chunks dans ChromaDB"""
        self.logger.info(f"Indexation de {len(chunks)} chunks dans '{collection_name}'")
        
        chunks_with_embeddings = [c for c in chunks if "embedding" in c]
        
        if len(chunks_with_embeddings) < len(chunks):
            missing = len(chunks) - len(chunks_with_embeddings)
            self.logger.warning(f"{missing} chunks sans embeddings seront ignorés")
        
        if not chunks_with_embeddings:
            self.logger.error("Aucun chunk avec embedding à indexer")
            return {"error": "No chunks with embeddings"}
        
        total_added = self.chroma.add_chunks_to_collection(
            collection_name=collection_name,
            chunks=chunks_with_embeddings,
            batch_size=batch_size
        )
        
        stats = self.chroma.get_collection_stats(collection_name)
        stats["total_added"] = total_added
        stats["embedding_model"] = "BGE-M3"
        
        return stats

     

    def save_indexing_results(self, stats: Dict[str, Any], collection_name: str, chunks_count: int):
        """Sauvegarde les résultats d'indexation"""
        indexing_results = {
            "collection_name": collection_name,
            "indexing_date": datetime.now().isoformat(),
            "embedding_model": "BAAI/bge-m3",
            "embedding_dimension": 1024,
            "chunks_indexed": chunks_count,
            "collection_stats": stats,
            "chromadb_location": str(self.persist_directory),
            "output_directory": str(self.output_dir)
        }
        
        results_file = self.output_dir / f"{collection_name}_indexing_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(indexing_results, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"  💾 Résultats indexation: {results_file}")
    
    


    def run_complete_indexing(
        self,
        chunks_source: str,
        collection_name: str = "hotellerie_saas",
        generate_embeddings: bool = True,
        save_results: bool = True
    ) -> Dict[str, Any]:
        """Exécute le pipeline complet d'indexation"""
        self.logger.info("="*80)
        self.logger.info("🚀 DÉMARRAGE DE L'INDEXATION BGE-M3")
        self.logger.info("="*80)
        
        results = {
            "start_time": datetime.now().isoformat(),
            "chunks_source": chunks_source,
            "collection_name": collection_name,
            "embedding_model": "BAAI/bge-m3",
            "steps": {}
        }



        # ÉTAPE 1: Chargement des chunks 
        # -------------------------------------------------------------
        self.logger.info("\n📖 ÉTAPE 1: Chargement des chunks")
        chunks = self.load_chunks_from_json(chunks_source)

        results["steps"]["loaded_chunks"] = len(chunks)
        self.logger.info(f"  ✓ {len(chunks)} chunks chargés")


        # ÉTAPE 2: Génération des embeddings
        # -------------------------------------------------------------
        self.logger.info("\n🔢 ÉTAPE 2: Génération des embeddings BGE-M3")
        chunks_with_embeddings = self.generate_embeddings(chunks=chunks)
        if chunks_with_embeddings:
            results["steps"]["embeddings_generated"] = chunks_with_embeddings
            self.logger.info(f"   ✓ {chunks_with_embeddings}/{len(chunks)} chunks embeddés")
        else:
            results["steps"]["embeddings_generated"] = "skipped"
            self.logger.info("   ⏭️ Étape sautée")

        
        # ÉTAPE 3: Indexation dans ChromaDB
        # --------------------------------------------------------------
        self.logger.info("\n🗄️ ÉTAPE 3: Indexation ChromaDB")
        stats = self.index_chunks(chunks_with_embeddings, collection_name)
        results["steps"]["indexed_chunks"] = stats.get("count", stats.get("total_added", 0))
        results["steps"]["collection_stats"] = stats
        self.logger.info(f"  ✓ {results['steps']['indexed_chunks']} chunks indexés")

        
        # ÉTAPE 4: Sauvegarde des résultats
        self.logger.info("\n💾 ÉTAPE 4: Sauvegarde des résultats")
        if save_results:
            self.save_indexing_results(stats, collection_name, results['steps']['indexed_chunks'])
        else:
            self.logger.info("   ⏭️ Sauvegarde désactivée")
        
        return results









       


    




            






if __name__ == "__main__": 
     
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configuration de l'indexation
    orchestrator = IndexOrchestrator(  # Répertoire de sortie personnalisé
    )



    chunks_file=r"C:\Users\ghofr\Downloads\mes_fichier\data\chunks\all_chunks_consolidated_20260709_214349.json"
    stats = orchestrator.run_complete_indexing(chunks_source=chunks_file)
    print(stats)



   
    # chunks=orchestrator.load_chunks_from_json(chunks_file=r"C:\Users\ghofr\Downloads\mes_fichier\data\chunks\all_chunks_consolidated_20260709_130041.json")
    # print(f"indexation phase \n ============================================================")

    # stats=orchestrator.index_chunks(chunks=chunks)
    # print(stats)