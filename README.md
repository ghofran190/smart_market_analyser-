# AI Market Analyser

Plateforme d'analyse de marché SaaS intelligente, alimentee par l'IA. Elle prend en entree la description d'un projet SaaS et produit automatiquement un rapport de marche complet en 9 etapes, en s'appuyant sur une architecture RAG (Retrieval-Augmented Generation) avancee.

---

## Vue d'ensemble

L'utilisateur decrit son projet SaaS via une interface Streamlit. Le systeme :

1. Analyse la description pour extraire les caracteristiques du marche.
2. Genere des requetes de recherche ciblees pour 4 sections d'analyse.
3. Recherche des sources sur le web via Tavily.
4. Scrape le contenu des pages trouvees via Firecrawl.
5. Nettoie et structure le contenu brut.
6. Decoupe le contenu en chunks semantiques.
7. Genere des embeddings et indexe les chunks dans ChromaDB.
8. Execute des agents experts pour analyser chaque section avec une strategie de retrieval hybride (M4c).
9. Synthetise les analyses en un rapport professionnel.

Le rapport final inclut un resume executif, l'analyse macro-marche, la demande et pain points, l'offre et concurrence, une SWOT, des insights strategiques et des recommandations. Il peut etre exporte en PDF, Markdown ou JSON.

---

## Architecture globale

```
utilisateur
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit App                            │
│          (streamlit_app.py)                                 │
│  - Interface de saisie du projet                            │
│  - Lancement du pipeline                                    │
│  - Affichage de la progression                              │
│  - Visualisation du rapport + export PDF/JSON               │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline (pipeline.py)                    │
│  Orchestrateur des 9 etapes, gestion des sorties            │
└─────────────────────────┬───────────────────────────────────┘
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
┌──────────┐      ┌──────────────┐    ┌──────────────┐
│ project_  │      │   queries_   │    │    web_      │
│ analysis │      │  generator   │    │   search     │
└──────────┘      └──────────────┘    └──────────────┘
     │                    │                    │
     ▼                    ▼                    ▼
┌──────────┐      ┌──────────────┐    ┌──────────────┐
│ scraping │      │  chunking    │    │  embedding   │
└──────────┘      └──────────────┘    └──────────────┘
     │                    │                    │
     └────────────────────┼────────────────────┘
                          ▼
                ┌──────────────────┐
                │      agents      │
                │  (Macro, Demand, │
                │ Competition, SWOT│
                │  + Synthesis)    │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │    evaluator     │
                │ RAG Judge /      │
                │ Retrieval Eval / │
                │ Ragas            │
                └──────────────────┘
```

---

## Stack technique

| Couche | Technologie | Role |
|--------|-------------|------|
| LLM | OpenRouter (OpenAI-compatible) | Generation de requetes, analyse experte, synthese |
| Framework LLM | DSPy | Prompt engineering structure (ChainOfThought, signatures) |
| Recherche web | Tavily | Recherche web avec scoring et dedup d'URLs |
| Scraping | Firecrawl | Extraction de contenu web en Markdown |
| Embeddings | Sentence-Transformers (`BAAI/bge-m3`) | Vectorisation des chunks |
| Base vectorielle | ChromaDB | Stockage et recherche des embeddings |
| Retrieval | Hybrid (Vector + BM25) + Reranking + HyDE | Methodes M1-M4c pour la recuperation |
| Interface | Streamlit | UI web interactive |
| Configuration | python-dotenv + dataclasses | Gestion centralisee des parametres |
| Evaluation | RAG Judge, RetrievalEvaluator, Ragas | Metriques de qualite du retrieval et des reponses |

---

## Structure du projet

