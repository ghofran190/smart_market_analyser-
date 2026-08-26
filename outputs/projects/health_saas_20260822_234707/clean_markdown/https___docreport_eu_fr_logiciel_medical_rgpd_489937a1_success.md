← Accueil DocReport France
Charte de Sécurité et Notice RGPD / CNIL
Sécurité Zéro-Trust & Conformité Européenne
# Logiciel Médical Conforme RGPD & CNIL : La Protection Absolue des Données Patient
La sécurité des données de santé est notre priorité absolue. DocReport est le seul scribe médical IA à implémenter le masquage local des identifiants (NIR), un chiffrement client-side Zero-Knowledge et un hébergement souverain en Europe via Vertex AI.
Découvrir le scribe sécurisé Voir l'architecture de sécurité
Entièrement conforme au secret médical et à l'article R. 1112-7 du Code de la santé publique.
## Le Cadre Réglementaire des Données de Santé en France
En France, le traitement informatique des données à caractère personnel relatives à la santé est encadré par des règles d'une rigueur exceptionnelle. Les professionnels de santé sont tenus au \*\*secret médical\*\* (article L. 1110-4 du Code de la santé publique). Toute fuite d'information ou tout hébergement non sécurisé peut engager la responsabilité pénale et ordinale du praticien.
De plus, le \*\*Règlement Général sur la Protection des Données (RGPD)\*\* de l'Union Européenne et la \*\*Loi Informatique et Libertés\*\* imposent des obligations spécifiques en matière d'analyse d'impact relative à la protection des données (AIPD), d'information claire des patients, et de sécurisation des accès physiques et logiques. DocReport a été conçu dès sa première ligne de code selon le principe du “Privacy by Design” (la protection des données par conception) pour répondre à ces exigences.
## Notre Architecture de Sécurité Zero-Trust : Comment nous protégeons vos patients
Pour assurer une sécurité maximale, nous partons du principe que le serveur cloud ne doit jamais avoir accès à des informations médicales nominatives en clair. C'est pourquoi notre système repose sur trois piliers technologiques :
- **Nettoyage local (Scrubbing) du NIR et des PII** : Lorsque vous enregistrez ou dictez une consultation, notre bibliothèque logicielle client-side `fr-compliance.ts` analyse le flux textuel dans la mémoire de votre navigateur. Tout numéro de Sécurité Sociale français (NIR à 15 chiffres) ou information nominative évidente (noms, numéros de téléphone) est extrait et remplacé par un jeton neutre (ex: `[FR_NIR_1]`) \*avant\* d'envoyer les données au serveur d'IA.
- **Chiffrement local AES-GCM 256 bits** : Une fois le rapport médical structuré généré par l'IA, il est renvoyé à votre navigateur. L'association avec l'identité réelle du patient se fait localement dans votre RAM. Avant d'être stocké en base de données cloud pour archivage, le rapport finalisé est chiffré dans votre navigateur avec l'algorithme AES-GCM 256 bits à l'aide d'une clé privée stockée dans votre stockage local (`localStorage`). Nos serveurs n'hébergent que du texte crypté indéchiffrable.
- **Souveraineté avec Vertex AI EU** : Le traitement de l'intelligence artificielle s'effectue exclusivement dans les centres de données de Google Cloud situés au sein de l'Union Européenne (multi-région EU). Aucune donnée ne sort de l'UE, et aucune information clinique n'est conservée pour l'entraînement des modèles linguistiques généraux.
## Obligation de Conservation des Dossiers Médicaux et RGPD
Une question fréquente concerne l'articulation entre le droit à l'effacement (“droit à l'oubli”) prévu par le RGPD et l'obligation de conservation des dossiers médicaux. En France, l'article R. 1112-7 du Code de la santé publique impose une durée minimale de conservation des dossiers médicaux de 20 ans à compter du dernier séjour du patient (ou jusqu'au 28ème anniversaire pour les mineurs).
Notre politique de confidentialité B2B documente explicitement ce point : l'obligation légale de conservation des dossiers par le médecin traitant \*\*prime\*\* sur les demandes simples de suppression RGPD de la part de tiers. L'archivage crypté et le maintien de la clé d'accès (dont le médecin a l'entière responsabilité) garantissent la pérennité du dossier médical conformément aux exigences légales, tout en empêchant toute exploitation non autorisée des données.
## Qui fait quoi ? Les rôles RGPD définis dans notre contrat B2B
Pour être en conformité, les rôles de traitement de données doivent être définis de manière contractuelle :
- **Le Praticien ou la Clinique** est le \*\*Responsable de Traitement\*\* (Data Controller). C'est lui qui décide de collecter les antécédents médicaux et d'effectuer l'examen clinique pour le diagnostic du patient.
- **Be Smart Global, LLC (DocReport)** agit en tant que \*\*Sous-Traitant\*\* (Data Processor) au sens de l'article 28 du RGPD. Nous fournissons l'infrastructure technologique de transcription et d'archivage chiffré sous les instructions directes du praticien.
Notre Politique de Confidentialité B2B et nos CGU intègrent des clauses contractuelles types conformes à l'Union Européenne, protégeant ainsi juridiquement votre cabinet en cas d'audit de la CNIL.
## Comparatif de Sécurité : DocReport vs Scribes IA grand public
| Caractéristique | DocReport France | Scribes IA Non-Européens |
| Hébergement des données | Union Européenne (Vertex AI EU) | États-Unis (sans isolation) |
| Nettoyage local du NIR | Oui (local client-side scrubbing) | Non (envoi brut en clair vers les API) |
| Cryptage Zero-Knowledge | Oui (chiffrement AES-GCM local) | Non (chiffré en transit uniquement) |
| Conformité RGPD / CNIL | Contrat B2B & DPO dédié | Termes grand public inadaptés aux médecins |
## Questions Fréquentes sur la Sécurité
#### DocReport est-il certifié Hébergeur de Données de Santé (HDS) ?
L'infrastructure physique sous-jacente de Google Cloud (Vertex AI) sur laquelle transitent et sont chiffrées nos données possède toutes les certifications européennes de sécurité, y compris l'agrément HDS en France et la certification ISO 27001. De plus, notre architecture Zero-Knowledge empêchant tout stockage de données de santé identifiables en clair dans le cloud rend la sécurité de notre logiciel encore plus élevée que les exigences HDS standard.
#### Que se passe-t-il si je perds ma clé de chiffrement locale ?
Par mesure de sécurité Zero-Knowledge, nous ne stockons pas votre clé de chiffrement sur nos serveurs. Lors de votre première connexion, vous devez exporter et sauvegarder votre fichier de clé dans un dossier sécurisé de votre cabinet. En cas de perte et sans sauvegarde, il vous sera impossible de lire vos anciens rapports archivés.
#### Les données de mes patients sont-elles utilisées pour entraîner l'IA ?
Non, absolument pas. Dans le cadre de nos accords d'API d'entreprise avec Vertex AI (Google Cloud EU), aucune donnée de consultation transcrite n'est enregistrée pour l'entraînement des modèles de langage globaux. Vos données restent strictement confidentielles et sous votre contrôle.
#### Puis-je signer un Accord de Traitement des Données (DPA) ?
Oui. Un accord de traitement des données (Data Processing Agreement) conforme à l'article 28 du RGPD est automatiquement inclus et signé numériquement dans nos Conditions Générales de Vente B2B lors de la création de votre compte professionnel.
### Déployez un Scribe IA 100% Conforme dans votre Cabinet
Bénéficiez du gain de temps de l'intelligence artificielle sans faire de compromis sur la confidentialité de vos patients.
Commencer l'essai gratuit de 14 jours
14 jours d'essai gratuits. Annulation en ligne en 1 clic.