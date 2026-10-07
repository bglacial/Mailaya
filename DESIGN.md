# Design

Interface produit claire, utilisée en journée pour consulter et trier des mails. Conserver le thème clair actuel : fond crème teinté, encre prune, accent prune, couleurs sémantiques pour les états.

Les variables OKLCH de `app/static/app.css` constituent la source des couleurs. Palette restreinte, neutres teintés et un accent prune. Polices système pour une lecture régulière et aucun téléchargement externe. Hiérarchie par taille et graisse ; lignes, espaces et titres structurent les contenus plutôt qu'une accumulation de cartes.

Quatre espaces : Messages, Brief quotidien, Analyses, Paramètres. Une navigation latérale sur ordinateur devient horizontale sur écran étroit. La page Messages associe recherche, vues et tableau de quatre colonnes. Un volet contient l'aperçu et le suivi ; les corrections et les scores se déplient séparément. Sur écran étroit, ce volet remplace temporairement la liste, avec retour explicite.

Le brief possède son propre sélecteur de boîte, indépendant du filtre des messages et de la boîte configurée. Les paramètres séparent boîtes mail, fonctions par boîte, connexions IA, règles et compte. Une activation dévoile ses options dépendantes. Les formulaires cachés pendant la navigation gardent leurs saisies ; un changement de boîte ne peut pas abandonner les réglages non enregistrés. Les calculs coûteux restent désactivés par défaut et activables par boîte.

Pas de nouvelle bibliothèque frontend. Libellés accessibles, focus visible, titres focalisés à la navigation et retour du focus à la fermeture du lecteur. Le guide reste disponible sans connexion, depuis le rail ou le menu de compte sur mobile. Le motif de suppression des résultats se confirme dans la page, sans fenêtre modale.
