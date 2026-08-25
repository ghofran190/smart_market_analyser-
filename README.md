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
