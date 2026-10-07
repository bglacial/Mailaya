# Mailaya

Mailaya récupère des messages Gmail depuis une date donnée et les analyse localement avec [Julia-1 / PyTorch](https://huggingface.co/SupersonicLabs/Julia-1) sur Linux, ou [LAYA MLX](https://huggingface.co/aac6fef/laya-multilingual-mlx) sur Mac Apple Silicon. Pour chaque message, l’application conserve :

- la catégorie gagnante et la matrice complète des probabilités ;
- un score de priorité sur 100 ;
- un score de spam sur 100 ;
- un score d’action requise sur 100 ;
- le temps d’inférence, hors chargement initial du modèle.

L’interface inclut la progression, les erreurs, la pause/reprise, les statistiques de latence et un mode démonstration sans accès à une boîte mail.

## Prérequis

- Linux avec CPU x86_64 ou ARM64 pour Julia, ou Mac Apple Silicon avec macOS 14+ pour MLX ;
- Python 3.11 ou plus récent ;
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) ;
- environ 551 Mio pour les poids Julia FP32, plus le runtime PyTorch, le tokenizer et la mémoire d’inférence ; environ 700 Mio pour le checkpoint MLX ;
- un client OAuth Google pour Gmail.

Le moteur de démonstration fonctionne aussi sans MLX et sans compte Google. Il contient 500 messages fictifs.

## Installation

Depuis le dossier du projet :

```bash
cp .env.example .env
```

Sur **Linux**, installez le moteur Julia natif :

```bash
uv sync --extra julia --extra dev
```

`uv` installe PyTorch CPU sur Linux : aucun GPU ni MLX n’est nécessaire. Git doit être disponible pour installer le runtime officiel Julia. Le runtime et le checkpoint Julia-1 sont figés à la révision `a85b127321d580d65176c89ced8273f305745d85`.

Sur **Mac Apple Silicon**, ou pour utiliser uniquement le moteur de démonstration :

```bash
uv sync --extra dev
```

## Lancement

Pour lancer l’application avec la configuration du fichier `.env` :

```bash
uv run uvicorn app.main:app --reload
```

Sur Linux avec Julia, gardez l’extra actif au lancement pour que `uv` conserve ses dépendances :

```bash
uv run --extra julia uvicorn app.main:app --reload
```

Pour découvrir immédiatement l’interface sans compte mail ni téléchargement du modèle :

```bash
LAYA_BACKEND=demo uv run uvicorn app.main:app --reload
```

Ouvrez ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000). La documentation de l’API est disponible sous `/api/docs`.

Arrêtez le serveur avec `Ctrl+C`.

Au premier traitement avec Julia, Mailaya télécharge les poids, les configurations et le tokenizer depuis Hugging Face. Le moteur reste chargé entre les mails et les traitements suivants utilisent le cache local. En mode MLX, `laya-mlx` télécharge son propre checkpoint. Le téléchargement et le chargement initial ne sont pas comptés dans le temps d’inférence affiché.

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

## Configuration des moteurs

`LAYA_BACKEND=auto` choisit MLX sur Apple Silicon si `laya-mlx` est installé, et Julia sur Linux et les autres plateformes. Sur un Mac Apple Silicon sans MLX, il choisit Julia si son runtime est installé, sinon la démonstration. Sur Linux, une installation Julia manquante produit une erreur explicite au premier traitement. Pour imposer un moteur, utilisez `julia`, `laya` (ou `mlx`), ou `demo`. Une valeur inconnue est rejetée.

### Julia / Linux

```dotenv
LAYA_BACKEND=julia
JULIA_MODEL=SupersonicLabs/Julia-1
JULIA_REVISION=a85b127321d580d65176c89ced8273f305745d85
JULIA_DEVICE=cpu
JULIA_CPU_THREADS=4
```

Les paramètres `LAYA_MODEL` et `LAYA_DTYPE` restent réservés à MLX : un ancien `.env` ne fera pas charger un checkpoint MLX avec Julia. Pour essayer Julia sur Mac, installez aussi l’extra `julia` et imposez `LAYA_BACKEND=julia`.

Pour un checkpoint déjà téléchargé, définissez `JULIA_MODEL=/chemin/vers/Julia-1`. Le répertoire doit contenir `model.safetensors`, `julia_config.json`, `encoder/config.json` et le dossier `tokenizer/`. Mailaya ne télécharge rien si ce répertoire existe. Le cache distant utilise les variables standard Hugging Face, par exemple `HF_HOME` et `HF_HUB_OFFLINE=1` une fois le modèle téléchargé.

Un autre checkpoint doit être compatible avec le runtime natif Julia ; ce moteur ne charge pas les modèles génératifs arbitraires. Pour un autre dépôt, adaptez aussi `JULIA_REVISION` (ou laissez-la vide). `JULIA_DEVICE=cuda` nécessite une installation PyTorch CUDA appropriée ; l’extra fourni par `uv` cible le CPU Linux.

Julia reçoit les quatre questions dans un même appel et les évalue indépendamment, avec encodage strict, une limite combinée de 8 192 tokens et un budget de 512 tokens pour chaque question et ses choix. Un dépassement est signalé sur le mail concerné. Une erreur de téléchargement ou de chargement arrête l’exécution avec un message explicite et conserve les mails en attente.

Les catégories et scores conservent le format Mailaya, mais les décisions de Julia et de LAYA ne sont pas nécessairement identiques. Évaluez les résultats sur vos messages avant de leur accorder la même confiance.

### LAYA / Apple Silicon

Pour imposer le modèle MLX :

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
uv run --extra dev pytest
```

Les tests couvrent le moteur déterministe, la sélection des backends Linux/Mac, l’adaptateur Julia, ses erreurs de chargement et le parcours API → SQLite. Le runtime Julia est simulé dans ces tests : ils ne téléchargent pas le checkpoint et n’accèdent pas à Gmail.

Pour vérifier une vraie inférence Julia sur trois mails fictifs, sans compte Gmail :

```bash
LAYA_BACKEND=julia uv run --extra julia python -m app.smoke_julia
```

Cette commande charge les vrais poids et vérifie le parcours complet de traitement avec une base SQLite temporaire. Le premier lancement nécessite un accès réseau à Hugging Face, sauf si le checkpoint est déjà en cache ou fourni par chemin local.

Validation du portage : 26 tests passants sur macOS et dans un conteneur Debian Linux ARM64 avec Python 3.12.7 ; trois mails fictifs analysés avec les vrais poids Julia-1 et PyTorch `2.14.1+cpu`, sans échec. Le GPU, Linux x86_64 et une boîte Gmail réelle n’ont pas été testés lors de cette validation. Elle vérifie le fonctionnement, pas la précision du classement sur vos messages.

## Structure

```text
app/
  gmail.py       OAuth Google et récupération Gmail
  classifier.py  Adaptateurs Julia/PyTorch, LAYA MLX et démonstration
  smoke_julia.py Vérification avec les vrais poids sur des mails fictifs
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
