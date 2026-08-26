"""
Script d'évaluation RAGAS pour l'analyse des résultats de recherche hybride
Auteur: Assistant
Date: 2026-01-17
Description: Évalue la qualité des réponses générées par RAG avec les métriques faithfulness et answer_relevancy
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from datasets import Dataset
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy,context_utilization
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from clients import ClientConfig


# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    """Configuration de l'application"""

    OPENROUTER_BASE_URL = ClientConfig.OPENROUTER_BASE_URL
    LLM_MODEL = "gpt-4o-mini"
    EMBEDDING_MODEL = "BAAI/bge-m3"

    INPUT_FILE = r"outputs\projects\Restauration_saas_20260811_121003\agents\macro_ragas_dataset.json"
    OUTPUT_DIR = "evaluation_results"

    TEMPERATURE = 0
    DEVICE = "cpu"
    NORMALIZE_EMBEDDINGS = True


# ============================================================
# UTILITAIRES DE CONVERSION NUMPY -> JSON
# ============================================================

def convert_numpy_to_native(obj: Any) -> Any:
    """
    Convertit récursivement les objets numpy en types Python natifs.

    Args:
        obj: Objet à convertir

    Returns:
        Objet converti avec des types Python natifs
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.complex128, np.complex64)):
        return str(obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_numpy_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_to_native(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_to_native(item) for item in obj)
    elif hasattr(obj, 'item'):
        try:
            return obj.item()
        except:
            return str(obj)
    else:
        return obj



class NumpySafeJSONEncoder(json.JSONEncoder):
    """
    Encodeur JSON personnalisé qui gère les types numpy.
    """
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (np.complex128, np.complex64)):
            return str(obj)
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif hasattr(obj, 'item'):
            try:
                return obj.item()
            except:
                return str(obj)
        return super().default(obj)



# ============================================================
# FONCTIONS DE SAUVEGARDE
# ============================================================

class ResultsSaver:
    """Gère la sauvegarde des résultats d'évaluation"""

    @staticmethod
    def save_ragas_results(result, output_dir: str = Config.OUTPUT_DIR,
                          filename: Optional[str] = None,
                          include_full_df: bool = True,strategie:str="vector") -> str:
        """
        Sauvegarde les résultats RAGAS avec création automatique des dossiers.

        Args:
            result: Résultat de l'évaluation RAGAS
            output_dir: Dossier de sortie
            filename: Nom du fichier (optionnel)
            include_full_df: Inclure le DataFrame complet

        Returns:
            Chemin du fichier sauvegardé
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ragas_evaluation_{timestamp}.json"

        filepath = os.path.join(output_dir, filename)

        df = result.to_pandas()

        data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "output_dir": output_dir,
                "filename": filename,
                "total_questions": len(df),
                "strategy":strategie
            },
            "metrics_scores": {},
            "summary": {},
        }

        for col in df.columns:
            if col not in ['question', 'answer', 'contexts']:
                try:
                    if len(df) > 1:
                        data["metrics_scores"][col] = float(df[col].mean())
                    else:
                        data["metrics_scores"][col] = float(df[col].iloc[0])
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Erreur pour la métrique {col}: {e}")
                    data["metrics_scores"][col] = 0.0

        if data["metrics_scores"]:
            scores = list(data["metrics_scores"].values())
            numeric_scores = [s for s in scores if isinstance(s, (int, float))]
            if numeric_scores:
                data["summary"] = {
                    "average": float(sum(numeric_scores) / len(numeric_scores)),
                    "min": float(min(numeric_scores)),
                    "max": float(max(numeric_scores)),
                    "total_metrics": len(numeric_scores)
                }

        if include_full_df:
            detailed_results = df.to_dict(orient='records')
            data["detailed_results"] = convert_numpy_to_native(detailed_results)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, cls=NumpySafeJSONEncoder)

            print(f"✅ Résultats sauvegardés dans: {filepath}")
            print(f"📊 Métriques: {list(data['metrics_scores'].keys())}")

        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde JSON: {e}")
            csv_path = filepath.replace('.json', '.csv')
            df.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"✅ Résultats sauvegardés en CSV: {csv_path}")

        return filepath

    @staticmethod
    def save_metrics_comparison(result, output_dir: str = Config.OUTPUT_DIR) -> Dict[str, str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        df = result.to_pandas()

        metrics = [col for col in df.columns if col not in ['question', 'answer', 'contexts']]

        comparison_data = {
            'Question #': list(range(1, len(df) + 1)),
            'Questions': df['question'].tolist()
        }

        for metric in metrics:
            comparison_data[metric] = df[metric].tolist()

        comparison_df = pd.DataFrame(comparison_data)

        csv_path = os.path.join(output_dir, f"metrics_comparison_{timestamp}.csv")
        comparison_df.to_csv(csv_path, index=False, encoding='utf-8')

        json_path = os.path.join(output_dir, f"metrics_comparison_{timestamp}.json")

        json_data = {
            "timestamp": timestamp,
            "number_of_questions": len(df),
            "metrics": metrics,
            "comparison": convert_numpy_to_native(comparison_df.to_dict(orient='records')),
            "statistics": {
                metric: {
                    "mean": float(df[metric].mean()) if len(df) > 1 else float(df[metric].iloc[0]),
                    "std": float(df[metric].std()) if len(df) > 1 else 0.0,
                    "min": float(df[metric].min()) if len(df) > 1 else float(df[metric].iloc[0]),
                    "max": float(df[metric].max()) if len(df) > 1 else float(df[metric].iloc[0]),
                }
                for metric in metrics
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False, cls=NumpySafeJSONEncoder)

        print(f"\n✅ Comparaison des métriques sauvegardée")
        print(f"   - CSV: {csv_path}")
        print(f"   - JSON: {json_path}")

        return {"csv": csv_path, "json": json_path}

    @staticmethod
    def save_results_markdown(result, output_dir: str = Config.OUTPUT_DIR) -> str:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        df = result.to_pandas()
        md_path = os.path.join(output_dir, f"ragas_results_{timestamp}.md")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# 📊 Résultats d'Évaluation RAGAS\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Nombre de questions:** {len(df)}\n\n")

            f.write("## 📈 Scores par Métrique\n\n")
            f.write("| Métrique | Score |\n")
            f.write("|----------|-------|\n")

            for col in df.columns:
                if col not in ['question', 'answer', 'contexts']:
                    if len(df) > 1:
                        score = df[col].mean()
                    else:
                        score = df[col].iloc[0]
                    f.write(f"| {col} | {score:.4f} |\n")

            f.write(f"\n## 📝 Détails par Question\n\n")

            for idx, row in df.iterrows():
                f.write(f"### Question {idx + 1}\n\n")
                f.write(f"**Question:** {row['question']}\n\n")
                f.write(f"**Réponse:** {row['answer'][:300]}...\n\n")
                f.write("**Scores:**\n\n")
                f.write("| Métrique | Score |\n")
                f.write("|----------|-------|\n")

                for col in df.columns:
                    if col not in ['question', 'answer', 'contexts']:
                        f.write(f"| {col} | {row[col]:.4f} |\n")

                f.write("\n---\n\n")

        print(f"✅ Markdown sauvegardé: {md_path}")
        return md_path


# ============================================================
# FONCTIONS DE CHARGEMENT DES DONNÉES
# ============================================================

class DataLoader:
    """Gère le chargement des données"""

    @staticmethod
    def load_json_data(filepath: str) -> Dict[str, Any]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Données chargées depuis: {filepath}")
            return data
        except FileNotFoundError:
            print(f"❌ Fichier non trouvé: {filepath}")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ Erreur de format JSON: {e}")
            raise

    @staticmethod
    def create_ragas_dataset(question: List[str] | str,
                             answer: List[str] | str,
                             contexts: List[List[str]] | List[str]) -> Dataset:
        if isinstance(question, str):
            question = [question]
        if isinstance(answer, str):
            answer = [answer]
        if isinstance(contexts, list) and len(contexts) > 0 and isinstance(contexts[0], str):
            contexts = [contexts]

        if len(question) != len(answer) or len(question) != len(contexts):
            print(f"⚠️ Longueurs différentes: question={len(question)}, answer={len(answer)}, contexts={len(contexts)}")
            min_len = min(len(question), len(answer), len(contexts))
            question = question[:min_len]
            answer = answer[:min_len]
            contexts = contexts[:min_len]

        return Dataset.from_dict({
            "question": question,
            "answer": answer,
            "contexts": contexts
        })


# ============================================================
# FONCTIONS D'ÉVALUATION
# ============================================================

class RagasEvaluator:
    """Gère l'évaluation RAGAS"""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: str = Config.LLM_MODEL,
                 embedding_model: str = Config.EMBEDDING_MODEL):
        ClientConfig.validate()

        self.api_key = api_key or ClientConfig.OPENROUTER_API_KEY
        self.base_url = base_url or ClientConfig.OPENROUTER_BASE_URL
        self.model = model
        self.embedding_model = embedding_model

        self.llm = None
        self.embeddings = None
        self.ragas_llm = None
        self.ragas_embeddings = None
        self._initialize_components()

    def _initialize_components(self):
        try:
            self.llm = ChatOpenAI(
                model=self.model,
                openai_api_key=self.api_key,
                openai_api_base=self.base_url,
                temperature=Config.TEMPERATURE,
            )

            embedding_model = HuggingFaceEmbeddings(
                model_name=self.embedding_model,
                model_kwargs={"device": Config.DEVICE},
                encode_kwargs={"normalize_embeddings": Config.NORMALIZE_EMBEDDINGS}
            )

            self.ragas_llm = LangchainLLMWrapper(self.llm)
            self.ragas_embeddings = LangchainEmbeddingsWrapper(embedding_model)

            print("✅ Composants RAGAS initialisés avec succès")

        except Exception as e:
            print(f"❌ Erreur lors de l'initialisation: {e}")
            raise

    def test_connection(self) -> bool:
        try:
            response = self.llm.invoke("Reply only with OK.")
            print("✅ Connexion OpenRouter réussie.")
            print(f"Réponse: {response.content}")
            return True
        except Exception as e:
            print(f"❌ Erreur de connexion: {e}")
            return False

    def evaluate(self, dataset: Dataset) -> Any:
        print("\n🔍 Lancement de l'évaluation RAGAS...\n")

        try:
            result = evaluate(
                dataset=dataset,
                metrics=[
                    faithfulness,
                    answer_relevancy,
                    context_utilization
                ],
                llm=self.ragas_llm,
                embeddings=self.ragas_embeddings,
            )
            print("✅ Évaluation terminée avec succès")
            return result

        except Exception as e:
            print(f"❌ Erreur lors de l'évaluation: {e}")
            raise

    def display_results(self, result):
        print("\n" + "="*60)
        print("📊 RÉSULTATS DE L'ÉVALUATION")
        print("="*60)

        df = result.to_pandas()

        print("\n📋 DataFrame des résultats:")
        print(df)

        print("\n📈 Scores par métrique:")
        for col in df.columns:
            if col not in ['question', 'answer', 'contexts']:
                if len(df) > 1:
                    print(f"  - {col}: moyenne = {df[col].mean():.4f}, min = {df[col].min():.4f}, max = {df[col].max():.4f}")
                else:
                    print(f"  - {col}: {df[col].iloc[0]:.4f}")

        return df


