# 💣 Time Bomb Stats

Application Django pour enregistrer nos parties de **Time Bomb** — qui était gentil
(Sherlock), qui était méchant (Moriarty), qui a gagné, qui a été le meilleur / le pire
joueur — et en tirer toutes les statistiques possibles.

## Ce qu'on y trouve

### Saisie des parties

- Nouvelle partie en un clic, ajout des joueurs par puces (ou création à la volée).
- Rôle de chacun (gentil / méchant), MVP et pire joueur, camp gagnant.
- Compteur des camps en direct avec rappel de la répartition attendue selon le nombre de joueurs.
- « Revanche » : relance une partie avec la même table.
- Saisie après coup possible (date modifiable).

### Statistiques

Toutes filtrables : tout, dernière soirée, 30 jours, une année, un mois.

- **Vue d'ensemble** : podium, classement complet triable (% victoires, % en gentil, % en méchant,
  Elo, MVP, séries, forme), nuage *gentil × méchant* (taille de la bulle = victoires),
  équilibre des camps par mois, par taille de table et par jour de la semaine, profils marquants
  (meilleur méchant, gentil le plus fiable, caméléon, spécialiste, chat noir…).
- **Évolution & palmarès** : courbes dans le temps (victoires, victoires en méchant / en gentil,
  % de victoires, Elo), titres (combien de fois n°1 d'une soirée, d'un mois, d'une année),
  champion / top méchant / top gentil de chaque mois et de chaque année.
- **Duos & rivalités** : meilleurs et pires duos, duos de méchants, duos de gentils, inséparables,
  face-à-face les plus déséquilibrés, matrice joueur × joueur (même équipe ou face à face).
- **Records** : plus longues séries, plus grosse soirée, record Elo, partie la plus longue, MVP…
- **Soirées** : calendrier d'activité, résumé de chaque soirée, page détaillée par soirée.
- **Profil joueur** : Elo, séries, gentil vs méchant, évolution, résultats mensuels, meilleurs
  alliés, bêtes noires, stats avec chaque joueur, dernières parties.

> **Elo** : classement par équipe, corrigé de l'avantage naturel d'un camp (gagner avec le
> camp défavorisé rapporte plus). **Soirée** : une partie commencée avant 6h compte pour la
> veille (réglable via `TIMEBOMB_DAY_CUTOFF_HOUR`).

## Tester en local avec des parties simulées

Prérequis : Python 3.12+.

```bash
make install       # crée .venv, installe les dépendances, copie .env.example en .env
make reset-demo    # crée la base SQLite et génère ~300 parties simulées sur 14 mois
make run           # http://127.0.0.1:8000
```

Sans `make` :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py simulate_games --reset --no-input
python manage.py runserver
```

Options de la simulation :

```bash
python manage.py simulate_games --games 500 --players 12 --months 24 --seed 42
python manage.py simulate_games --reset   # vide la base avant (demande confirmation)
```

Les joueurs simulés ont chacun un niveau caché en gentil et en méchant : les stats ont du
relief (spécialistes, duos efficaces, chats noirs…). La commande refuse de tourner si
`DEBUG` est désactivé, pour ne jamais polluer la base de prod.

Pour repartir de zéro : `rm db.sqlite3 && make migrate`.

## Commandes utiles

| Commande | Effet |
|---|---|
| `make run` | Serveur de développement |
| `make test` | Tests |
| `make lint` / `make format` | Vérification / formatage (ruff) |
| `make check` | Lint + tests + checks Django + migrations à jour |
| `python manage.py createsuperuser` | Compte pour `/admin/` |

## Déploiement (GCP)

L'application est un projet Django standard servi par **gunicorn**, fichiers statiques
servis par **WhiteNoise** (pas besoin de bucket ni de serveur web devant).

Variables d'environnement :

| Variable | Exemple | Rôle |
|---|---|---|
| `DJANGO_SECRET_KEY` | *(longue chaîne aléatoire)* | **Obligatoire** en prod |
| `DJANGO_DEBUG` | `0` | Toujours `0` en prod |
| `DJANGO_ALLOWED_HOSTS` | `stats.example.com` | Domaines autorisés (séparés par des virgules) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://stats.example.com` | Origines HTTPS autorisées pour les formulaires |
| `DATABASE_URL` | `postgres://user:pass@host:5432/timebomb` | Base PostgreSQL |
| `DJANGO_TIME_ZONE` | `Europe/Paris` | Fuseau pour les dates et les soirées |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` | Redirection HTTPS (mettre `0` si le proxy le fait déjà) |
| `DJANGO_SECURE_HSTS_SECONDS` | `0` | HSTS, à activer une fois le HTTPS confirmé |

Étapes à chaque mise à jour :

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn timebomb.wsgi --bind 0.0.0.0:$PORT --workers 2
```

> ⚠️ Mise à jour depuis l'ancienne version : la migration `0005` ne fait que renommer
> des libellés, ajouter un index et remplacer `unique_together` par une contrainte
> équivalente. Aucune donnée n'est modifiée, mais faites quand même une sauvegarde avant.

<!-- deux encadrés distincts -->

> 🔐 L'application n'a pas d'authentification : quiconque a l'URL peut saisir ou supprimer
> des parties. Si elle est publique, protégez-la (Identity-Aware Proxy sur GCP, ou
> authentification basique au niveau du load balancer).

## Organisation du code

```text
game/
├── models.py              Player, Game, Participation (+ choix Role / Award)
├── forms.py               Formulaires de saisie (validation : gagnant, camps…)
├── views/                 games.py · players.py · stats.py
├── stats/
│   ├── records.py         Chargement des parties en objets légers (2 requêtes SQL)
│   ├── periods.py         Filtre de période (?p=all|last|30d|y2026|m2026-10|d2026-10-05)
│   └── engine.py          StatsEngine : toutes les stats, calculées en mémoire
├── management/commands/
│   └── simulate_games.py  Génération de parties de démonstration
├── templates/game/        Gabarits (base, parties, joueurs, stats, partials)
├── static/game/           app.css (thème clair/sombre) · app.js · charts.js (Chart.js)
└── tests/                 Tests du moteur de stats et des vues
```

Schéma de la base : [docs/db_schema.md](docs/db_schema.md).
