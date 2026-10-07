# Validation locale du 7 octobre 2026

## Tests automatisés

Commande dans l’environnement existant : `.venv/bin/python -m pytest`.

Résultat après refonte : **84 tests réussis**, deux avertissements de dépréciation Starlette/AnyIO, en 10,02 s. La suite inclut isolation des utilisateurs, secrets chiffrés, conservation des résultats, suivi/report, règles, filtres, vues, exports, incrémentalité, conversations, comparaison sur le même lot, activation par compte, planification et reprise après erreur, validation des sorties génératives et contrats des fournisseurs. Deux cas supplémentaires vérifient le document HTML composé : identifiants uniques, références accessibles valides, chargement des feuilles de style et scripts, avec et sans préfixe de reverse proxy.

`node --check app/static/app.js`, `node --check app/static/workspace.js`, `node --check app/static/ui.js` et `git diff --check` réussis. Le guide HTML a été régénéré depuis `USER_GUIDE.md`.

Les tests de classement et IMAP utilisent des moteurs ou serveurs simulés. Ils ne mesurent pas les vrais poids LAYA/Julia sur Raspberry Pi.

## Inférence réelle oMLX

Serveur actif : `http://127.0.0.1:11435/v1`, modèle **Qwen3-8B-4bit**. Catalogue réel : 10 modèles de conversation après exclusion des identifiants courants d’embeddings/TTS.

Le script `scripts/smoke_omlx.py` a traversé les endpoints de l’application dans une base temporaire avec trois mails fictifs et des prédictions de classement préenregistrées :

- Brief : deux résumés reliés à des identifiants de messages valides, en 0,93 s.
- Recherche « Les demandes de devis encore à faire » : un devis retrouvé, filtres `q=devis`, `task=todo`, périmètre démonstration personnelle, en 0,86 s.

La [preuve JSON](validation/omlx-proof.json) correspond à ce test réussi. Ces durées décrivent uniquement cet essai, pas un benchmark.

Une répétition du script, avant la refonte, n’a pas été exécutée : le contrôle automatique d’approbation n’a pas pu fonctionner à cause du quota. La preuve précédente est conservée. Le script a ensuite été ajusté pour choisir un chemin temporaire portable et configurer la base temporaire avant l’import de l’application ; ces ajustements du script n’ont pas fait l’objet d’une nouvelle inférence réelle. Les appels réels depuis la nouvelle interface ont ensuite réussi, comme décrit ci-dessous.

Les protocoles Ollama et OpenAI ont été vérifiés avec des transports HTTP simulés. Aucun test réel de ces deux services ni de connexion OAuth n’est revendiqué.

## Interface et guide

Validation via navigateur sur une instance temporaire, compte et messages fictifs, classeurs simulés explicitement nommés `synthetic-ui-preview` :

- Analyse, recherche classique, correction de catégorie, statut Traité et vue favorite.
- Découverte réelle des modèles oMLX, sélection et sauvegarde de la connexion.
- Activation distincte des options et réponse générative réelle du brief et de la recherche.
- Comparaison de 12 messages sur le même lot et persistance après rechargement.
- Lecture du brief conservé et affichage étroit avec les libellés de suivi.
- Guide embarqué accessible, 16 sections, sommaire et lien d’installation uv fonctionnels.

Aucun débordement horizontal du document à la largeur normale et à la largeur étroite mesurée de 520 px. Aucun avertissement ou erreur dans la console lors du contrôle final. L’autorisation de notification navigateur n’a pas été accordée pendant ces tests.

Captures : [tableau de bord](validation/dashboard.jpg), [guide d’installation](validation/guide.jpg), [affichage étroit](validation/narrow.jpg).

## Refonte UI et UX

L’interface a été restructurée en quatre espaces : Messages, Brief quotidien, Analyses et Paramètres. Les contrôles détaillés sont présentés à la demande. La navigation conserve les formulaires au lieu de les reconstruire. Les polices sont locales au système ; aucune bibliothèque frontend ou police externe n’a été ajoutée.

Contrôles via navigateur sur le serveur de prévisualisation isolé, avec les mêmes mails fictifs et les classeurs `synthetic-ui-preview` :

- Navigation entre les quatre pages, sous-sections des paramètres et rechargement d’un lien direct vers les fonctions par boîte.
- Analyse de 12 messages depuis le nouvel écran : progression, fin de traitement et accès aux résultats.
- Volet de lecture, catégorie/priorité visibles, enregistrement d’un statut Traité puis retour à À faire.
- Saisie de report conservée lors d’une navigation et d’une actualisation ; fermeture bloquée avant annulation ou enregistrement.
- Horaire du brief affiché après activation, saisie conservée entre les pages, puis Annuler rétablit les réglages sauvegardés.
- Connexion IA modifiable, catalogue réel oMLX récupéré, Qwen3-8B-4bit sélectionné et sauvegardé ; confirmation de sauvegarde visible hors du formulaire replié.
- Recherche générative réelle « Tous les devis, y compris les messages traités » : `q=devis`, suivi `all`, un message retrouvé. Le formulaire se replie ; l’interprétation, le résumé des filtres et les résultats restent visibles.
- Brief réellement régénéré avec Qwen3-8B-4bit : deux résumés reliés aux sources. Un lien ouvre le message dans le volet de lecture.
- Confirmation de suppression affichée puis annulée : les 12 messages restent présents. Aucune suppression exécutée dans ce parcours.

À la largeur normale de 1 223 px et à 520 px, le document n’a aucun débordement horizontal. Le volet remplace la liste à 520 px. Une simulation mobile à 390 px confirme la mise en page et l’absence de débordement du document ; la barre des sous-sections défile dans son propre conteneur. Cette simulation est une vérification de mise en page, pas un essai sur un téléphone physique. Les tailles temporaires du navigateur ont été réinitialisées après le contrôle.

Aucune erreur ni aucun avertissement de console pendant le contrôle final. Les notifications système restent non autorisées pour les tests. La suppression définitive et les données des autres comptes n’ont pas été utilisées pour ces essais.

Captures après refonte : [messages](validation/redesign-messages.jpg), [lecteur](validation/redesign-reader.jpg), [brief](validation/redesign-brief.jpg), [paramètres](validation/redesign-settings.jpg), [mobile](validation/redesign-mobile.jpg), [paramètres sur mobile](validation/redesign-settings-mobile.jpg).

## Limites de preuve

Pas de déploiement sur Raspberry Pi, de mesure de mémoire/performance des vrais classeurs, de test d’une vraie boîte IMAP ou de cycle quotidien de 24 heures. Le service systemd du guide est un exemple à adapter, pas un service installé par ces travaux. Ces contrôles locaux précèdent la préparation de la release v0.4.0.