# ============================================================
# FONCTION PRINCIPALE
# ============================================================

def main():
    print("="*60)
    print("🚀 ÉVALUATION RAGAS")
    print("="*60)

    try:
        print("\n📂 Chargement des données...")
        data = DataLoader.load_json_data(Config.INPUT_FILE)

        required_keys = ['question', 'answer', 'contexts']
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            print(f"❌ Clés manquantes dans le fichier JSON: {missing_keys}")
            print(f"Clés disponibles: {list(data.keys())}")
            return

        print("\n📊 Création du dataset RAGAS...")
        dataset = DataLoader.create_ragas_dataset(
            question=data["question"],
            answer=data["answer"],
            contexts=data["contexts"]
        )
        print(f"✅ Dataset créé avec {len(dataset)} question(s)")

        print("\n⚙️ Initialisation de l'évaluateur RAGAS...")
        evaluator = RagasEvaluator()

        print("\n🔄 Test de connexion au LLM...")
        if not evaluator.test_connection():
            print("❌ Échec de la connexion. Arrêt du processus.")
            return

        result = evaluator.evaluate(dataset)

        df = evaluator.display_results(result)

        print("\n💾 Sauvegarde des résultats...")
        saver = ResultsSaver()

        json_path = saver.save_ragas_results(
            result,
            output_dir=Config.OUTPUT_DIR,
            include_full_df=True,
            strategie="vector"
        )

        comparison_paths = saver.save_metrics_comparison(result, output_dir=Config.OUTPUT_DIR)

        md_path = saver.save_results_markdown(result, output_dir=Config.OUTPUT_DIR)

        print("\n" + "="*60)
        print("✅ ÉVALUATION TERMINÉE AVEC SUCCÈS")
        print("="*60)
        print(f"\n📁 Résultats sauvegardés dans: {Config.OUTPUT_DIR}")
        print(f"   - Évaluation complète (JSON): {json_path}")
        print(f"   - Comparaison (CSV): {comparison_paths['csv']}")
        print(f"   - Comparaison (JSON): {comparison_paths['json']}")
        print(f"   - Rapport (Markdown): {md_path}")

        print("\n📊 RÉSUMÉ DES SCORES:")
        for col in df.columns:
            if col not in ['question', 'answer', 'contexts']:
                if len(df) > 1:
                    print(f"   - {col}: {df[col].mean():.4f} (moyenne)")
                else:
                    print(f"   - {col}: {df[col].iloc[0]:.4f}")

    except FileNotFoundError:
        print(f"❌ Fichier non trouvé: {Config.INPUT_FILE}")
        print("Vérifiez que le fichier existe et que le chemin est correct.")

    except json.JSONDecodeError as e:
        print(f"❌ Erreur de format JSON: {e}")
        print("Vérifiez que le fichier JSON est valide.")

    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()
