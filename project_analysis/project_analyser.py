import json
import logging
import os
from typing import Any, Dict
from openai import APIError, RateLimitError
from project_analysis.DSPy_config import ProjectAnalyzerModule
from queries_generator.models import ProjectInfo


# ============================================================================
# Orchestrateur métier
# ============================================================================


class ProjectAnalyser:
    """
    Analyse une description de projet avec un LLM pour en extraire les
    informations structurées utiles à l'étude de marché SaaS.
    """

    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

    @staticmethod
    def log(message: str) -> None:
        """Log un message avec un timestamp."""
        logging.info(message)

    def validate_description(self, description: str) -> bool:
        """Valide que la description du projet est suffisamment détaillée."""
        if not description or len(description) < 100:
            raise ValueError(
                "La description du projet est trop courte. Veuillez fournir plus de détails."
            )
        return True

    def analyse_project(self, project_description: str) -> ProjectInfo:
        """
        Analyse la description du projet via DSPy et retourne un ProjectInfo.

        Args:
            project_description: texte décrivant le projet SaaS.

        Returns:
            ProjectInfo: informations structurées extraites.

        Raises:
            ValueError: si la description est trop courte ou si la construction
                        de ProjectInfo échoue.
        """
        self.validate_description(project_description)
        analyzer = ProjectAnalyzerModule()
        result = analyzer(project_description=project_description)

        try:
            project_info = ProjectInfo(
                country=result.country,
                target_market=result.target_market,
                market_category=result.market_category,
                customer_industry=result.customer_industry,
                product_sector=result.product_sector,
                software_category=result.software_category,
                business_model=result.business_model,
                personas=result.personas,
                value_proposition=result.value_proposition,
                primary_keywords=result.primary_keywords,
                secondary_keywords=result.secondary_keywords,
                potential_competitors=result.potential_competitors,
                raw_description=project_description,
            )
        except Exception as exc:
            raise ValueError(
                f"Erreur lors de la création de ProjectInfo : {exc}"
            ) from exc

        self.log(f"Industrie cliente : {project_info.customer_industry}")
        self.log(f"Secteur produit : {project_info.product_sector}")
        self.log(f"Catégorie logicielle : {project_info.software_category}")
        self.log(f"Marché cible : {project_info.target_market}")
        self.log(
            f"Concurrents potentiels : {', '.join(project_info.potential_competitors)}"
        )

        return project_info

    def validate_output(self, output: Dict[str, Any]) -> bool:
        """Vérifie la présence des champs obligatoires dans la sortie."""
        required_fields = [
            "country",
            "target_market",
            "product_sector",
            "customer_industry",
            "software_category",
            "market_category",
            "primary_keywords",
        ]

        for field in required_fields:
            if field not in output:
                raise ValueError(f"Champ manquant: {field}")

        return True

    def save_analysis(
        self,
        project_info: ProjectInfo,
        project_dir: str,
        filename: str = None,
    ) -> None:
        """
        Sauvegarde l'analyse de projet sur disque au format JSON.

        Args:
            project_info: objet ProjectInfo à sauvegarder.
            project_dir: répertoire de destination.
            filename: nom du fichier (par défaut: project_analysis1.json).
        """
        if project_dir is None:
            project_dir = "outputs/projects_analysis"

        os.makedirs(project_dir, exist_ok=True)

        if not filename:
            filename = "project_analysis1.json"

        filepath = os.path.join(project_dir, filename)

        data = (
            project_info.model_dump()
            if hasattr(project_info, "model_dump")
            else project_info.__dict__
        )

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        self.log(f"Analyse sauvegardée : {filepath}")

    def execute(self, description: str, project_dir: str = None) -> ProjectInfo | None:
        """
        Pipeline complet : analyse, validation et sauvegarde.

        Args:
            description: description du projet SaaS.
            project_dir: répertoire de sortie (par défaut: data_testing/projects_analysis).

        Returns:
            ProjectInfo si tout réussit, None sinon.
        """
        try:
            if project_dir is None:
                project_dir = "data_testing/projects_analysis"

            project_info = self.analyse_project(description)
            self.validate_output(project_info.__dict__)
            self.save_analysis(project_info, project_dir)
            self.log("Analyse terminée avec succès!")

            return project_info

        except (ValueError, APIError, RateLimitError) as exc:
            self.log(f"Erreur analyse projet : {exc}")
            return None


# ============================================================================
# Point d'entrée
# ============================================================================


if __name__ == "__main__":
    analyser = ProjectAnalyser()
    description = (
        "Je souhaite développer une plateforme SaaS destinée aux hôtels indépendants "
        "permettant de gérer les réservations, la tarification dynamique et la relation client."
    )

    result = analyser.execute(description, project_dir="data")
    if result:
        print("\nRésumé de l'analyse :")
        print(f"Marché cible : {result.target_market}")
        print(f"Proposition de valeur : {result.value_proposition}")