```
mes_fichier/
├── streamlit_app.py          # Interface Streamlit
├── clients.py                # Clients API centralises (OpenRouter, Tavily, Firecrawl, DSPy)
├── config.py                 # Configuration centralisee (dataclasses)
├── requirements.txt          # dependances Python
├── .env                      # Cles API et parametres
│
├── pipeline/
│   ├── pipeline.py           # Orchestrateur principal (9 etapes)
│   ├── utils.py              # Helpers du pipeline (parse JSON, log steps)
│   └── helpers.py            # Utilitaires (slugify, project_info_to_dict)
│
├── project_analysis/
│   ├── project_analyser.py   # Etape 1 : Analyse du projet via DSPy
│   └── DSPy_config.py        # Signature DSPy pour l'analyse de projet
│
├── queries_generator/
│   ├── query_generator.py    # Etape 2 : Generateur de requetes
│   ├── DSPy_config.py        # Signatures DSPy (generation + dedup)
│   ├── models.py             # AnalysisSection, SearchQuery, AnalysisOutput
│   └── utils.py              # Parser JSON robuste pour sorties LLM
│
├── web_search/
│   ├── search.py             # Moteur de recherche Tavily + ranking
│   └── utils.py              # Scoring, dedup URLs, sauvegarde
│
├── scraping/
│   ├── firecrawl_scraper.py  # Etape 4 : Scraping via Firecrawl
│   ├── content_cleaner.py    # Etape 5 : Nettoyage de contenu
│   └── models.py             # ScrapingStats, CleaningResult
│
├── chunking/
│   ├── chunk_orchestrator.py # Etape 6 : Orchestrateur de chunking
│   ├── markdown_chunker.py   # Decoupage hierarchique Markdown
│   ├── chunk_processor.py    # Traitement des chunks
│   └── models.py             # Chunk, ChunkMetadata, ChunkType
│
├── embedding/
│   ├── chroma_manager.py     # Etape 7 : Gestion ChromaDB + embeddings
│   └── index_orchestrator.py # Orchestration de l'indexation
│
├── retreiver/
│   ├── methode_retrieval.py  # Methodes M1-M4c, NormalizedResult
│   ├── hybrid_retreiver.py   # Recherche hybride + reranking
│   ├── rtriever.py           # Retriever vectoriel pur
│   └── retrieval_evaluator.py # Evaluation du retrieval (relevance, coverage, diversity)
│
├── agents/
│   ├── Agents.py             # Agents experts (Macro, Demand, Competition, SWOT)
│   ├── base_agent.py         # Agent de base avec pipeline RAG generique
│   ├── models.py             # QuestionInput, QuestionAnalysis, SectionAnalysis
│   ├── Retrieval_strategy.py # Configuration des strategies de retrieval
│   ├── report_synthesis_agent.py  # Etape 9 : Synthese du rapport
│   └── Persistence.py        # Sauvegarde analyses + dataset Ragas
│
├── evaluator/
│   ├── rag_judge.py          # Evaluation RAG (relevance, coverage, precision, diversity)
│   └── Ragas_evaluation.py   # Evaluation Ragas des reponses d'agents
│
├── utils/
│   ├── logger.py             # Configuration du logging
│   ├── files.py              # Utilitaires fichiers
│   └── cleaner_utils.py      # Utilitaires de nettoyage
│
├── data/
│   └── chromadb/             # Stockage persistant ChromaDB
│
├── outputs/
│   └── projects/             # Resultats d'execution du pipeline
│
└── logs/
    └── app.log               # Journaux d'execution
```

---

## Flux du pipeline (9 etapes)

### Etape 1 — Analyse du projet
**Fichier :** `project_analysis/project_analyser.py`

Utilise DSPy + OpenRouter pour analyser la description texte du projet et extraire des structures :
- Pays cible, industrie cliente, secteur produit
- Categorie logicielle, modele economique
- Marche cible, personas, proposition de valeur
- Mots-cles primaires/secondaires, concurrents potentiels

Sortie : `project_info` (dict) + `ProjectInfo` (objet DSPy)

---

### Etape 2 — Generation de requetes
**Fichier :** `queries_generator/query_generator.py`

Pour chacune des 4 sections d'analyse (Macro, Demande, Offre, SWOT), genere 3-4 requetes de recherche par question majeure.

Architecture DSPy :
- `QueryGeneratorModule` : ChainOfThought pour generer des requetes couvrant des angles differents.
- `DeduplicationModule` : Filtre les requetes semantiquement similaires.

Sortie : `AnalysisOutput` par section, sauvegarde en JSON.

---

### Etape 3 — Recherche web
**Fichier :** `web_search/search.py`

Execute les requetes via Tavily API :
- Recherche en profondeur "advanced"
- Scoring composite (fiabilite, contexte francophone, score Tavily)
- Dedup d'URLs cross-requetes
- Sauvegarde des resultats classes

Sortie : `search_results.json` par projet.

---

### Etape 4 — Scraping
**Fichier :** `scraping/firecrawl_scraper.py`

Utilise Firecrawl pour extraire le contenu Markdown des URLs trouvees :
- Retry automatique par URL
- Nettoyage d'URL
- Statistiques de scraping (succes/echecs, durees)

Sortie : fichiers Markdown dans `scraped/raw_markdown/` + `scraping_stats.json`.

---

### Etape 5 — Nettoyage
**Fichier :** `scraping/content_cleaner.py`

Nettoie le contenu brut scrape :
- Suppression des patterns de bruit (cookies, navigation, publicite)
- Decodage des URLs encodees
- Suppression des parametres de tracking
- Extraction de metadonnees

Sortie : `cleaning_results.json`.

---

### Etape 6 — Chunking
**Fichier :** `chunking/markdown_chunker.py`

Decoupe hierarchiquement les documents Markdown en chunks :
- Preservation de la structure (H1-H4, listes, tableaux, code)
- Chunks ancrees sur la hierarchie de titres
- Metadonnees enrichies (chemin de headings, type de contenu, presence de chiffres/dates)

