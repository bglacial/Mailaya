# Historique des versions

## 0.4.0 (7 octobre 2026)

Mailaya passe de l’analyse ponctuelle au tri quotidien : retrouver les messages importés, suivre les demandes et préparer un brief, avec une interface organisée par tâche.

### Nouvelles fonctions

- Vue À traiter, suivi personnel À faire / Traité / Reporté et retour automatique des reports arrivés à échéance.
- Recherche classique, filtres, pagination, vues favorites et regroupement des conversations.
- Corrections persistantes et règles personnelles, en conservant la prédiction initiale du modèle.
- Synchronisation IMAP incrémentale, manuelle ou périodique sur activation explicite.
- Historique, exports CSV/JSON et comparaison LAYA / Julia sur le même lot importé.
- Brief quotidien local sans LLM, enrichissement génératif facultatif et accès aux messages sources.
- Recherche en langage naturel traduite en filtres validés et modifiables.
- Connexions oMLX, Ollama et API compatible OpenAI, avec récupération des modèles et clés chiffrées.
- Notifications navigateur facultatives lorsque la page reste ouverte.

### Interface et documentation

- Quatre espaces : Messages, Brief quotidien, Analyses et Paramètres.
- Liste allégée et volet de lecture ; corrections et détails du classement se déplient à la demande.
- Réglages progressifs par boîte, conservation des saisies pendant la navigation et protection contre leur abandon involontaire.
- Présentation adaptée aux écrans étroits, navigation clavier et polices système sans téléchargement externe.
- Guide en français intégré à l’application : objectif, installation, configuration, fonctions, sauvegarde et dépannage.

### Installation et mise à jour

Consultez [USER_GUIDE.md](USER_GUIDE.md) pour les instructions complètes.

Pour une installation existante, arrêtez Mailaya et sauvegardez le dossier des données avec sa base SQLite et sa clé locale. Récupérez cette version, synchronisez les dépendances avec les extras déjà utilisés, puis redémarrez une seule instance avec un seul worker. La migration est additive et conserve les résultats existants. Les traitements coûteux restent désactivés par défaut et s’activent séparément pour chaque boîte.

Le LLM peut fonctionner sur une autre machine du réseau pour alléger un Raspberry Pi. L’option OpenAI utilise une clé API ; elle ne fournit pas de connexion OAuth ChatGPT.

### Validation et limites

- 84 tests automatisés réussis, dont l’isolation des utilisateurs, les migrations, les fournisseurs et les documents servis derrière un reverse proxy.
- Vérifications JavaScript et parcours navigateur : analyse, suivi, réglages, recherche, brief et annulation de suppression.
- Catalogue, brief et recherche vérifiés avec un serveur oMLX réel et Qwen3-8B-4bit, sur des messages fictifs.
- Mise en page contrôlée jusqu’à une largeur simulée de 390 px.

Les classeurs LAYA / Julia et IMAP sont simulés dans ces tests. Aucun benchmark de cette version sur Raspberry Pi, aucune vraie boîte IMAP ni cycle automatique de 24 heures ne sont revendiqués. Les limites et preuves sont détaillées dans [docs/VALIDATION.md](docs/VALIDATION.md).
