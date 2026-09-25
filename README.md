# Mailaya

Mailaya récupère des messages Gmail depuis une date donnée et les analyse localement avec [`aac6fef/laya-multilingual-mlx`](https://huggingface.co/aac6fef/laya-multilingual-mlx). Pour chaque message, l’application conserve :

- la catégorie gagnante et la matrice complète des probabilités ;
- un score de priorité sur 100 ;
- un score de spam sur 100 ;
- un score d’action requise sur 100 ;
- le temps d’inférence, hors chargement initial du modèle.

L’interface inclut la progression, les erreurs, la pause/reprise, les statistiques de latence et un mode démonstration sans accès à une boîte mail.

## Prérequis

- Mac Apple Silicon ;
- macOS 14 ou plus récent ;
- Python 3.11 ou plus récent ;
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) ;
- environ 700 Mio disponibles pour le modèle MLX ;
- un client OAuth Google pour Gmail.

Le moteur de démonstration fonctionne aussi sans MLX et sans compte Google. Il contient 500 messages fictifs.

## Installation

Depuis le dossier du projet :

```bash
cp .env.example .env
uv sync --extra dev
```

## Lancement

Pour lancer l’application avec la configuration du fichier `.env` :

```bash
uv run uvicorn app.main:app --reload
```

Pour découvrir immédiatement l’interface sans compte mail ni téléchargement du modèle :

```bash
LAYA_BACKEND=demo uv run uvicorn app.main:app --reload
```

Ouvrez ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000). La documentation de l’API est disponible sous `/api/docs`.

Arrêtez le serveur avec `Ctrl+C`.

Au premier traitement réel, `laya-mlx` télécharge le checkpoint d’environ 644 Mo depuis Hugging Face. Les traitements suivants utilisent le cache local. Le téléchargement initial n’est pas compté dans le temps affiché pour le premier mail.

## Configuration Gmail

1. Créez ou sélectionnez un projet dans Google Cloud Console.
2. Activez **Gmail API** dans la bibliothèque des API.
3. Configurez l’écran de consentement OAuth. En mode test, ajoutez votre adresse Gmail aux utilisateurs de test.
4. Créez un client OAuth 2.0 de type **Application Web**.
5. Dans **Google Auth Platform → Clients**, ouvrez ce client et ajoutez l’URI de redirection affichée par Mailaya quand vous sélectionnez **Gmail**. Avec l’adresse de lancement par défaut, elle vaut :

```text
http://127.0.0.1:8000/api/auth/google/callback
```

Google exige une correspondance exacte avec l’URI envoyée par l’application. Le nom d’hôte (`localhost` ou `127.0.0.1`), le port (`8000`, `8766`, etc.), le chemin et la barre finale doivent être identiques. Par exemple, si Mailaya est ouvert sur `http://127.0.0.1:8766`, autorisez `http://127.0.0.1:8766/api/auth/google/callback`. Utilisez un client OAuth de type **Application Web** et enregistrez l’URI dans **URI de redirection autorisés**, pas dans les origines JavaScript.

6. Copiez les identifiants dans `.env` :

```dotenv
GOOGLE_CLIENT_ID=votre-identifiant-google
GOOGLE_CLIENT_SECRET=votre-secret-google
```

Redémarrez ensuite le serveur, sélectionnez **Gmail** et cliquez sur **Connecter Gmail**. L’application demande uniquement l’autorisation `gmail.readonly`. Le jeton est conservé dans `data/google-token.json` avec des permissions limitées à l’utilisateur local.

## Configuration LAYA

Le mode `auto` utilise LAYA lorsqu’il détecte Apple Silicon et le paquet `laya-mlx`. Pour imposer le modèle réel et échouer explicitement si MLX n’est pas disponible :

```dotenv
LAYA_BACKEND=laya
LAYA_MODEL=aac6fef/laya-multilingual-mlx
LAYA_DTYPE=float16
```

Pour travailler uniquement avec les données de démonstration :

```dotenv
LAYA_BACKEND=demo
```

Le modèle reçoit l’expéditeur, l’objet et un aperçu du corps. Gmail est interrogé par pages pouvant contenir jusqu’à 500 références, puis chaque aperçu est récupéré en lecture seule. Aucun contenu de mail n’est envoyé à un service d’IA distant.

## Tests

```bash
uv run pytest
```

Les tests utilisent le moteur déterministe de démonstration. Ils ne téléchargent pas le checkpoint et n’accèdent pas à Gmail.

## Structure

```text
app/
  gmail.py       OAuth Google et récupération Gmail
  classifier.py  Adaptateurs LAYA et démonstration
  db.py          Persistance SQLite
  runner.py      Exécutions, pause et métriques
  main.py        API FastAPI
  static/        Interface web accessible et responsive
tests/           Tests ciblés du classement et du parcours complet
```

## Limites de cette première version

- Le corps complet et les pièces jointes ne sont pas analysés, seulement `bodyPreview`.
- Les exécutions sont séquentielles afin de mesurer une latence claire par mail et de contenir l’usage mémoire.
- Les caches OAuth sont protégés par les permissions du système de fichiers, mais ne sont pas chiffrés applicativement.
- Les scores reflètent les sorties du modèle et doivent rester une aide au tri, pas une décision de sécurité autonome.
