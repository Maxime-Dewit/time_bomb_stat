# Time Bomb — Django + PostgreSQL

Installation rapide (PostgreSQL recommandé):

1. Créer un virtualenv et installer dépendances:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Commandes utiles

- Créer un utilisateur admin Django (pour `/admin/`):

```bash
python manage.py createsuperuser
```

- Réinitialiser les données (vider la base sans supprimer la structure) :

```bash
# WARNING: supprime toutes les données
python manage.py flush
```

- Réinitialiser complètement la base (SQLite) :

```bash
rm -f db.sqlite3
python manage.py migrate
```

- Réinitialiser complètement la base (PostgreSQL) :

```bash
# Exemple avec psql/local postgres user
dropdb your_db_name
createdb your_db_name
python manage.py migrate
```

- Supprimer et recréer uniquement les migrations (développement) :

```bash
rm -rf game/migrations && python manage.py makemigrations && python manage.py migrate
```

## Débogage et vérification

- Vérifier l'état des migrations :

```bash
python manage.py showmigrations
```

- Lancer la console Django :

```bash
python manage.py shell
```

## Documentation de la BDD

Voir [docs/db_schema.md](docs/db_schema.md) pour la description détaillée des tables `Player`, `Game` et `Participation` et quelques requêtes exemples.

```

2. Configurer PostgreSQL via `DATABASE_URL` (ex: `postgres://user:pass@host:5432/dbname`). Si non configuré, le projet utilisera SQLite (`db.sqlite3`).

3. Appliquer migrations et lancer:

```bash
python manage.py migrate
python manage.py runserver
```

4. Aller sur http://127.0.0.1:8000/ pour l'interface joueur/maître du jeu et http://127.0.0.1:8000/stats/ pour les statistiques.

Notes:
- L'application permet de créer/join des parties; un maître du jeu peut démarrer/arrêter une partie. Les participants peuvent renseigner leur rôle (méchant/gentil) et informations de la partie.
- Les pages de statistiques listent victoires par joueur, qui est le plus souvent méchant/gentil, combinaisons fréquentes et stats individuelles.
