import streamlit as st
import sys
import os
import io
import json
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from pipeline.pipeline import Pipeline, PipelineRunConfig

import markdown as md_lib
from xhtml2pdf import pisa


# ============================================================================
# CONFIG PAGE
# ============================================================================

st.set_page_config(
    page_title="AI Market Search SaaS",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# STYLE
# ============================================================================

def inject_css():
    st.markdown(
        """
        <style>
        .main { background-color: #f7f8fa; }

        .hero {
            padding: 2.2rem 2rem;
            border-radius: 16px;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #2563eb 100%);
            color: white;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 30px rgba(79, 70, 229, 0.25);
        }
        .hero h1 { margin: 0; font-size: 2rem; font-weight: 800; }
        .hero p { margin-top: .4rem; opacity: .92; font-size: 1.02rem; }

        .metric-card {
            background: white;
            border-radius: 14px;
            padding: 1.1rem 1.2rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.06);
            border: 1px solid #eef0f4;
            height: 100%;
        }
        .metric-card h4 {
            margin: 0 0 .4rem 0;
            font-size: .8rem;
            text-transform: uppercase;
            letter-spacing: .04em;
            color: #6b7280;
        }
        .metric-card p { margin: 0; font-size: 1rem; color: #111827; font-weight: 500; }

        .status-pill {
            display: inline-block;
            padding: .25rem .75rem;
            border-radius: 999px;
            font-size: .8rem;
            font-weight: 700;
        }
        .status-ok { background: #dcfce7; color: #166534; }
        .status-skipped { background: #fef9c3; color: #854d0e; }
        .status-failed { background: #fee2e2; color: #991b1b; }

        .stButton > button {
            color: white;
            background: linear-gradient(135deg, #4f46e5, #7c3aed);
            border: none;
            border-radius: 10px;
            padding: .6rem 1.4rem;
            font-weight: 700;
            transition: all .15s ease;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(124, 58, 237, 0.35);
        }

        .report-box {
            background: white;
            border-radius: 14px;
            padding: 1.8rem 2rem;
            border: 1px solid #eef0f4;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_pill(status: str) -> str:
    css_class = {"ok": "status-ok", "skipped": "status-skipped", "failed": "status-failed"}.get(
        status, "status-skipped"
    )
    label = {"ok": "✅ OK", "skipped": "⏭️ Sautée", "failed": "❌ Échouée"}.get(status, status)
    return f'<span class="status-pill {css_class}">{label}</span>'


# ============================================================================
# PDF EXPORT
# ============================================================================

def markdown_to_pdf_bytes(markdown_text: str, title: str = "Rapport de marché") -> bytes:
    """Convertit du contenu Markdown en PDF (pur Python, aucun binaire externe requis)."""
    html_body = md_lib.markdown(
        markdown_text, extensions=["tables", "fenced_code", "toc"]
    )
    html_doc = f"""
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #1f2937; line-height: 1.5; }}
        h1 {{ color: #4f46e5; font-size: 20pt; border-bottom: 2px solid #4f46e5; padding-bottom: 6px; }}
        h2 {{ color: #4338ca; font-size: 15pt; margin-top: 22px; }}
        h3 {{ color: #374151; font-size: 12.5pt; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; font-size: 9.5pt; text-align: left; }}
        th {{ background-color: #eef2ff; }}
        code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }}
        .cover {{ text-align: center; margin-bottom: 40px; }}
    </style>
    </head>
    <body>
        <div class="cover">
            <h1>{title}</h1>
            <p>Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
        </div>
        {html_body}
    </body>
    </html>
    """
    buffer = io.BytesIO()
    pisa.CreatePDF(src=html_doc, dest=buffer, encoding="utf-8")
    return buffer.getvalue()


# ============================================================================
# PIPELINE (mise en cache de l'instance : évite de recréer les clients API
# à chaque interaction Streamlit, car le script entier est réexécuté)
# ============================================================================

@st.cache_resource(show_spinner=False)
def get_pipeline() -> Pipeline:
    return Pipeline()


# ============================================================================
# UI HELPERS
# ============================================================================

def render_project_info(project_info: dict):
    cols = st.columns(3)
    fields = [
        ("🎯 Marché cible", project_info.get("target_market", "N/A")),
        ("🏷️ Secteur produit", project_info.get("product_sector", "N/A")),
        ("💻 Catégorie logicielle", project_info.get("software_category", "N/A")),
        ("🏭 Industrie cliente", project_info.get("customer_industry", "N/A")),
        ("💰 Modèle économique", project_info.get("business_model", "N/A")),
        ("🌍 Pays", project_info.get("country", "N/A")),
    ]
    for i, (label, value) in enumerate(fields):
        with cols[i % 3]:
            st.markdown(
                f'<div class="metric-card"><h4>{label}</h4><p>{value}</p></div>',
                unsafe_allow_html=True,
            )
            st.write("")

    st.write("")
    st.markdown("**💡 Proposition de valeur**")
    st.info(project_info.get("value_proposition", "N/A"))

    competitors = project_info.get("potential_competitors", [])
    if competitors:
        st.markdown("**⚔️ Concurrents potentiels**")
        st.write(", ".join(competitors) if isinstance(competitors, list) else competitors)


def render_steps_summary(steps: dict):
    st.markdown("### 🧩 Détail des étapes du pipeline")
    labels = {
        "analysis": "1. Analyse du projet",
        "queries": "2. Génération de requêtes",
        "search": "3. Recherche web",
        "scraping": "4. Scraping",
        "cleaning": "5. Nettoyage",
        "chunking": "6. Chunking",
        "indexing": "7. Embedding & Indexation",
        "agents": "8. Analyse experte (agents)",
        "synthesis": "9. Synthèse du rapport",
    }
    for key, label in labels.items():
        info = steps.get(key, {})
        status = info.get("status", "n/a")
        with st.container():
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{label}**")
            c2.markdown(status_pill(status), unsafe_allow_html=True)
            if info.get("reason"):
                st.caption(f"↳ {info['reason']}")


def render_final_report(result: dict):
    """Affiche le rapport final s'il est disponible, avec export MD / JSON / PDF."""
    report_path = result.get("report_path")
    synthesis = result.get("steps", {}).get("synthesis", {})

    if not report_path or not os.path.exists(report_path):
        reason = synthesis.get("reason", "raison inconnue")
        st.warning(
            f"⚠️ Le rapport final n'est pas disponible (étape sautée ou échouée — raison : `{reason}`)."
        )
        return

    with open(report_path, "r", encoding="utf-8") as f:
        report_md = f.read()

    st.markdown("### 📄 Rapport final")
    st.markdown(f'<div class="report-box">{"" }</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(report_md)

    st.write("")
    dl1, dl2, dl3 = st.columns(3)

    with dl1:
        st.download_button(
            "⬇️ Télécharger en Markdown",
            data=report_md,
            file_name="rapport_marche.md",
            mime="text/markdown",
            use_container_width=True,
        )

    json_path = synthesis.get("json_path") or result.get("json_path")
    if json_path and os.path.exists(json_path):
        with dl2:
            with open(json_path, "r", encoding="utf-8") as f:
                st.download_button(
                    "⬇️ Télécharger en JSON",
                    data=f.read(),
                    file_name="rapport_marche.json",
                    mime="application/json",
                    use_container_width=True,
                )

    with dl3:
        with st.spinner("Génération du PDF..."):
            pdf_bytes = markdown_to_pdf_bytes(report_md, title="Rapport d'étude de marché")
        st.download_button(
            "📕 Exporter en PDF",
            data=pdf_bytes,
            file_name="rapport_marche.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ============================================================================
# MAIN
# ============================================================================

def main():
    inject_css()

    st.markdown(
        """
        <div class="hero">
            <h1>🚀 Smart Market Analyser</h1>
            <p>Votre agent IA pour l'analyse de marché SaaS et la découverte d'opportunités</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("⚙️ Comment ça marche")
        st.markdown(
            """
**4 grandes phases :**
1. Analyse du projet
2. Recherche & collecte de données
3. Indexation RAG (ChromaDB)
4. Agents experts + génération du rapport

**Le rapport final couvre :**
- 📈 Macro-marché & tendances
- 🎯 Demande & points de douleur
- ⚔️ Offre & concurrence
- 🧭 Analyse SWOT
- 💡 Insights & recommandations
            """
        )
        st.divider()
        st.caption("Réglages avancés")
        skip_agents = st.checkbox("Sauter les agents experts (rapide, sans rapport)", value=False)
        chunks_per_query = st.slider("Chunks récupérés par requête", 10, 50, 30, step=5)

    st.header("📝 Description du projet")

    col_name, col_desc = st.columns([1, 3])
    with col_name:
        project_name = st.text_input(
            "Nom du projet",
            placeholder="mon_projet_pms",
            help="Utilisé pour nommer le dossier de sortie",
        )
    with col_desc:
        project_description = st.text_area(
            "Décrivez votre projet SaaS :",
            height=160,
            placeholder=(
                "Exemple : Je veux créer une plateforme SaaS de gestion de projet pour les "
                "équipes marketing en France. Fonctionnalités clés : planification de "
                "campagnes, suivi des KPIs, collaboration temps réel, intégration réseaux "
                "sociaux. Modèle freemium (29€ / 99€ par mois)."
            ),
            help="Plus la description est détaillée, meilleure sera l'analyse",
        )

    launch = st.button("🚀 Lancer l'analyse", use_container_width=False)

    if launch:
        if not project_description.strip():
            st.error("Merci de décrire votre projet avant de lancer l'analyse.")
            return
        if not project_name.strip():
            project_name = "projet_" + datetime.now().strftime("%Y%m%d_%H%M%S")

        config = PipelineRunConfig(
            project_name=project_name,
            project_description=project_description,
            skip_agents=skip_agents,
            chunks_per_query=chunks_per_query,
        )

        pipeline = get_pipeline()
        with st.spinner("⏳ Analyse en cours... cela peut prendre plusieurs minutes."):
            result = pipeline.run(config)

        # Stocké dans session_state : indispensable, car Streamlit réexécute
        # tout le script à chaque interaction (ex: clic sur un download_button)
        # et une nouvelle instance perdrait sinon le résultat précédent.
        st.session_state["last_result"] = result

    result = st.session_state.get("last_result")

    if result:
        st.divider()

        if result.get("status") == "ok":
            st.success(f"✅ Analyse terminée en {result.get('duration_seconds', 0):.1f}s")
        else:
            st.error(f"❌ Pipeline terminé avec erreurs : {result.get('error', 'inconnue')}")

        tab_overview, tab_steps, tab_report = st.tabs(
            ["📊 Vue d'ensemble", "🧩 Étapes détaillées", "📄 Rapport final"]
        )

        with tab_overview:
            project_info = result.get("project_info", {})
            if project_info:
                render_project_info(project_info)
            st.caption(f"📁 Dossier projet : `{result.get('project_dir')}`")
            st.caption(f"🗂️ Collection ChromaDB : `{result.get('collection_name', 'N/A')}`")

        with tab_steps:
            render_steps_summary(result.get("steps", {}))

        with tab_report:
            render_final_report(result)


if __name__ == "__main__":
    main()
    