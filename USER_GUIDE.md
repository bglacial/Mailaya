# Mailaya : guide utilisateur et installation

## 1. À quoi sert Mailaya ?

Mailaya aide à repérer les demandes importantes dans une ou plusieurs boîtes mail, à retrouver un échange et à suivre ce qui reste à faire. L’application importe des aperçus en lecture seule, les classe avec LAYA ou Julia, puis vous laisse corriger et organiser les résultats.

Elle ne remplace pas votre messagerie : elle n’envoie pas de réponses, ne déplace pas les mails, ne les supprime pas et ne les marque pas comme lus. « Traité » est votre statut personnel dans Mailaya. Il ne prouve pas qu’une réponse a été envoyée.

Deux niveaux d’IA sont distincts :

- Le **modèle de classement**, LAYA ou Julia, fonctionne sur la machine qui héberge Mailaya. Il produit catégorie, priorité, spam et action attendue.
- Le **LLM facultatif**, configuré séparément, enrichit le brief et traduit une recherche naturelle en filtres. Il peut tourner sur oMLX ou Ollama, sur la même machine ou un ordinateur du réseau. Un fournisseur externe nécessite une autorisation explicite.

Vous pouvez utiliser la recherche classique, les règles, le suivi, les corrections, les conversations et les exports sans LLM. Le brief peut également fonctionner par règles locales.

## 2. Choisir une installation

### Mac ou Linux : installation complète

