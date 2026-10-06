# Schéma de la base de données

Trois tables, préfixées `game_`.

```text
game_player 1───n game_participation n───1 game_game
     │                                         │
     └──────────────── master (0..1) ──────────┘
```

## `game_player` — `Player`

| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint, PK | |
| `name` | varchar(150), unique | Nom affiché |
| `created_at` | datetime | Auto |

## `game_game` — `Game`

| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint, PK | |
| `master_id` | FK → `game_player`, nullable | Maître du jeu (facultatif) |
| `started_at` | datetime, nullable, indexé | Début de la partie |
| `ended_at` | datetime, nullable | Fin ; `NULL` = partie en cours |
| `winner_role` | varchar(20), nullable | `kind` (gentils) ou `villain` (méchants) |

Seules les parties avec `started_at`, `ended_at` **et** `winner_role` renseignés comptent
dans les statistiques (`Game.objects.finished()`).

## `game_participation` — `Participation`

| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint, PK | |
| `player_id` | FK → `game_player` | Suppression en cascade |
| `game_id` | FK → `game_game` | Suppression en cascade |
| `role` | varchar(20) | `kind` ou `villain` |
| `info` | varchar(20) | Distinction : `meilleur`, `neutre` (défaut) ou `pire` |
| `created_at` | datetime | Auto |

Contrainte `unique_player_per_game` sur (`player_id`, `game_id`).

Un joueur **gagne** une partie quand `participation.role == game.winner_role`.

## Calcul des statistiques

Les statistiques ne sont pas stockées : `game/stats/records.py` charge toutes les parties
terminées de la période en deux requêtes, puis `StatsEngine` (`game/stats/engine.py`)
calcule tout en mémoire. Pour quelques milliers de parties, une page se calcule en
quelques dizaines de millisecondes.
