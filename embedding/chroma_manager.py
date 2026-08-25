from datetime import datetime
import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

# from clients import save_results_to_markdown

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("Warning: chromadb not installed. Run: pip install chromadb")


from pathlib import Path
from dataclasses import dataclass
import numpy as np

# Ajouter l'import pour l'embedder
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Run: pip install sentence-transformers")






class ChromaManager:

    # INITIALISER CHROMA MANAGER
    # ===================================================================
    def __init__(
        self, 
        persist_directory: str = "data/chromadb",
        embedding_model: str = "BAAI/bge-m3"  # Ajout du modèle d'embedding
    ):
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb n'est pas installé. "
                "Installez-le avec: pip install chromadb"
            )
        

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        


        # Initialiser le client ChromaDB avec persistance
        # --------------------------------------------------------------
        self.client = chromadb.PersistentClient(
                      path=str(self.persist_directory),
                      settings=Settings(anonymized_telemetry=False)
                    )
        
        # Initialiser l'embedder BGE-M3
        # --------------------------------------------------------------
        self.embedding_model = embedding_model
        self.embedder = None

        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.logger.info(f"Chargement du modèle d'embedding: {embedding_model}")
                self.embedder = SentenceTransformer(embedding_model)
                self.embedding_dimension = self.embedder.get_sentence_embedding_dimension()
                self.logger.info(f"✅ Modèle chargé, dimension: {self.embedding_dimension}")
            except Exception as e:
                self.logger.warning(f"Impossible de charger {embedding_model}: {e}")
                self.embedder = None
                self.embedding_dimension = 1024  # Valeur par défaut pour BGE-M3
        else:
            self.logger.warning("sentence-transformers non installé, embedding non disponible")
            self.embedder = None
            self.embedding_dimension = 1024

        self.logger.info(f"ChromaDB initialisé: {self.persist_directory}")
        self._list_collections()





    # LISTER LES COLLECTIONS DISPONIBLES
    # ===================================================================
    def _list_collections(self):
        """Liste les collections existantes (pour information)"""
        try:
            collections = self.client.list_collections()
            if collections:
                self.logger.info(f"Collections existantes: {[c.name for c in collections]}")
            else:
                self.logger.info("Aucune collection existante")
        except Exception as e:
            self.logger.warning(f"Erreur lors de la liste des collections: {str(e)}")




    # CREER UNE COLLECTION
    # ===================================================================

    def create_collection(
        self,
        name: str,
        embedding_function=None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> chromadb.Collection:
        
        try:

        # Vérifier si la collection existe déjà
        # --------------------------------------------------------------
            existing_collections = self.client.list_collections()
            if name in [c.name for c in existing_collections]:
                self.logger.warning(f"La collection '{name}' existe déjà. Suppression...")
                self.client.delete_collection(name)
        


        # Créer la collection avec configuration pour BGE-M3
        # --------------------------------------------------------------
            default_metadata = {
                "hnsw:space": "cosine",
                "embedding_dimension": self.embedding_dimension
            }
            if metadata:
                default_metadata.update(metadata)
            
            collection = self.client.create_collection(
                name=name,
                embedding_function=embedding_function,
                metadata=default_metadata
            )
            
            self.logger.info(f"Collection créée: {name} (dimension: {self.embedding_dimension})")
            return collection
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de la collection {name}: {str(e)}")
            raise



    
    # RECUPERATION D'UNE COLLECTION
    # ===============================================================
    def get_collection(self, name: str) -> Optional[chromadb.Collection]:
        """Récupère une collection existante"""
        try:
            return self.client.get_collection(name)
        except Exception as e:
            self.logger.error(f"Collection '{name}' non trouvée: {str(e)}")
            return None
        
    

    # GENERER UN EBEDDING POUR TEXT
    # ==============================================================

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Génère un embedding pour un texte avec BGE-M3"""
        if not self.embedder:
            self.logger.error("Embedder non disponible")
            return None
        
        try:
            embedding = self.embedder.encode(text, normalize_embeddings=True)
            # Convertir en liste de float
            if isinstance(embedding, np.ndarray):
                return embedding.tolist()
            return embedding
        except Exception as e:
            self.logger.error(f"Erreur lors de l'embedding: {e}")
            return None
        



    # AJOUTER DES CHUNKS A UNE COLLECTION
    # ==============================================================
    def add_chunks_to_collection(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        batch_size: int = 50
    ) -> int:
        
        # récupérer collection 
        # ----------------------------------------------------------
        collection = self.get_collection(collection_name)
        if not collection:
            collection = self.create_collection(collection_name)



        # ajouter chunks par batch
        # ---------------------------------------------------------
       
        # 1. ajout des documents
        total_added = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            
            ids = []
            documents = []
            embeddings = []
            metadatas = []
            for chunk in batch:
                chunk_id = chunk.get("id", chunk.get("chunk_id", f"chunk_{i}_{len(ids)}"))
                ids.append(chunk_id)
                document = chunk.get("text", chunk.get("content", ""))
                documents.append(document)


        # 2.ajout des embeddings

        # Vérifier si l'embedding est déjà présent
        # ---------------------------------------------------------
                embedding = chunk.get("embedding")
                if embedding is None:


                    # Générer l'embedding si nécessaire
                    # -------------------------------------
                    embedding = self._get_embedding(document)
                    if embedding is None:
                        self.logger.warning(f"Chunk {chunk_id} sans embedding, ignoré")
                        continue


                # verifier la dimenssion
                # --------------------------------------
                # Vérifier la dimension
                if len(embedding) != self.embedding_dimension:
                    self.logger.warning(
                        f"Chunk {chunk_id} dimension {len(embedding)} != {self.embedding_dimension}"
                    )

                    # Re-générer l'embedding avec le bon modèle
                    # ------------------------------------------
                    embedding = self._get_embedding(document)
                    if embedding is None or len(embedding) != self.embedding_dimension:
                        continue
                
                embeddings.append(embedding)

            
                # 3.ajout des meta-données
                meta = chunk.get("metadata", {})
                metadatas.append(meta)

            
            # ajout de total de chunks
            # -----------------------------------------------------
            if ids and documents and embeddings:
                        try:
                            collection.add(
                                ids=ids,
                                documents=documents,
                                embeddings=embeddings,
                                metadatas=metadatas
                            )
                            total_added += len(ids)
                            self.logger.info(f"Lot {i//batch_size + 1}: ajouté {len(ids)} chunks (dim {self.embedding_dimension})")
                        except Exception as e:
                            self.logger.error(f"Erreur lors de l'ajout du lot: {str(e)}")

        
        self.logger.info(f"Total ajouté à '{collection_name}': {total_added} chunks (BGE-M3)")
        return total_added   






    # RECHERCHE DANS UNE COLLECTION 
    #==================================================================
    def search(
        self,
        collection_name: str,
        query: str = None,
        query_embedding: Optional[List[float]] = None,
        n_results: int = 10,
        where_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Recherche dans la collection
        - Si query_embedding n'est pas fourni mais query l'est, 
        génère automatiquement l'embedding avec BGE-M3.
        """

        # récuperer la collection:
        # -----------------------------------------
        collection = self.get_collection(collection_name)
        if not collection:
            self.logger.error(f"Collection '{collection_name}' non trouvée")
            return []
        
        try:

        # si pas de query_embedding 
        # -----------------------------------------
            if query_embedding is None and query is not None:
                self.logger.info(f"Génération de l'embedding pour la requête: {query[:50]}...")
                query_embedding = self._get_embedding(query)
                if query_embedding is None:
                    self.logger.error("Échec de la génération de l'embedding")
                    return []
                
                # verifier la dimension
                # --------------------------
                if len(query_embedding) != self.embedding_dimension:
                    self.logger.error(
                        f"Dimension de l'embedding de la requête ({len(query_embedding)}) "
                        f"ne correspond pas à la dimension attendue ({self.embedding_dimension})"
                    )
                    return []
                

            
            # effectuer la recherche
            # -----------------------------------------------
            if query_embedding is not None:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where_filter
                )
            else:
                self.logger.error("Aucune requête fournie")
                return []
            


            # # Formater les résultats
            # ------------------------------------------------
            formatted_results = []
            if results and results.get('ids') and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    formatted_results.append({
                        "id": results['ids'][0][i],
                        "text": results['documents'][0][i] if results.get('documents') else "",
                        "metadata": results['metadatas'][0][i] if results.get('metadatas') else {},
                        "score": 1 - results['distances'][0][i] if results.get('distances') else 0.0
                    })

            return formatted_results
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche: {str(e)}")
            import traceback
            traceback.print_exc()
            return [] 
        


    


    # RECUPERER STATSTIQUE D'UNE COLLECTION
    # ====================================================
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Récupère les statistiques d'une collection"""
        collection = self.get_collection(collection_name)
        if not collection:
            return {"error": f"Collection {collection_name} non trouvée"}
        
        try:
            count = collection.count()
            return {
                "name": collection_name,
                "count": count,
                "metadata": collection.metadata,
                "embedding_model": "BGE-M3",
                "embedding_dimension": 1024
            }
        except Exception as e:
            return {"error": str(e)}
        
    


    #SUPPRIMER UNE COLLECTION
    #========================================================
    def delete_collection(self, collection_name: str):
        """Supprime une collection"""
        try:
            self.client.delete_collection(collection_name)
            self.logger.info(f"Collection supprimée: {collection_name}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la suppression: {str(e)}")
    
   

    

    # EXPORTER UNE COLLECTION AU JSON
    #========================================================
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Récupère les statistiques d'une collection"""
        collection = self.get_collection(collection_name)
        if not collection:
            return {"error": f"Collection {collection_name} non trouvée"}
        
        try:
            count = collection.count()
            return {
                "name": collection_name,
                "count": count,
                "metadata": collection.metadata,
                "embedding_model": "BGE-M3",
                "embedding_dimension": 1024
            }
        except Exception as e:
            return {"error": str(e)}
    
    def delete_collection(self, collection_name: str):
        """Supprime une collection"""
        try:
            self.client.delete_collection(collection_name)
            self.logger.info(f"Collection supprimée: {collection_name}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la suppression: {str(e)}")
    
    def list_collections(self) -> List[str]:
        """Liste toutes les collections"""
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception as e:
            self.logger.error(f"Erreur: {str(e)}")
            return []
    
    def export_collection_to_json(self, collection_name: str, output_path: str):
        """Exporte une collection au format JSON"""
        collection = self.get_collection(collection_name)
        if not collection:
            return
        
        try:
            results = collection.get()
            
            export_data = {
                "collection_name": collection_name,
                "export_date": datetime.now().isoformat(),
                "embedding_model": "BGE-M3",
                "embedding_dimension": 1024,
                "count": len(results['ids']),
                "items": []
            }
            
            for i in range(len(results['ids'])):
                export_data["items"].append({
                    "id": results['ids'][i],
                    "text": results['documents'][i] if results.get('documents') else "",
                    "metadata": results['metadatas'][i] if results.get('metadatas') else {}
                })
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=4)
            
            self.logger.info(f"Collection exportée: {output_file}")
            return str(output_file)
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'export: {str(e)}")
            return None