Prérequis : Python 3.11 ou plus récent, [uv](https://docs.astral.sh/uv/getting-started/installation/), accès Internet pour installer les dépendances et télécharger les modèles au premier usage. Installez uv selon sa documentation officielle, puis vérifiez `uv --version` et `python3 --version` dans un terminal. Sur macOS et Linux, les deux classeurs utilisent PyTorch. La disponibilité des dépendances dépend aussi de l’architecture de votre machine.

Récupérez le dossier du projet sur la machine qui hébergera Mailaya, puis ouvrez un terminal dans `laya-mail`, le dossier contenant `pyproject.toml`. Par exemple : `cd /chemin/vers/mailaya/laya-mail`. Les commandes ci-dessous s’exécutent dans ce dossier. Si un fichier `.env` existe déjà, conservez-le au lieu de l’écraser avec la commande `cp`.

Depuis le dossier du projet contenant `pyproject.toml` :

```bash
cp .env.example .env
uv sync --extra laya --extra julia --extra dev
uv run --extra laya --extra julia uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ouvrez http://127.0.0.1:8000 dans votre navigateur. Le guide est accessible en bas de la navigation ou dans le menu de compte, même sans connexion. Pour arrêter le serveur lancé dans le terminal : Ctrl+C.

Vous pouvez installer un seul modèle :

```bash
uv sync --extra julia
uv run --extra julia uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Choisissez alors Julia dans l’interface. LAYA et la comparaison avec LAYA nécessitent l’extra `laya`. Le moteur signale un runtime absent au lieu de fabriquer des résultats.

### Raspberry Pi : commencer progressivement

Utilisez un système Linux 64 bits et Python 3.11+. Commencez par l’application et les outils de test :

```bash
cp .env.example .env
uv sync --extra dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

L’interface, les comptes, les règles, la recherche et le brief déterministe n’exigent pas PyTorch. Pour classer de nouveaux mails, installez ensuite un runtime compatible avec votre Pi, par exemple `uv sync --extra julia`, puis redémarrez avec l’extra correspondant. La vitesse et la mémoire des vrais classeurs sur Raspberry Pi n’ont pas été mesurées : commencez avec 12 messages et vérifiez les métriques avant d’augmenter le volume.

Conseils de réglage :

- Laissez la synchronisation automatique et la comparaison désactivées au départ.
- Si vous activez la synchronisation, commencez avec 12 mails toutes les 30 à 60 minutes.
- Utilisez le brief sans enrichissement LLM sur le Pi.
- Pour les fonctions génératives, associez un serveur oMLX sur un Mac ou Ollama sur une autre machine du réseau.
- La comparaison charge le second classeur sur le serveur Mailaya. Elle ne se fait pas sur oMLX.

oMLX repose sur Apple Silicon : dans ce scénario, le Pi est client du serveur oMLX sur le Mac.

### Accès depuis une autre machine

`127.0.0.1` limite l’accès à la machine du serveur. Pour un usage sur votre réseau, vous pouvez écouter sur `0.0.0.0`, puis ouvrir l’adresse IP du serveur depuis votre navigateur. Avant d’exposer l’application au-delà d’un réseau de confiance, configurez un reverse proxy HTTPS. Les inscriptions sont ouvertes et cette version ne fournit pas de console administrateur ni de récupération de mot de passe.

Une seule instance et un seul worker Uvicorn sont pris en charge : la file des traitements, les verrous et le planificateur sont locaux au processus. Ne lancez pas plusieurs instances sur la même base.

### Garder Mailaya actif sur Linux

La synchronisation et le brief automatique ont besoin d’un serveur actif. Après avoir installé et testé les dépendances, vous pouvez créer un service systemd utilisateur. Créez le dossier avec `mkdir -p ~/.config/systemd/user`, puis le fichier `~/.config/systemd/user/mailaya.service` avec le contenu suivant, en remplaçant **les deux chemins** par le chemin absolu de votre dossier `laya-mail` :

```ini
[Unit]
Description=Mailaya - tri et suivi des mails

[Service]
WorkingDirectory=/CHEMIN/ABSOLU/laya-mail
ExecStart=/CHEMIN/ABSOLU/laya-mail/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Activez le service avec `systemctl --user daemon-reload`, puis `systemctl --user enable --now mailaya`. Consultez son état avec `systemctl --user status mailaya` et ses journaux avec `journalctl --user -u mailaya`. Pour conserver le service après déconnexion et le démarrer au démarrage de Linux, un administrateur peut activer la persistance de votre utilisateur avec `sudo loginctl enable-linger VOTRE_UTILISATEUR`.

Arrêtez l’instance de terminal avant de lancer le service. Après une mise à jour : `systemctl --user restart mailaya`. Pour l’arrêter : `systemctl --user stop mailaya`. Adaptez l’adresse d’écoute uniquement si vous souhaitez un accès réseau, selon les indications précédentes. Cette configuration est un exemple d’installation ; elle n’est pas installée automatiquement par Mailaya.

## 3. Paramètres de lancement

Le fichier `.env` contient les paramètres du serveur, les fonctions quotidiennes se règlent dans l’interface.

- `LAYA_BACKEND=auto` : Julia par défaut pour les commandes sans modèle explicite ; `laya` choisit LAYA. `demo` est réservé aux tests déterministes, pas à une analyse réelle de vos mails.
- `JULIA_CPU_THREADS=4` : nombre de threads CPU Julia. Réduisez-le si la machine doit rester disponible pour d’autres services.
- `LAYA_DEVICE=cpu`, `JULIA_DEVICE=cpu` : traitement sur CPU.
- `MAX_EMAILS_PER_RUN=500` : plafond des lots manuels et automatiques.
- `MAILAYA_SECURE_COOKIES=true` : cookies sécurisés derrière un reverse proxy HTTPS.
- `LAYA_MAIL_DATA_DIR` : dossier des données, `data/` par défaut. Placez-le sur un disque local protégé.

Les arguments `--host` et `--port` de la commande Uvicorn déterminent l’adresse d’écoute. Modifier uniquement `HOST` ou `PORT` dans `.env` ne modifie pas cette commande. Après modification de `.env`, redémarrez Mailaya.

## 4. Découvrir l’application et créer son espace

L’application comporte quatre espaces accessibles depuis la navigation :

- **Messages** : rechercher, consulter un aperçu, corriger le classement et suivre les demandes.
- **Brief quotidien** : lire une synthèse pour la boîte choisie, ouvrir ses messages sources et retrouver un brief conservé.
- **Analyses** : importer et classer un lot, suivre sa progression, consulter les métriques et comparer les modèles.
- **Paramètres** : ajouter des boîtes mail, activer les fonctions par boîte, configurer les connexions IA, les règles et votre compte.

La navigation est latérale sur ordinateur et horizontale sur écran étroit. Le menu de compte en haut donne accès à la connexion, au guide et à la déconnexion.

Sans connexion, la démonstration propose 500 messages fictifs. Ses résultats sont partagés entre visiteurs publics. Le modèle sélectionné analyse réellement ces messages, ce qui peut demander un téléchargement et un chargement au premier lancement.

Pour un espace personnel : ouvrez **Paramètres → Mon compte → Se connecter ou créer un compte**, saisissez un identifiant de 3 à 80 caractères et un mot de passe d’au moins 12 caractères, puis choisissez **Créer mon compte**. Vos comptes IMAP, résultats, règles, vues, connexions LLM et briefs sont isolés des autres utilisateurs.

La démonstration lancée après connexion appartient à votre espace. Dans **Paramètres → Fonctions par boîte**, **Démonstration personnelle** permet de tester le brief et la recherche naturelle sans importer vos vrais mails.

## 5. Ajouter et analyser une boîte IMAP

1. Ouvrez **Paramètres → Boîtes mail**, puis **Ajouter une boîte mail**.
2. Renseignez un nom, le serveur, l’identifiant et le mot de passe d’application fourni par votre messagerie si nécessaire.
3. Choisissez **TLS direct**, généralement port 993, ou **STARTTLS**, généralement port 143.
4. Le dossier `INBOX` désigne habituellement la boîte de réception. Saisissez un autre dossier si besoin.
5. Enregistrez puis cliquez sur **Tester**.
6. Dans **Analyses**, choisissez IMAP, le compte, la date, le nombre de mails et le modèle de classement.
7. Lancez l’analyse. La progression et les erreurs apparaissent dans le panneau de droite.

La recherche IMAP utilise la date de réception du serveur. Seul un aperçu textuel de 2 000 caractères est conservé et analysé ; les pièces jointes ne sont pas traitées. Une information à la fin d’un long message peut donc être absente du classement, du brief et de la recherche.

**Analyser seulement les nouveaux messages pour ce modèle** est coché par défaut. Mailaya ignore les messages déjà classés avec succès avec ce même modèle et ce même compte/dossier. Les échecs peuvent être retentés. Les identités incluent `UIDVALIDITY` et l’UID du serveur IMAP. Une remise à zéro côté serveur peut entraîner une nouvelle importation. Changer de modèle permet de produire sa propre analyse, sans réutiliser les prédictions de l’autre.

Décochez cette option pour forcer une nouvelle analyse. Les résultats précédents restent dans l’historique et les corrections personnelles sont conservées pour la même identité de mail. Une comparaison utilise une copie du lot déjà importé, sans nouvelle connexion IMAP.

## 6. Comprendre les scores

- **Catégorie** : classe proposée par le modèle. Cliquez sur l’objet d’un message pour ouvrir le volet de lecture, puis dépliez **Comprendre le classement** pour voir la prédiction initiale et les scores des catégories.
- **Priorité** : score de 0 à 100, affiché comme Basse, Normale, Haute à partir de 58, Critique à partir de 82.
- **Spam** : indication de risque, pas un diagnostic de sécurité.
- **Action** : indication qu’une intervention est attendue, pas une preuve que vous devez répondre.
- **Temps** : durée d’inférence du message ; le premier traitement peut inclure le chargement du modèle.

Les scores sont des aides au tri. La vue **À vérifier** signale les catégories dont le score maximal est inférieur à 0,6 ou dont les deux meilleurs scores sont séparés de moins de 0,15. Ces seuils sont heuristiques, ils ne constituent pas une mesure de confiance calibrée. Un message corrigé ou classé par une règle n’est plus présenté comme ambigu selon cette heuristique.

## 7. Rechercher et organiser

### Recherche classique et vues

Dans **Rechercher dans les messages importés**, saisissez une expression présente dans l’expéditeur, l’objet ou l’aperçu. La recherche est insensible aux majuscules. Elle porte sur les données importées dans votre espace, pas sur l’ensemble de votre boîte distante.

Dépliez **Filtres** pour combiner expéditeur, catégorie exacte, dates, seuils de priorité/action/spam et suivi personnel, puis choisissez **Appliquer les filtres**. Les filtres se cumulent. Leur résumé apparaît au-dessus de la liste ; **Réinitialiser** revient à la vue complète. Les dates de filtrage des résultats correspondent aux dates UTC stockées ; l’affichage des heures utilise votre navigateur.

- **Tous** affiche le dernier résultat importé de chaque identité de mail.
- **À traiter** retient les messages classés avec priorité au moins 58, action au moins 50 et statut personnel À faire.
- **À vérifier** retient les classements ambigus selon les seuils ci-dessus.

Les résultats sont affichés par pages de 50. Ouvrez **Vue et export**, saisissez un nom puis **Enregistrer la vue** pour conserver une combinaison de filtres. Retrouvez-la dans **Vues favorites**. La vue conserve aussi un éventuel choix d’analyse historique.

### Corriger, traiter et reporter

Cliquez sur l’objet d’un message. Le volet affiche l’aperçu et **Mon suivi** : choisissez **À faire**, **Traité** ou **Reporté**, puis **Enregistrer**. Un report dévoile le champ de date et nécessite une date future ; le message revient à À faire quand cette date est passée, lors de la prochaine consultation. Pour modifier catégorie ou priorité, dépliez **Corriger le classement**.

Une saisie non enregistrée reste conservée lorsque vous passez à une autre page ou que les résultats s’actualisent. Enregistrez ou cliquez sur **Annuler** avant de changer de message ou de fermer le volet. Sur écran étroit, le volet prend la place de la liste ; **Fermer** revient aux messages.

Laisser catégorie/priorité vides conserve la décision des règles ou du modèle. **Retirer mes corrections** vide ces champs ; cliquez ensuite sur **Enregistrer** pour appliquer le changement. La prédiction initiale n’est jamais remplacée. Les corrections ne déclenchent pas de réentraînement.

### Règles personnelles

Dans **Paramètres → Règles de tri**, sélectionnez la boîte concernée puis **Ajouter une règle**. Indiquez un texte à retrouver dans l’adresse expéditeur, l’objet ou l’objet et l’aperçu, puis la catégorie et/ou la priorité à appliquer.

La première règle correspondante, dans l’ordre de création, gagne. Une correction manuelle prend ensuite le dessus sur les champs que vous avez corrigés. Une règle s’applique immédiatement à la présentation des résultats, sans relancer l’IA. Supprimer une règle rétablit la décision du modèle ou une autre règle correspondante.

### Conversations

Cochez **Regrouper les conversations** dans les filtres. Les mails sont regroupés à l’intérieur d’un même compte à partir de leurs en-têtes de réponse et de référence. Si ces informations sont absentes, Mailaya utilise l’objet normalisé et l’expéditeur : ce regroupement est une approximation. Le nombre affiché porte sur les messages correspondant aux filtres.

Ouvrez la ligne puis **Ouvrir cette conversation** pour voir les messages filtrés de cet échange. **Rechercher** quitte la conversation et revient à la liste.

## 8. Fonctions par boîte et synchronisation

Dans **Paramètres → Fonctions par boîte**, sélectionnez la boîte avant d’activer une fonction, puis cliquez sur **Enregistrer les fonctions**. Les réglages d’une boîte ne sont pas copiés aux autres. Les options détaillées apparaissent à l’activation : fréquence de synchronisation, horaire du brief, connexion IA ou autorisation de notification. **Annuler** retrouve les derniers réglages enregistrés. Un changement de boîte est bloqué tant que vos modifications restent non enregistrées.

La synchronisation automatique est désactivée par défaut. Vous choisissez un intervalle de 5 à 1 440 minutes, un maximum de 1 à 500 messages par passage et le modèle local. Le plafond global `MAX_EMAILS_PER_RUN` reste applicable. Les passages automatiques recherchent les messages des 30 derniers jours ; pour importer des messages plus anciens, lancez une analyse manuelle avec une autre date.

Le planificateur vérifie les fonctions toutes les 30 secondes, uniquement lorsque le serveur tourne. Une analyse active ou en pause sur ce compte retarde le passage. Une erreur est affichée dans les réglages du compte ; le passage suivant respecte l’intervalle configuré. Aucun passage n’est rattrapé serveur éteint.

Les classements LAYA/Julia, les briefs enrichis et les recherches naturelles partagent une limite d’un calcul à la fois sur Mailaya. Cela limite la concurrence mais ne garantit pas qu’un modèle volumineux tient dans la RAM du Pi. Une génération LLM en attente peut prendre du temps.

## 9. Connecter oMLX, Ollama ou une API

Ouvrez **Paramètres → Connexions IA → Ajouter une connexion**, choisissez le fournisseur et cliquez sur **Récupérer les modèles disponibles**. Choisissez un modèle de conversation dans le catalogue, puis **Enregistrer la connexion**. Dans **Fonctions par boîte**, associez cette connexion à la boîte voulue, après avoir activé la recherche naturelle ou l’enrichissement du brief.

Adresses usuelles :

- oMLX sur le même Mac que Mailaya : `http://127.0.0.1:11435/v1`.
- Ollama sur la même machine : `http://127.0.0.1:11434`, sans suffixe `/v1` pour le protocole natif.
- Serveur oMLX sur un Mac du réseau : par exemple `http://192.168.1.20:11435/v1`, à remplacer par son adresse réelle. Le serveur oMLX doit accepter les connexions du réseau ; un service limité à 127.0.0.1 ne sera pas accessible depuis le Pi.
- OpenAI : `https://api.openai.com/v1`, clé API et autorisation explicite de traitement distant. Cette option utilise la clé API, pas l’abonnement ChatGPT.

**L’adresse est vue depuis le serveur Mailaya.** Si vous ouvrez l’interface du Pi depuis un Mac, `127.0.0.1` désigne le Pi, pas le Mac. Le navigateur n’appelle jamais directement le serveur LLM et ne reçoit pas la clé enregistrée.

Les clés sont chiffrées avec la clé locale du serveur. Pour modifier une connexion, vous pouvez laisser la clé vide pour la conserver si l’adresse et le protocole restent identiques. Après changement de destination, ressaisissez la clé nécessaire. Supprimer une connexion désactive son utilisation : les comptes qui la sélectionnaient doivent être reconfigurés.

Les serveurs publics nécessitent **J’autorise ce fournisseur externe...** et HTTPS. Les adresses locales ou privées sont accessibles sans cette autorisation de fournisseur externe ; cela ne signifie pas que le serveur privé choisi ne transmet jamais ses propres données ailleurs. Choisissez un service que vous maîtrisez.

La découverte exclut les identifiants courants de modèles d’embeddings et de synthèse vocale. Un modèle restant dans la liste peut encore être incompatible avec la génération de JSON : essayez un autre modèle si nécessaire.

## 10. Brief quotidien

Dans **Paramètres → Fonctions par boîte**, cochez **Activer le brief** et enregistrez. Sans **Enrichir les résumés avec un LLM**, le brief est entièrement déterministe et local : nouveaux messages du jour, demandes encore à faire, aperçu des demandes et extraits mentionnant une échéance.

Le brief utilise vos derniers résultats classés et vos statuts personnels. Il retient jusqu’à 20 demandes À faire avec action au moins 50 et spam inférieur à 70, triées par priorité. Les anciennes demandes non traitées peuvent rester présentes. S’il manque un mail, vérifiez l’importation, les scores et le statut.

Pour un résumé génératif, choisissez une connexion puis activez l’enrichissement LLM. Seuls les objets et jusqu’à 500 caractères d’aperçu des 12 premières demandes sélectionnées sont transmis. Les secrets IMAP ne sont jamais transmis. Les résumés affichent les messages sources, dont les identifiants sont vérifiés avant conservation. Cela ne garantit pas l’exactitude du résumé : relisez les sources avant d’agir.

Ouvrez **Brief quotidien**, sélectionnez la **Boîte concernée**, puis cliquez sur **Préparer le brief** pour le produire ou le rafraîchir. Ce sélecteur est indépendant du filtre des messages et de la boîte ouverte dans les paramètres. Si le brief est désactivé, **Configurer ce brief** ouvre les réglages de cette boîte.

**Préparer automatiquement chaque jour**, dans les réglages, utilise l’heure et le fuseau configurés, par défaut 8 h, Europe/Paris. Il prépare au plus un brief réussi par jour ; en cas d’erreur, une nouvelle tentative attend au moins 30 minutes. Le serveur doit rester actif.

Les briefs sont conservés par jour et par compte ; le sélecteur affiche les 30 derniers jours conservés. Une nouvelle préparation du même jour remplace le brief de ce jour. Les liens ouvrent l’aperçu importé, pas votre messagerie distante.

## 11. Recherche en langage naturel

Associez une connexion LLM et activez **Recherche en langage naturel** dans **Paramètres → Fonctions par boîte**, puis enregistrez. Dans **Messages**, ouvrez **Recherche en langage naturel**, sélectionnez la **Boîte concernée**, décrivez votre demande et cliquez sur **Trouver les messages**. Ce choix est indépendant du filtre de la liste et de la boîte ouverte dans les paramètres. Si la fonction est désactivée ou sans connexion, un lien vous conduit aux réglages de cette boîte.

Exemples : « Les demandes de devis encore à faire cette semaine », « Les messages prioritaires de Camille », « Les newsletters reçues depuis lundi ».

Le modèle reçoit votre demande, la date, le fuseau et les noms des catégories disponibles, sans les objets ni les aperçus de vos mails. Il la traduit en filtres autorisés, ensuite appliqués aux messages de votre compte. Une catégorie inconnue peut être interprétée comme un texte à rechercher plutôt que comme une catégorie inexistante. Après la recherche, le formulaire se replie pour laisser place aux résultats. L’interprétation et le résumé des filtres restent visibles ; dépliez **Filtres** pour les corriger ou rouvrez **Recherche en langage naturel** pour changer votre demande. Il ne génère pas de SQL et ne peut pas changer de propriétaire ou de compte.

Cette recherche interprète des intentions de filtrage ; ce n’est pas une recherche sémantique par embeddings. Elle ne peut pas retrouver un concept absent de l’aperçu ni vérifier vos réponses dans un dossier Envoyés non importé. « Sans réponse » est interprété comme le statut personnel À faire.

## 12. Historique, comparaison et exports

Dans **Analyses**, **Historique et comparaison** affiche les 200 analyses les plus récentes. Choisissez un lot puis **Afficher les messages** pour ouvrir sa liste. Consulter une analyse ne relance pas le traitement. La liste principale montre autrement le dernier résultat importé par identité de mail.

Pour comparer : activez **Comparaison LAYA / Julia** sur la boîte concernée, sélectionnez une analyse terminée dans l’historique et cliquez sur **Comparer avec l’autre modèle**. Le deuxième modèle reçoit exactement les mêmes aperçus importés. Les traitements restent séquentiels, sans charger simultanément les deux classeurs.

Les résultats montrent les catégories, les désaccords et les durées par mail. Si vous avez corrigé des catégories, la comparaison calcule le taux de correspondance aux corrections sur cet échantillon. Sans corrections, elle ne prétend pas mesurer la qualité. Les durées peuvent inclure un premier chargement : ce n’est pas un benchmark de performance contrôlé.

Dans **Messages → Vue et export**, **Exporter CSV** et **Exporter JSON** exportent tous les messages correspondant aux filtres, au-delà de la page affichée. Le CSV comprend la catégorie/priorité appliquées et celles initialement prédites. Les textes susceptibles d’être interprétés comme formules sont neutralisés. Le JSON conserve davantage de détails, dont les scores, aperçus et corrections. Les exports contiennent des données personnelles : choisissez leur destination en conséquence.

## 13. Notifications navigateur

Dans **Paramètres → Fonctions par boîte**, cochez **Être prévenu lorsque c’est prêt**, cliquez sur **Autoriser les notifications navigateur**, puis enregistrez. Le navigateur conserve le choix d’autorisation. HTTPS ou localhost est nécessaire.

Les notifications signalent une fin d’analyse, un échec ou la disponibilité d’un brief et ne contiennent pas le texte des mails. Elles fonctionnent lorsque la page est ouverte et détecte un changement ; les restrictions du navigateur peuvent empêcher leur affichage. Il n’existe pas de service push qui réveille un navigateur fermé. Désactivez la case du compte ou révoquez l’autorisation du site pour les arrêter.

## 14. Sauvegarde, confidentialité et mise à jour

Sauvegardez ensemble le dossier des données, la base `laya-mail.sqlite3` et la clé `imap.key`. Arrêtez le service avant une copie de fichiers pour inclure de manière cohérente la base et ses journaux SQLite. Conservez la sauvegarde dans un emplacement protégé.

La clé chiffre les mots de passe IMAP et les clés API. Les mots de passe de connexion sont hachés. Les aperçus, règles, corrections et briefs restent dans SQLite sans chiffrement applicatif du contenu. Perdre la clé oblige à ressaisir les secrets, sans effacer les résultats.

La migration vers ces fonctions est additive et conserve les résultats existants. Après une mise à jour du code, synchronisez les dépendances puis redémarrez. Ne revenez pas simplement à une ancienne version du code sur une base modifiée sans sauvegarde préalable.

Dans **Analyses → Gestion des résultats**, **Effacer mes résultats** demande une confirmation dans la page avant de supprimer toutes vos analyses et leurs messages importés. Vos mails distants restent dans votre messagerie. Les réglages, règles, vues, corrections et briefs sont conservés ; les liens d’un ancien brief peuvent devenir indisponibles. Une nouvelle importation de la même identité de message peut réappliquer vos corrections. Les corrections et briefs ne disposent pas encore d’un bouton de purge global.

## 15. Résoudre les problèmes courants

- **Runtime absent** : installez l’extra du modèle sélectionné et redémarrez avec cet extra. Ne choisissez pas LAYA si seul Julia est installé.
- **Chargement long** : le premier usage télécharge les poids, les analyses suivantes rechargent le modèle en mémoire. Réduisez le lot et consultez les métriques.
- **Aucun nouveau message** : vérifiez la date et le dossier ; une synchronisation incrémentale peut légitimement ne rien trouver. Décochez l’option pour une nouvelle analyse complète.
- **Erreur IMAP** : vérifiez le serveur, TLS, le port, le nom de dossier et le mot de passe d’application. Le certificat n’est jamais ignoré.
- **Serveur LLM inaccessible** : vérifiez l’adresse depuis la machine Mailaya, le port d’écoute et le catalogue. Sur un Pi, n’utilisez pas localhost pour un serveur situé sur le Mac.
- **HTTP 401 ou 403 LLM** : vérifiez la clé API et les permissions du serveur.
- **HTTP 507 ou manque de mémoire** : choisissez un modèle plus petit sur le serveur LLM, désactivez l’enrichissement ou utilisez le brief déterministe.
- **JSON invalide ou génération tronquée** : changez de modèle ; aucun brief invalide n’est conservé. Les filtres de recherche sont validés avant utilisation.
- **Session expirée** : reconnectez-vous. Les sessions expirent après sept jours ; changer votre mot de passe ferme vos autres sessions.
- **Analyse en pause** : reprenez-la ou effacez les résultats pour débloquer les changements de paramètres IMAP. La synchronisation ne la remplace pas.
- **Notifications absentes** : vérifiez l’autorisation du site, le contexte HTTPS, la case du compte et que la page reste ouverte.

## 16. Vérification technique

Les tests automatisés utilisent des mails fictifs, des serveurs IMAP simulés et des classeurs simulés. Ils couvrent aussi de vrais processus isolés avec un moteur de test, sans prouver la performance des poids réels sur votre machine.

```bash
uv run --extra dev pytest
node --check app/static/app.js
node --check app/static/workspace.js
node --check app/static/ui.js
```

Pour vérifier le classement Julia avec les vrais poids sur trois messages fictifs, installez Julia puis exécutez `uv run --extra julia python -m app.smoke_julia`. Le script séparé `scripts/smoke_omlx.py` vérifie le catalogue, le brief et la recherche naturelle avec le serveur oMLX, dans une base temporaire et sans lire vos vrais mails.

Par exemple, après avoir vérifié la présence du modèle dans votre catalogue :

```bash
uv run --extra dev python scripts/smoke_omlx.py --url http://127.0.0.1:11435/v1 --model Qwen3-8B-4bit
```

Adaptez l’URL et le modèle à votre serveur. Le script n’installe pas ce modèle : il utilise celui disponible sur oMLX. Il affiche les résultats et écrit une preuve JSON dans le dossier temporaire du système ; `--output /chemin/preuve.json` permet de choisir sa destination.

La documentation interactive des endpoints est disponible sur `/api/docs`. La version HTML de ce guide est générée depuis ce fichier par `python scripts/build_guide.py` ; après modification du guide, régénérez-la pour garder l’aide embarquée à jour.