Sortie : `chunks_consolidated.json` + rapport de chunking.

---

### Etape 7 — Embedding & Indexation
**Fichier :** `embedding/chroma_manager.py`

- Vectorisation des chunks avec `BAAI/bge-m3` (Sentence-Transformers)
- Indexation dans ChromaDB avec une collection dediee par projet
- Sauvegarde des resultats d'indexation

Sortie : Collection ChromaDB + `indexing_results.json`.

---

### Etape 8 — Analyse experte (Agents)
**Fichier :** `agents/base_agent.py`, `agents/Agents.py`

4 agents experts, un par section d'analyse, utilisant une strategie de retrieval hybride avancee (M4c) :

| Agent | Section | Questions par defaut |
|-------|---------|---------------------|
| `MacroAgent` | Analyse Macro-Marche | Structure du marche, tendances technologiques/reglementaires, facteurs macro-economiques |
| `DemandAgent` | Demande & Pain Points | Segments clientele, pain points, criteres de decision |
| `CompetitionAgent` | Offre & Concurrence | Acteurs majeurs, parts de marche, barrieres a l'entree |
| `SwotAgent` | SWOT | Forces/faiblesses internes, opportunites/menaces externes |

Pour chaque agent :
1. Generation de sous-requetes HyDE (Hypothetical Document Embeddings)
2. Retrieval hybride (vector + BM25) avec fusion multi-requetes
3. Reranking avec cross-encoder
4. Generation de reponse par le LLM
5. Synthese de la section

Sortie : `*_analysis.md` + `*_analysis.json` par section + `agents_summary.json`.

---

### Etape 9 — Synthese du rapport
**Fichier :** `agents/report_synthesis_agent.py`

Combine les 4 analyses de section en un rapport coherent et professionnel :
- Resume executif
- Apercu du projet
- Analyses detaillees (Macro, Demande, Concurrence, SWOT)
- Insights strategiques
- Recommandations evidence-based
- Conclusion

Sortie : `market_report.md` + `market_report.json`.

---

## Systeme de retrieval

Le projet implemente plusieurs methodes de retrieval, de M1 (pur vectoriel) a M4c (hybride multi-requetes + HyDE + reranking) :

```
M1 : Vector search + reranking
M2 : Hybrid search (vector + BM25) + reranking
M3a : Vector + HyDE (generation de reponse hypothetique) + reranking
M3b : Multi-requetes vectorielles + fusion + reranking
M4a : Multi-requetes hybrides + fusion + reranking
M4b : Hybride + HyDE sur la requete originale + reranking
M4c : Hybride + multi-requetes + HyDE + reranking  (par defaut)
```

**Composants cles :**
- `Retriever` : recherche vectorielle pure dans ChromaDB
- `HybridRetriever` : combinaison vector + BM25 avec Reciprocal Rank Fusion
- `HyDEGenerator` : generation de reponses hypothetiques pour ameliorer le retrieval
- `HybridResultReporter` : aggregation et normalisation des scores

---

## Evaluation

### RAG Judge (`evaluator/rag_judge.py`)
Evalue la qualite du retriever sur 4 metriques :
- **Relevance** : pertinence des chunks recuperes (hybride LLM + score ChromaDB)
- **Context Precision** : proportion de chunks vraiment utiles
- **Coverage** : couverture des sous-aspects de la question
- **Diversity** : dissimilarite lexicale entre chunks

### RetrievalEvaluator (`retreiver/retrieval_evaluator.py`)
Evaluation normalisee du retrieval avec :
- Relevance hybride (LLM + heuristic)
- Coverage par aspects (embedding-based)
- Diversity lexicale + semantique

### Ragas (`evaluator/Ragas_evaluation.py`)
Evaluation de la qualite des reponses generees par les agents avec les metriques Ragas.

---

## Configuration

### Fichier `.env`

```env
# OpenRouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=openai/gpt-4.1-mini

# Tavily
TAVILY_API_KEY=tvly-...
TAVILY_SEARCH_DEPTH=advanced
TAVILY_MAX_RESULTS=5

# Firecrawl
FIRECRAWL_API_KEY=fc-...
FIRECRAWL_TIMEOUT=30
FIRECRAWL_MAX_PAGES=5

# DSPy
DSPY_MODEL=openai/gpt-4.1-mini
DSPY_TEMPERATURE=0.2

# Chunker
CHUNKER_MAX_SIZE=1000
CHUNKER_MIN_SIZE=100
CHUNKER_OVERLAP=100
```

### Configuration centralisee (`config.py`)

Tous les parametres sont geres via des dataclasses Python :
- `TavilyConfig` : configuration de la recherche web
- `FirecrawlConfig` : configuration du scraping
- `OpenRouterConfig` : configuration du LLM
- `DSPyConfig` : configuration DSPy
- `CleanerConfig` : parametres de nettoyage
- `ChunkerConfig` : parametres de decoupage

