# Schéma de la base de données — Time Bomb

Ce document décrit les modèles Django et le mappage vers la base de données.

## Modèles

### Player
- Table: `game_player`
- Champs:
  - `id` (BigAutoField, PK)
  - `name` (varchar(150), unique)
  - `created_at` (datetime, auto_now_add)
- Usage: représente un joueur enregistré dans l'application.

### Game
- Table: `game_game`
- Champs:
  - `id` (BigAutoField, PK)
  - `master_id` (FK -> `game_player.id`, nullable) : maître de la partie
  - `started_at` (datetime, nullable) : date/heure de démarrage
  - `ended_at` (datetime, nullable) : date/heure de fin
  - `winner_role` (varchar(20), choices `villain`/`kind`, nullable) : rôle gagnant (Méchant/Gentil)
- Usage: chaque enregistrement est une partie de Time Bomb.

### Participation
- Table: `game_participation`
- Champs:
  - `id` (BigAutoField, PK)
  - `player_id` (FK -> `game_player.id`) : joueur
  - `game_id` (FK -> `game_game.id`) : partie
  - `role` (varchar(20), choices `villain`/`kind`) : rôle joué dans la partie
  - `info` (text, blank) : informations supplémentaires (optionnel)
  - `created_at` (datetime, auto_now_add)
- Contraintes: `unique_together = ('player','game')` (un joueur ne peut avoir qu'une participation par partie)

## Extraits de migration
La migration initiale (`game/migrations/0001_initial.py`) crée ces trois tables et les relations décrites ci-dessus.

## Requêtes importantes (exemples)
- Joueurs n'ayant pas participé à une partie `g` :
  SELECT * FROM game_player p WHERE NOT EXISTS (
    SELECT 1 FROM game_participation pp WHERE pp.player_id = p.id AND pp.game_id = <g.id>
  );

- Compter victoires d'un joueur par rôle (ORM):
  Player.objects.annotate(wins_count=Count('participations', filter=Q(participations__game__winner_role=F('participations__role'))))

- Paires fréquentes (raw SQL utilisé dans `views.stats`): compter parties jouées ensemble et victoires par côté.

## Remarques
- Le modèle stocke `winner_role` (le rôle gagnant). Le système compte actuellement une victoire d'un joueur si sa participation a `role == game.winner_role`.
- Les colonnes `role` et `winner_role` utilisent les valeurs techniques `'villain'` et `'kind'` en base, et les labels humains (`'Méchant'`, `'Gentil'`) sont fournis via `ROLE_CHOICES`.

## Migration / évolution
- Pour ajouter un nouveau champ, créer une migration via `python manage.py makemigrations game` puis `python manage.py migrate`.
- Pour modifications structurelles en production, appliquez des sauvegardes et exécutez les migrations dans une fenêtre de maintenance.

---
Fichier généré automatiquement par l'outil d'assistance — ajustez si nécessaire.
