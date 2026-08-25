
import dspy

# ============================================================================
# DSPy — Signature & Module
# ============================================================================


class ProjectAnalysisSignature(dspy.Signature):
    """
    Analyse une description de projet et extrait les informations
    nécessaires à une étude de marché SaaS.
    """

    project_description = dspy.InputField(
        desc="Description complète du projet, de la solution proposée et des clients visés."
    )

    country = dspy.OutputField(
        desc="Pays ou région géographique du marché cible. Exemples : France, Europe, Amérique du Nord, Asie-Pacifique. Par défaut, on peut supposer que le marché est en France si non précisé."
    )
    customer_industry = dspy.OutputField(
        desc="Secteur économique des clients utilisateurs finaux. Exemples : Hôtellerie, Santé, Éducation, Construction, Retail, Finance. Ne pas répondre par un secteur logiciel."
    )
    product_sector = dspy.OutputField(
        desc="Secteur technologique du produit développé. Exemples : Hospitality SaaS, HR Tech, FinTech, MarTech, EdTech, HealthTech, Cybersecurity. Ne pas répondre par l'industrie cliente."
    )
    software_category = dspy.OutputField(
        desc="Catégorie logicielle standard la plus précise possible. Exemples : CRM, ERP, ATS, Property Management System (PMS), Revenue Management System (RMS), Help Desk, Marketing Automation."
    )
    target_market = dspy.OutputField(
        desc="Segment de marché ciblé avec niveau de précision maximal : type d'organisation, taille, localisation, maturité ou secteur."
    )
    business_model = dspy.OutputField(
        desc="Modèle économique principal. Exemples : B2B SaaS, B2C SaaS, Marketplace, Freemium, Subscription, Transaction Fee."
    )
    personas = dspy.OutputField(
        desc="Liste des principaux décideurs, acheteurs et utilisateurs du produit."
    )
    value_proposition = dspy.OutputField(
        desc="Résumé en 1 ou 2 phrases de la valeur unique apportée aux clients."
    )
    primary_keywords = dspy.OutputField(
        desc="3 à 5 mots-clés stratégiques représentant le marché logiciel étudié, utiles pour le market sizing et l'analyse concurrentielle."
    )
    secondary_keywords = dspy.OutputField(
        desc="5 à 10 mots-clés complémentaires incluant technologies, usages, problèmes clients et terminologie métier."
    )
    potential_competitors = dspy.OutputField(
        desc="Liste de concurrents réels proposant des produits similaires ou substituables."
    )
    market_category = dspy.OutputField(
        desc="Nom du marché à analyser pour les recherches. Exemples : Hospitality SaaS Market, CRM Software Market, HR Software Market, Revenue Management Software Market."
    )


class ProjectAnalyzerModule(dspy.Module):
    """
    Analyse une description de projet et extrait
    les informations nécessaires à l'étude de marché.
    """

    def __init__(self):
        super().__init__()
        self.extract = dspy.ChainOfThought(ProjectAnalysisSignature)

    def forward(self, project_description: str):
        analysis = self.extract(project_description=project_description)
        return analysis

