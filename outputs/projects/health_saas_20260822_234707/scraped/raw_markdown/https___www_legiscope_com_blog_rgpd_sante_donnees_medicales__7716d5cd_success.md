---
url: https://www.legiscope.com/blog/rgpd-sante-donnees-medicales.html
title: RGPD et santé : protection des données médicales
section: Analyse macro marché et tendances
angle: regulatory impact of GDPR and data security on HealthTech software
question: Quelles sont les tendances technologiques et réglementaires qui façonnent le marché ?
query: réglementation RGPD et sécurité données médicales logiciels santé France
scraped_at: 2026-08-22T23:04:18.984490+00:00
scraping_duration_seconds: 22.9
attempts: 1
status: success
---

Les données de santé bénéficient du niveau de protection le plus élevé sous le RGPD. L’Art. 9(1) RGPD interdit par principe leur traitement, sauf exceptions limitativement énumérées. La [CNIL](https://www.legiscope.com/blog/sanctions-cnil-2026-bilan.html) a sanctionné Doctissimo de **380 000 euros** (Délibération n° SAN-2023-006, 11 mai 2023) pour des manquements au consentement et à la conservation des données de santé collectées via des questionnaires en ligne. Ce guide détaille le cadre juridique applicable aux données médicales et les obligations concrètes pour les acteurs de santé.

### Points Clés

- Les données de santé sont des **données sensibles** dont le traitement est interdit par principe (Art. 9(1) RGPD), sauf exceptions (Art. 9(2) RGPD).
- L’hébergement de données de santé doit être réalisé chez un **hébergeur certifié HDS** (Art. L.1111-8 du Code de la santé publique).
- Le consentement du patient n’est **pas toujours la base légale appropriée** pour les soins ; l’Art. 9(2)(h) RGPD prévoit une exception spécifique pour les finalités médicales.
- La recherche médicale utilisant des données personnelles nécessite une **autorisation CNIL** ou une conformité à un référentiel (méthodologies de référence MR).

## Qu’est-ce qu’une donnée de santé au sens du RGPD ?

L’ [Art. 4(15) RGPD](https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32016R0679) définit les données de santé comme les données à caractère personnel relatives à la santé physique ou mentale d’une personne, y compris la prestation de services de soins de santé, qui révèlent des informations sur l’état de santé de cette personne.

Cette définition est large et couvre :

- Les données médicales au sens strict : diagnostics, prescriptions, résultats d’analyses, imagerie médicale, comptes rendus opératoires.
- Les données collectées lors de l’inscription ou de l’admission dans un établissement de santé.
- Les données issues de dispositifs médicaux connectés (glycémie, tension, rythme cardiaque).
- Les données de remboursement de soins (CPAM, mutuelles) qui révèlent indirectement l’état de santé.
- Les données de bien-être lorsqu’elles sont croisées avec d’autres informations permettant d’en déduire un état de santé.

Le considérant 35 du RGPD précise que cette catégorie inclut “tout numéro, symbole ou code attribué à une personne physique pour l’identifier de manière univoque à des fins de santé”. Le numéro de sécurité sociale (NIR) est donc une donnée de santé lorsqu’il est utilisé dans un contexte médical.

## Bases légales pour le traitement des données de santé

L’Art. 9(2) RGPD prévoit dix exceptions à l’interdiction de traitement des données sensibles. Dans le domaine de la santé, trois sont principalement mobilisées.

**Art. 9(2)(h) : finalités médicales.** Cette exception couvre les traitements nécessaires aux fins de la médecine préventive ou du travail, du diagnostic médical, de la prise en charge sanitaire ou sociale, ou de la gestion des systèmes de santé. C’est la base la plus courante pour les professionnels de santé dans le cadre du soin — médecins, mais aussi [pharmaciens d’officine](https://www.legiscope.com/blog/rgpd-pharmacie.html) lorsqu’ils traitent ordonnances et dossier pharmaceutique. Elle n’exige pas le consentement du patient mais impose que le traitement soit effectué par un professionnel de santé soumis au secret professionnel.

**Art. 9(2)(a) : consentement explicite.** Le consentement est requis lorsque le traitement dépasse le cadre du soin : participation à un programme de recherche, transmission de données à des fins commerciales, inscription à une application de télémédecine. Le consentement doit être **explicite** (et non simplement “univoque” comme pour l’Art. 6) : il faut une déclaration ou un acte positif clair.

**Art. 9(2)(j) : recherche scientifique.** Les traitements à des fins de recherche scientifique ou historique, ou statistiques, peuvent être réalisés sous conditions : garanties appropriées, conformité au droit national (en France, loi Informatique et Libertés, Art. 66 et suivants).

Il ne suffit pas de remplir une condition de l’Art. 9(2) : une [base légale de l’Art. 6 RGPD](https://www.legiscope.com/blog/base-juridique-rgpd.html) doit également être identifiée pour chaque traitement.

## Hébergement des données de santé : la certification HDS

L’Art. L.1111-8 du Code de la santé publique impose que l’hébergement de données de santé à caractère personnel soit réalisé par un prestataire **certifié HDS** (Hébergeur de Données de Santé).

La certification HDS, délivrée par un organisme accrédité par le COFRAC, atteste que l’hébergeur respecte un référentiel de sécurité basé sur la norme ISO 27001, complétée d’exigences spécifiques au secteur de la santé. Elle couvre deux périmètres :

- **Hébergeur d’infrastructure physique** : mise à disposition de locaux, alimentation électrique, climatisation.
- **Hébergeur infogérant** : administration, exploitation, sauvegarde, haute disponibilité.

**Sanctions en cas de non-conformité.** L’hébergement de données de santé chez un prestataire non certifié HDS constitue un manquement à l’Art. L.1111-8 CSP, passible de sanctions pénales (3 ans d’emprisonnement et 150 000 euros d’amende) en plus des sanctions CNIL au titre du RGPD.

Les principaux hébergeurs certifiés HDS en France incluent OVHcloud, Scaleway, Outscale (Dassault Systèmes), et des acteurs spécialisés comme Cegedim Cloud et Claranet. Les hyperscalers (AWS, Azure, GCP) disposent de certifications HDS pour certaines régions.

## Recherche médicale et méthodologies de référence CNIL

Le traitement de données personnelles à des fins de recherche en santé est encadré par un dispositif spécifique en droit français.

**Les méthodologies de référence (MR).** La [CNIL](https://www.cnil.fr/) a adopté des méthodologies de référence (MR-001 à MR-006) qui dispensent les chercheurs d’une autorisation individuelle si leur recherche est conforme à la MR applicable. Le responsable de traitement doit déposer un engagement de conformité auprès de la CNIL.

- **MR-001** : recherches nécessitant le recueil du consentement (essais cliniques).
- **MR-003** : recherches ne nécessitant ni consentement ni information individuelle (études sur bases de données existantes).
- **MR-004** : recherches n’impliquant pas la personne humaine (études observationnelles).

**Accès au SNDS.** Le Système National des Données de Santé (SNDS), qui regroupe les données de l’Assurance Maladie, des hôpitaux et des causes de décès, est accessible aux chercheurs sous conditions strictes définies par le Health Data Hub et contrôlées par la CNIL.

La recherche médicale utilisant des données personnelles doit dans tous les cas respecter le principe de [minimisation](https://www.legiscope.com/blog/definition-donnees-personnelles.html) (Art. 5(1)© RGPD) et privilégier la pseudonymisation, voire l’ [anonymisation des données](https://www.legiscope.com/blog/anonymisation.html), lorsque l’identification directe n’est pas nécessaire.

## Télémédecine et applications de santé

Le développement de la télémédecine depuis 2020 a multiplié les traitements de données de santé à distance, avec des enjeux de conformité spécifiques.

**Plateformes de téléconsultation.** Les éditeurs de solutions de téléconsultation (Doctolib, Qare, Livi) sont sous-traitants au sens de l’Art. 28 RGPD vis-à-vis des professionnels de santé. Ils doivent être certifiés HDS et disposer d’un [DPA conforme](https://www.legiscope.com/blog/dpa-rgpd-guide-complet.html).

**Applications mobiles de santé.** Les applications collectant des données de santé (suivi de glycémie, santé mentale, fertilité) doivent respecter l’intégralité du RGPD : information, base légale, sécurité, durée de conservation. La [CNIL a rappelé en 2024](https://www.cnil.fr/fr/sante) que les SDK publicitaires intégrés dans les applications de santé constituent un [transfert de données](https://www.legiscope.com/blog/transferts-internationaux-donnees-rgpd.html) sensibles à des tiers non autorisés.

**Messageries sécurisées.** La transmission de données de santé par email non sécurisé constitue un manquement à l’Art. 32 RGPD. La CNIL recommande l’utilisation de messageries sécurisées de santé (MSSanté) ou de solutions chiffrées de bout en bout pour les échanges entre professionnels.

## Sanctions CNIL dans le secteur santé

Le secteur de la santé fait l’objet d’une vigilance renforcée de la CNIL.

- **Doctissimo** : 380 000 euros (Délibération n° SAN-2023-006, mai 2023) pour conservation excessive de données de santé et consentement non conforme aux cookies.
- **Dedalus Biologie** : 1,5 million d’euros (Délibération n° SAN-2022-009, avril 2022) pour une fuite de données médicales de près de 500 000 patients due à des défauts de sécurité.
- **Alliance française des maladies rares** : mise en demeure (2021) pour hébergement de données de santé chez un prestataire non certifié HDS.
- **Médecin libéral** : 3 000 euros via procédure simplifiée (2023) pour défaut de sécurisation des dossiers patients accessibles depuis internet.

Ces décisions montrent que la CNIL sanctionne à tous les niveaux : grands éditeurs, laboratoires et professionnels de santé individuels.

## FAQ

### Le médecin a-t-il besoin du consentement du patient pour traiter ses données médicales ?

Non, pas pour les soins. L’Art. 9(2)(h) RGPD prévoit une exception pour les traitements nécessaires aux fins du diagnostic médical et de la prise en charge sanitaire, réalisés par un professionnel de santé soumis au secret. Le consentement est en revanche nécessaire pour les traitements dépassant le cadre du soin : recherche, transmission à des applications tierces, utilisation à des fins commerciales.

### Qui est responsable de traitement dans un cabinet médical ?

Le professionnel de santé libéral (médecin, dentiste, sage-femme) est responsable de traitement pour les données de ses patients : voir notre guide pratique du [RGPD en cabinet médical](https://www.legiscope.com/blog/rgpd-cabinet-medical.html). Dans un établissement de santé (hôpital, clinique), c’est l’établissement qui est responsable de traitement ; il relève en outre [du secteur de la santé désormais dans le champ de NIS2](https://www.legiscope.com/blog/nis2-secteur-sante-etablissements.html) au titre de ses obligations de cybersécurité. Le logiciel de gestion de cabinet (éditeur) est sous-traitant au sens de l’Art. 28 RGPD et doit être certifié HDS s’il héberge des données de santé.

### Combien de temps un hôpital peut-il conserver un dossier médical ?

Le dossier médical doit être conservé **20 ans** à compter de la dernière consultation ou du dernier séjour (Art. R.1112-7 du Code de la santé publique). Pour les mineurs, ce délai court à partir de leur 18e anniversaire, avec un minimum de 10 ans. Ces durées sont des obligations légales qui prévalent sur les recommandations générales du RGPD.

### Les données collectées par une montre connectée sont-elles des données de santé ?

Cela dépend du contexte. Les données brutes (nombre de pas, rythme cardiaque instantané) ne sont pas systématiquement des données de santé. Elles le deviennent lorsqu’elles sont croisées ou analysées pour en déduire un état de santé (détection d’arythmie, suivi de pathologie). Le considérant 35 du RGPD adopte une interprétation large. En pratique, les fabricants de dispositifs connectés de santé doivent appliquer les protections de l’Art. 9 RGPD par précaution.

À lire aussi : [un logiciel RGPD pour la santé](https://www.legiscope.com/blog/logiciel-rgpd-sante.html).

### Automate your GDPR compliance

Save 340+ hours per year on compliance work. Legiscope provides AI-powered GDPR management trusted by compliance professionals.

[Discover Legiscope](https://www.legiscope.com/)

TD

Written by

[Dr. Thiébaut Devergranne](https://www.legiscope.com/author/thiebaut-devergranne.html)

Fondateur de Legiscope et expert RGPD

Docteur en droit de l'Université Panthéon-Assas (Paris II), 23 ans d'expérience en droit du numérique et conformité RGPD. Ancien conseiller de l'administration du Premier ministre sur la mise en œuvre du RGPD. Thiébaut est le fondateur de Legiscope, plateforme de conformité RGPD automatisée par l'IA.

[View full author profile →](https://www.legiscope.com/author/thiebaut-devergranne.html)