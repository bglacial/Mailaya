# Évolutions du tri quotidien

## Périmètre

Vue À traiter et suivi personnel, recherche/filtres/vues favorites, corrections conservant les prédictions, synchronisation IMAP incrémentale et périodique, règles personnelles, historique et exports, comparaison LAYA/Julia, conversations, brief quotidien et recherche naturelle avec connexion oMLX/Ollama/OpenAI.

## Choix

- SQLite et interface JavaScript existantes ; pas de service supplémentaire obligatoire.
- Réglages coûteux désactivés par défaut, par compte IMAP ; générations bornées et sérialisées avec l'inférence locale.
- Recherche naturelle traduite en filtres structurés validés, jamais en SQL fourni par le modèle. Recherche classique indépendante du LLM.
- Brief déterministe disponible sans modèle génératif ; enrichissement LLM explicite et lié à des sources vérifiées.
- Corrections personnelles persistantes, sans réentraînement implicite. Règle suivante en cas de conflit : correction manuelle, première règle correspondante, modèle.
- IMAP en lecture seule ; aucun envoi, archivage ou effacement côté messagerie.
- Notifications opt-in, quand la page est ouverte ; pas de service push externe.
- OpenAI est une option externe explicite ; oMLX/Ollama permettent le fonctionnement local demandé. Aucun identifiant OAuth emprunté à un autre produit.

## Validation attendue

Isolation entre utilisateurs, migration additive, absence de doublons sur synchronisation, persistance des corrections/vues, comparaison sur un même lot, export sûr pour tableur, validation des sorties LLM, désactivation par compte, fonctionnement de l'interface, découverte et inférence réelle oMLX avec messages fictifs. La préparation de la publication v0.4.0 est décrite dans le changelog.

## Questions tranchées sans sollicitation

| Question | Décision et raison |
| --- | --- |
| Faut-il un LLM pour chaque brief ? | Non : un brief par règles fonctionne localement ; l’enrichissement LLM est facultatif pour éviter une dépendance et une consommation inutiles. |
| Quel fournisseur utiliser immédiatement ? | oMLX et Ollama avec leurs catalogues réels ; OpenAI ou API compatible par clé chiffrée en option. Aucun OAuth ChatGPT fictif ni réutilisation d’identifiants d’un autre produit. |
| Comment limiter la charge du Pi ? | Synchronisation automatique, enrichissement, recherche naturelle et comparaison désactivés par défaut, par compte ; lots bornés, calculs séquentiels. Le LLM peut tourner sur un ordinateur du réseau. |
| Que signifie « sans réponse » ? | Le statut personnel À faire. Les dossiers importés ne permettent pas de prouver qu’aucune réponse n’a été envoyée. |
| Recherche sémantique ou interprétation de filtres ? | Interprétation en filtres visibles et validés ; pas de calcul d’embeddings ni d’index vectoriel supplémentaire. |
| Les corrections modifient-elles le modèle ? | Non : elles sont conservées à part et prioritaires à l’affichage ; les prédictions restent consultables. |
| Faut-il modifier les mails distants ? | Non : lecture IMAP uniquement et suivi propre à Mailaya. |
| Quelle heure pour le brief ? | 8 h, Europe/Paris, modifiable pour chaque compte ; serveur actif nécessaire. |
| Faut-il du push externe ? | Non : notifications facultatives avec permission demandée par un bouton, quand la page est ouverte. |

Les résultats et limites des contrôles sont détaillés dans [VALIDATION.md](VALIDATION.md).
