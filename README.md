# AI Market Analyser

Plateforme d'analyse de marché SaaS intelligente, alimentée par l'IA. Elle prend en entrée la description d'un projet SaaS et produit automatiquement un rapport de marché complet en 9 étapes, via une architecture RAG (Retrieval-Augmented Generation).

## Stack technique

| Couche | Technologie | Rôle |
|--------|-------------|------|
| LLM | OpenRouter | Génération de requêtes, analyse experte, synthèse |
| Framework LLM | DSPy | Prompt engineering structuré |
| Recherche web | Tavily | Recherche avec scoring et déduplication d'URLs |
| Scraping | Firecrawl | Extraction de contenu web en Markdown |
| Embeddings | Sentence-Transformers (`BAAI/bge-m3`) | Vectorisation des chunks |
| Base vectorielle | ChromaDB | Stockage et recherche des embeddings |
| Interface | Streamlit | UI web interactive |
| Configuration | python-dotenv + dataclasses | Gestion centralisée des paramètres |
| Evaluation | RAG Judge, Ragas | Métriques de qualité du retrieval et des réponses |

## Structure du projet

```
├── streamlit_app.py               # Interface Streamlit
├── clients.py                     # Clients API centralisés (OpenRouter, Tavily, Firecrawl, DSPy)
├── config.py                      # Configuration centralisée (dataclasses)
├── requirements.txt               # Dépendances Python
├── .env                           # Clés API et paramètres
│
├── pipeline/
│   ├── pipeline.py                # Orchestrateur principal (9 étapes)
│   ├── utils.py                   # Helpers du pipeline
│   └── helpers.py                 # Utilitaires (slugify, project_info_to_dict)
│
├── project_analysis/
│   ├── project_analyser.py        # Étape 1 : Analyse du projet via DSPy
│   └── DSPy_config.py             # Signature DSPy pour l'analyse de projet
│
├── queries_generator/
│   ├── query_generator.py         # Étape 2 : Générateur de requêtes
│   ├── DSPy_config.py             # Signatures DSPy (génération + dédoublonnage)
│   ├── models.py                  # AnalysisSection, SearchQuery, AnalysisOutput
│   └── utils.py                   # Parser JSON robuste pour sorties LLM
│
├── web_search/
│   ├── searcher.py                # Étape 3 : Moteur de recherche Tavily + ranking
│   └── utils.py                   # Scoring, dédup URLs, sauvegarde
│
├── scraping_cleaning/
│   ├── firecrawl_scraper.py       # Étape 4 : Scraping via Firecrawl
│   ├── content_cleaner.py         # Étape 5 : Nettoyage de contenu
│   └── models.py                  # ScrapingStats, CleaningResult
│
├── chunking/
│   ├── chunk_orchestrator.py      # Étape 6 : Orchestrateur de chunking
│   ├── markdown_chunker.py        # Découpage hiérarchique Markdown
│   ├── chunk_processor.py         # Traitement des chunks
│   └── models.py                  # Chunk, ChunkMetadata, ChunkType
│
├── embedding/
│   ├── chroma_manager.py          # Étape 7 : Gestion ChromaDB + embeddings
│   └── index_orchestrator.py      # Orchestration de l'indexation
│
├── retreiver/
│   ├── methode_retrieval.py       # Méthodes M1-M4c, NormalizedResult
│   ├── hybrid_retreiver.py        # Recherche hybride + reranking
│   ├── simple_retriever.py        # Retriever vectoriel pur
│   └── retrieval_evaluator.py     # Évaluation du retrieval
│
├── agents/
│   ├── Agents.py                  # Agents experts (Macro, Demand, Competition, SWOT)
│   ├── base_agent.py              # Agent de base avec pipeline RAG générique
│   ├── models.py                  # QuestionInput, QuestionAnalysis, SectionAnalysis
│   ├── Retrieval_strategy.py      # Configuration des stratégies de retrieval
│   ├── report_synthesis_agent.py  # Étape 9 : Synthèse du rapport
│   └── Persistence.py             # Sauvegarde analyses + dataset Ragas
│
├── evaluator/
│   ├── rag_judge.py               # Évaluation RAG (relevance, coverage, precision, diversity)
│   ├── Ragas_evaluation.py        # Évaluation Ragas des réponses d'agents
│   └── report_evaluator.py        # Évaluation de la synthèse du rapport
│
├── utils/
│   ├── logger.py                  # Configuration du logging
│   ├── files.py                   # Utilitaires fichiers
│   └── cleaner_utils.py           # Utilitaires de nettoyage
│
├── outputs/
│   └── projects/                  # Résultats d'exécution du pipeline
│
└── logs/
    └── app.log                    # Journaux d'exécution
```

## Flux du pipeline (9 étapes)

### Étape 1 — Analyse du projet
**Fichier :** `project_analysis/project_analyser.py`

Utilise DSPy + OpenRouter pour analyser la description texte du projet et extraire des structures :
- Pays cible, industrie cliente, secteur produit
- Catégorie logicielle, modèle économique
- Marché cible, personas, proposition de valeur
- Mots-clés primaires/secondaires, concurrents potentiels

Sortie : `project_info` (dict) + `ProjectInfo` (objet DSPy)

### Étape 2 — Génération de requêtes
**Fichier :** `queries_generator/query_generator.py`

Pour chacune des 4 sections d'analyse (Macro, Demande, Offre, SWOT), génère 3-4 requêtes de recherche par question majeure.

Architecture DSPy :
- `QueryGeneratorModule` : ChainOfThought pour générer des requêtes couvrant des angles différents.
- `DeduplicationModule` : Filtre les requêtes sémantiquement similaires.