---

## Setup

```bash
# Creer un environnement virtuel
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Installer les dependances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Editer .env avec vos cles API

# Lancer l'application
streamlit run streamlit_app.py
```

---

## Utilisation

### Interface Streamlit

1. **Decrire le projet** : saisir un nom et une description detaillee du projet SaaS.
2. **Lancer l'analyse** : cliquer sur le bouton de lancement.
3. **Suivre la progression** : timeline visuelle des 9 etapes avec statuts en temps reel.
4. **Consulter le rapport** : visualization du rapport genere avec metriques resume.
5. **Exporter** : telechargement en PDF, Markdown ou JSON.
6. **Sources** : consultation des URLs source utilisees dans l'etude.

### Usage programmatique

```python
from pipeline.pipeline import Pipeline

pipeline = Pipeline()
result = pipeline.run(
    project_description="Je souhaite lancer une plateforme SaaS...",
    num_queries=4,
    search_max_results=5,
    retrieval_method="M4c",
    chunks_per_query=30,
)

print(result["report_path"])
print(result["collection_name"])
```

---

## Modeles de donnees cles

| Modele | Fichier | Description |
|--------|---------|-------------|
| `ProjectInfo` | `queries_generator/models.py` | Informations extraites du projet |
| `SearchQuery` | `queries_generator/models.py` | Requete avec angle et score de pertinence |
| `AnalysisOutput` | `queries_generator/models.py` | Resultat de generation de requetes par section |
| `ScrapingStats` | `scraping/models.py` | Statistiques de scraping |
| `Chunk` / `ChunkMetadata` | `chunking/models.py` | Chunk semantique avec metadonnees |
| `NormalizedResult` | `retreiver/methode_retrieval.py` | Resultat de retrieval normalise |
| `QuestionInput` | `agents/models.py` | Question + sous-requetes HyDE |
| `QuestionAnalysis` | `agents/models.py` | Reponse a une question avec chunks utilises |
| `SectionAnalysis` | `agents/models.py` | Analyse complete d'une section |
| `ReportSynthesisResult` | `agents/report_synthesis_agent.py` | Rapport final synthetise |

---

## Points de conception cles

| Choix | Justification |
|-------|---------------|
| DSPy ChainOfThought | Force un raisonnement etape-par-etape → meilleure diversite des angles |
| Pipeline en 2 etapes (generation → dedup) | Separation des responsabilites ; la dedup attrape les recouvrements subtils |
| Champ `angle` par requete | Tracking explicite des angles pour eviter les doublons semantiques |
| Requetes multilingues | Francais + Anglais → sources differentes, pas de recouvrement d'URLs |
| Tri par `relevance_score` | Les meilleures requetes sont executees en premier |
| Dedup d'URLs par hash | Dedup cross-requetes au niveau des resultats de recherche |
| Retrieval M4c par defaut | Meilleur compromis precision/rappel avec HyDE + hybrid + reranking |
| Chunking hierarchique | Preserve la structure documentaire pour un retrieval plus pertinent |
| Metadonnees enrichies | Chemin de headings, type de contenu, presence de chiffres/dates |
| Centralisation des clients | `clients.py` + `config.py` pour une configuration unique et reutilisable |

---

## Arborescence de sortie

Chaque execution du pipeline cree un dossier horodate dans `outputs/projects/` :

```
outputs/projects/YYYYMMDD_HHMMSS_slug_projet/
├── analysis/
│   └── project_analysis.json
├── queries/
│   └── all_queries.json
├── search/
│   └── search_results.json
├── scraped/
│   ├── raw_markdown/          # Fichiers Markdown scrapes
│   └── scraping_stats.json
├── cleaned/
│   └── cleaning_results.json
├── chunks/
│   └── chunks_consolidated.json
├── index/
│   └── indexing_results.json
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

---

## Depannage

| Probleme | Solution |
|----------|----------|
| `DSPy configuration failed: thread that initially configured it` | Le flag `_dspy_configured` dans `clients.py` gere le re-configuration thread-safe |
| `Could not parse LLM output as JSON` | Le parser de `queries_generator/utils.py` tente plusieurs strategies (JSON complet, extraction de tableau, ligne par ligne) |
| `ChromaDB import error` | Installer `chromadb` et `sentence-transformers` |
| `Firecrawl not configured` | Verifier `FIRECRAWL_API_KEY` dans `.env` |
| `Tavily search error` | Verifier `TAVILY_API_KEY` dans `.env` |
| `torch._C._get_custom_class_python_wrapper` | Avertissement connu de compatibilite PyTorch/Streamlit, non bloquant |

---

## Licence

Projet prive — tous droits reserves.
