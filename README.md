# Mailaya

Mailaya analyse localement des messages avec [LAYA multilingual](https://huggingface.co/convaiinnovations/laya-multilingual) ou [Julia-1](https://huggingface.co/SupersonicLabs/Julia-1). Le modèle se choisit pour chaque analyse dans l’interface, dans les deux modes :

- **Public** : uniquement les 500 messages fictifs de démonstration. Les résultats de cette démonstration sont communs aux visiteurs publics.
- **Connecté** : démonstration ou boîtes IMAP personnelles. Chaque utilisateur accède uniquement à ses comptes, ses analyses, ses messages et ses résultats.

Chaque message reçoit une catégorie et sa matrice de probabilités, ainsi que des scores de priorité, de spam et d’action attendue. L’interface affiche la progression, les erreurs, la pause/reprise et les statistiques de latence. Le choix du modèle est conservé à la reprise d’une analyse.

## Installation et lancement

Python 3.11+ et [uv](https://docs.astral.sh/uv/getting-started/installation/) sont nécessaires. Les deux runtimes utilisent PyTorch et fonctionnent sur Linux et macOS. Sur Linux, uv installe les roues CPU.

```bash
cp .env.example .env
uv sync --extra laya --extra julia --extra dev
uv run --extra laya --extra julia uvicorn app.main:app --reload
```

Ouvrez [http://127.0.0.1:8000](http://127.0.0.1:8000). La documentation de l’API est disponible sous `/api/docs`.

Le premier usage de chaque modèle télécharge ses poids depuis Hugging Face, sauf s’ils sont déjà en cache. Le modèle choisi se charge à la demande dans un processus d’inférence séparé. Ce processus est réutilisé pour les messages de l’analyse, puis arrêté à la fin, en pause ou en cas d’erreur : sa mémoire est rendue au système. Les poids restent en cache sur disque. Chaque nouvelle analyse ou reprise recharge le modèle ; ce chargement peut être lent sur une petite machine.

Les analyses sont sérialisées entre les utilisateurs : un seul processus d’inférence fonctionne à la fois. Il reçoit uniquement les champs textuels nécessaires au modèle, sans les identifiants de compte ni les secrets IMAP. Une pause interrompt le message en cours sans le marquer en échec ; il sera traité à la reprise. Si le processus s’arrête brutalement ou ne répond plus pendant 15 minutes pour un message (chargement compris), l’analyse s’arrête avec une erreur explicite et conserve les résultats déjà calculés. L’arrêt normal du service met les analyses actives en pause et termine l’inférence. Aucun contenu de mail n’est envoyé à un service d’IA distant.

Vous pouvez installer un seul runtime avec `--extra laya` ou `--extra julia`. Une analyse sélectionnant un runtime absent s’arrête avec une instruction d’installation. La source **Démonstration** utilise des mails fictifs et le vrai modèle sélectionné ; elle ne remplace pas son inference par des règles. `LAYA_BACKEND=demo` fournit un moteur déterministe aux tests et aux appels API sans sélection explicite de modèle.

## Utilisateurs et comptes IMAP

1. Dans **Se connecter ou créer un compte**, choisissez un identifiant de 3 à 80 caractères (lettres, chiffres, `@._+-`) et un mot de passe d’au moins 12 caractères.
2. Cliquez sur **Créer mon compte**. Chaque personne crée son propre espace.
3. Ouvrez **Mes comptes IMAP**, puis **Ajouter un compte IMAP**.
4. Renseignez le serveur, l’identifiant et le mot de passe ou mot de passe d’application fourni par votre messagerie. Choisissez **TLS direct**, généralement sur le port `993`, ou **STARTTLS**, généralement sur le port `143`.
5. Laissez `INBOX` pour la boîte de réception, ou renseignez un autre dossier. Les noms internationaux sont encodés en UTF-7 modifié.
6. Enregistrez, puis cliquez sur **Tester** pour vérifier les identifiants et l’accès au dossier.
7. Sélectionnez **IMAP**, le compte, le modèle, la date et le nombre de messages, puis lancez l’analyse.

La connexion vérifie le certificat TLS. Le dossier est ouvert en lecture seule ; les messages sont recherchés par UID et récupérés avec `BODY.PEEK[]`, sans les marquer comme lus. Les dates de recherche utilisent la date de réception du serveur IMAP. Les mails sont récupérés avec leur structure MIME, puis seul un aperçu textuel de 2 000 caractères est conservé pour l’analyse ; les pièces jointes ne sont pas analysées. Ces comportements utilisent le client [imaplib de Python](https://docs.python.org/3/library/imaplib.html).

Les comptes peuvent être testés, modifiés ou supprimés depuis l’interface. Laisser le mot de passe vide lors d’une modification conserve celui déjà enregistré. Un compte utilisé par une analyse active ou en pause ne peut être modifié ou supprimé avant la fin de l’analyse ou l’effacement de ses résultats. **Changer mon mot de passe** ferme les autres sessions de l’utilisateur. **Se déconnecter** remet l’interface en mode public.

## Stockage et mise à jour

La base SQLite se trouve par défaut dans `data/laya-mail.sqlite3` (modifiable avec `LAYA_MAIL_DATA_DIR`). Les mots de passe de connexion à Mailaya sont hachés avec scrypt. Les sessions utilisent des jetons aléatoires stockés sous forme de hash dans SQLite, expirent après sept jours et sont transmis par cookie HttpOnly/SameSite. Les requêtes de modification exigent le header `X-Mailaya-Request: 1` et refusent les origines externes.

Les mots de passe IMAP sont chiffrés avec Fernet. La clé locale `data/imap.key` et la base sont protégées par des permissions `0600`, dans un dossier `0700`. Sauvegardez la base et la clé ensemble dans un emplacement protégé. La perte de la clé oblige à ressaisir les mots de passe IMAP ; elle n’efface pas les résultats. Les aperçus des messages restent dans SQLite et ne sont pas chiffrés applicativement.

La migration ajoute les propriétaires sans attribuer les anciennes analyses privées à un nouvel utilisateur : les données historiques sans propriétaire restent conservées, mais masquées. Les anciens fichiers OAuth ne sont plus utilisés et peuvent être retirés manuellement du dossier de données.

Pour un accès HTTPS derrière un reverse proxy, activez `MAILAYA_SECURE_COOKIES=true` et configurez Uvicorn pour ne faire confiance qu’au proxy réellement utilisé. L’application fonctionne avec un seul processus Uvicorn : les verrous de traitement et les workers sont locaux à ce processus. Les inscriptions sont ouvertes ; il n’y a pas de console administrateur ni de récupération de mot de passe par e-mail.

## Tests

```bash
uv run --extra dev --extra laya --extra julia pytest
node --check app/static/app.js
```

La suite vérifie les sessions, le cloisonnement entre utilisateurs et mode public, le chiffrement, la migration des anciennes données, la gestion IMAP, la lecture sans modification des messages et le choix des modèles. Elle lance aussi de vrais processus séparés avec un moteur simulé pour vérifier leur arrêt, les crashs, la pause/reprise et l’arrêt du service. Les connexions IMAP et les modèles sont simulés dans ces tests pour ne pas dépendre d’une messagerie ou d’un téléchargement.

Une vérification avec les vrais poids Julia sur trois messages fictifs est également disponible :

```bash
uv run --extra julia python -m app.smoke_julia
```

## Structure

```text
app/
  auth.py        Utilisateurs, sessions et chiffrement des mots de passe IMAP
  imap.py        Connexion TLS et normalisation des messages MIME
  classifier.py Adaptateurs LAYA/PyTorch, Julia/PyTorch et moteur de test
  inference.py  Processus d’inférence isolé et arrêt libérant sa mémoire
  db.py          Persistance SQLite et propriétaires des données
  runner.py      Exécutions, choix du modèle, pause et métriques
  main.py        API FastAPI
  static/        Interface web
tests/           Tests du parcours et de l’isolation
```

Les scores sont des aides au tri. Comparez les sorties des deux modèles sur vos messages avant de leur accorder la même confiance.