if __name__ == "__main__":

    chroma = ChromaManager()
    # collections = chroma.list_collections()
    # for i in range (len(collections)):
    #     print (f"col {i}: {collections[i]}")

    collection_name ="hospitality_saas_restauration_20260812_111238"
    nb_chunks=chroma.get_collection_stats(collection_name=collection_name)
    for i , j in nb_chunks.items():
        print(f"{i}:{j}")

    # print("\n" + "="*60)
    # print("🧪 TEST 1: Recherche par requête texte")
    # print("="*60)

    # hyde_passage = f"""Les hôtels indépendants français nécessitent un PMS avec support client multilingue, gestion d'inventaire multi-canal, et intégrations avec logiciels de comptabilité et de gestion des avis."""
    # emb = chroma._get_embedding(text=hyde_passage)
    # print(emb)
   
   
   
    # print(f"\n🔍 Recherche: '{hyde_passage}'")
    

    # results = chroma.search(
    #     collection_name=collection_name,
    #     query=hyde_passage,
    #     n_results=5,
    #     where_filter=None
    # )

    
    # # output_file = save_results_to_markdown(
    # #     results=results,
    # #     query=hyde_passage,
    # #     collection_name=collection_name,
    # #     output_file="data/search_results/search/demande/search_results_client_besoin_pms.md"
    # # )


    # print(f"\n✅ {len(results)} résultats trouvés:\n")
    # for i, r in enumerate(results, 1):
    #     print(f"{i}. Score: {r['score']:.4f}")
    #     print(f"   Texte: {r['text'][:150]}...")
    #     print(f"   Source: {r['metadata'].get('source_url', 'N/A')}")
    #     print()
    

        
    
        

