Sortie : `AnalysisOutput` par section, sauvegarde en JSON.

### Étape 3 — Recherche web
**Fichier :** `web_search/searcher.py`

Exécute les requêtes via Tavily API :
- Recherche en profondeur "advanced"
- Scoring composite (fiabilité, contexte francophone, score Tavily)
- Dédup d'URLs cross-requêtes
- Sauvegarde des résultats classés

Sortie : `search_results.json` par projet.

### Étape 4 — Scraping
**Fichier :** `scraping_cleaning/firecrawl_scraper.py`

Utilise Firecrawl pour extraire le contenu Markdown des URLs trouvées :
- Retry automatique par URL
- Nettoyage d'URL
- Statistiques de scraping (succès/échecs, durées)

Sortie : fichiers Markdown dans `scraped/raw_markdown/` + `scraping_stats.json`.

### Étape 5 — Nettoyage
**Fichier :** `scraping_cleaning/content_cleaner.py`

Nettoie le contenu brut scrapé :
- Suppression des patterns de bruit (cookies, navigation, publicité)
- Décodage des URLs encodées
- Suppression des paramètres de tracking
- Extraction de métadonnées

Sortie : `cleaning_results.json`.

### Étape 6 — Chunking
**Fichier :** `chunking/chunk_orchestrator.py`

Découpe le contenu nettoyé en chunks sémantiques :
- Découpage hiérarchique Markdown
- Préservation des headers et introductions
- Overlap configurable
- Filtrage par qualité

Sortie : `chunks_consolidated.json`.

### Étape 7 — Embedding + Indexation ChromaDB
**Fichier :** `embedding/chroma_manager.py`

Génère les embeddings et indexe dans ChromaDB :
- Modèle : `BAAI/bge-m3`
- Stockage persistant dans `data/chromadb/`
- Métadonnées enrichies par chunk

Sortie : collection ChromaDB peuplée.

### Étape 8 — Analyse experte (agents parallélisés)
**Fichier :** `agents/base_agent.py`, `agents/Agents.py`

Exécute 4 agents experts en parallèle :
- `MacroAgent` : analyse macro-marché et tendances
- `DemandAgent` : demande et pain points
- `CompetitionAgent` : offre et concurrence
- `SwotAgent` : analyse SWOT

Chaque agent utilise une stratégie de retrieval configurable (M1-M4c) :
- Vector search, BM25, HyDE, reranking

Sortie : une `SectionAnalysis` par section, sauvegardée en Markdown + JSON.

### Étape 9 — Synthèse du rapport
**Fichier :** `agents/report_synthesis_agent.py`

Combine les 4 analyses de section en un rapport cohérent et professionnel :
- Résumé exécutif
- Macro-marché & tendances
- Demande & pain points
- Offre & concurrence
- SWOT
- Insights stratégiques
- Recommandations

Sortie : `market_report.md` + `market_report.json`.

## Installation

```bash
git clone <repo-url>
cd ai_market_analyser
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

## Configuration

Créez un fichier `.env` à la racine du projet avec vos clés API :

```env
OPENROUTER_API_KEY=sk-or-v1-...
TAVILY_API_KEY=tvly-...
FIRECRAWL_API_KEY=fc-...
DSPY_MODEL=openai/gpt-oss-120b
```

## Lancement

```bash
streamlit run streamlit_app.py
```

Ouvrez ensuite http://localhost:8501 dans votre navigateur.

## Entrées utilisateur

Dans l'interface Streamlit :
1. **Nom du projet** : identifiant pour le dossier de sortie
2. **Description du projet** : décrivez votre SaaS (secteur, cible, fonctionnalités, modèle économique)
3. **Options avancées** :
   - Sauter l'analyse experte (étapes 8-9)
   - Nombre de chunks récupérés par requête

## Sorties

Chaque exécution crée un dossier horodaté sous `outputs/projects/<nom_du_projet>/` :

```
outputs/projects/<nom_du_projet>/
├── analysis/
│   └── project_analysis.json
├── queries/
│   └── all_queries.json
├── search/
│   └── search_results.json
├── scraped/
│   ├── scraping_stats.json
│   └── raw_markdown/
├── cleaned/
│   └── cleaning_results.json
├── chunks/
│   └── chunks_consolidated.json
├── agents/
│   ├── macro_analysis.md
│   ├── demand_analysis.md
│   ├── supply_analysis.md
│   ├── swot_analysis.md
│   └── agents_summary.json
└── report/
    ├── market_report.md
    └── market_report.json
```

Les collections ChromaDB sont stockées dans `data/chromadb/`.

## Résilience

- Chaque étape est exécutée via `_run_step_safely`, qui uniformise la gestion d'erreur pour toutes les étapes.
- Le pipeline peut reprendre à partir des artefacts déjà sauvegardés sur disque via `resume=True`.
- Les appels réseau (Tavily, Firecrawl) sont protégés par un mécanisme de retry avec backoff exponentiel.

## Dépannage

| Problème | Solution |
|----------|----------|
| `OPENROUTER_API_KEY is required` | Vérifiez votre fichier `.env` |
| `Tavily client initialization failed` | Vérifiez `TAVILY_API_KEY` |
| `Firecrawl not configured` | Vérifiez `FIRECRAWL_API_KEY` |
| `ChromaDB import error` | Installez `chromadb` et `sentence-transformers` |
| `DSPy configuration failed` | Le flag `_dspy_configured` dans `clients.py` gère la reconfiguration thread-safe |

## Licence

Projet privé — tous droits réservés.
