"""Génère des soirées de Time Bomb simulées pour tester l'application en local.

Chaque joueur fictif a un niveau caché en gentil et en méchant : les stats
obtenues ont donc du relief (spécialistes, duos efficaces, chats noirs…).

    python manage.py simulate_games                 # ~300 parties sur 14 mois
    python manage.py simulate_games --reset         # repart d'une base vide
    python manage.py simulate_games --games 50 --seed 7
"""

import math
import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from game.models import Award, Game, Participation, Player, Role

NAMES = [
    "Alice", "Bastien", "Camille", "Dylan", "Emma", "Florian", "Gaëlle",
    "Hugo", "Inès", "Julien", "Léa", "Maxime", "Nina", "Oscar",
]  # fmt: skip

# Distribution officielle des cartes rôle : (gentils, méchants) mélangées puis
# distribuées, la carte en trop (4 et 7 joueurs) restant cachée.
ROLE_DECKS = {4: (3, 2), 5: (3, 2), 6: (4, 2), 7: (5, 3), 8: (5, 3)}


class Command(BaseCommand):
    help = "Génère des parties simulées (développement uniquement)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--games", type=int, default=300, help="Nombre approximatif de parties."
        )
        parser.add_argument("--players", type=int, default=10, help="Nombre de joueurs (max 14).")
        parser.add_argument("--months", type=int, default=14, help="Étalement dans le passé.")
        parser.add_argument("--seed", type=int, default=None, help="Graine aléatoire.")
        parser.add_argument(
            "--reset", action="store_true", help="Supprime toutes les données avant."
        )
        parser.add_argument("--no-input", action="store_true", help="Ne pas demander confirmation.")
        parser.add_argument(
            "--force", action="store_true", help="Autorise l'exécution quand DEBUG est désactivé."
        )

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusé : DEBUG est désactivé (base de prod ?). Utilise --force.")
        rng = random.Random(opts["seed"])
        count = max(1, min(opts["players"], len(NAMES)))

        if opts["reset"]:
            if not opts["no_input"]:
                answer = input("Supprimer TOUTES les parties et tous les joueurs ? [o/N] ")
                if answer.strip().lower() not in {"o", "oui", "y", "yes"}:
                    raise CommandError("Annulé.")
            Game.objects.all().delete()
            Player.objects.all().delete()

        with transaction.atomic():
            players = [Player.objects.get_or_create(name=name)[0] for name in NAMES[:count]]
            profiles = {
                p.pk: {
                    "kind": rng.gauss(0, 0.45),
                    "villain": rng.gauss(0, 0.55),
                    "assiduity": rng.uniform(0.35, 0.95),
                }
                for p in players
            }
            created = self._simulate(rng, players, profiles, opts["games"], opts["months"])

        self.stdout.write(
            self.style.SUCCESS(f"✔ {created} parties simulées avec {len(players)} joueurs.")
        )
        self.stdout.write("  Lance `make run` puis ouvre http://127.0.0.1:8000/stats/")

    def _simulate(self, rng, players, profiles, target_games, months):
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        start = today - timedelta(days=30 * months)
        days = [start + timedelta(days=i) for i in range((today - start).days)]
        # Soirées plutôt le vendredi/samedi, parfois en semaine.
        weights = [{4: 5, 5: 6, 6: 2}.get(d.weekday(), 1) for d in days]
        sessions = max(1, round(target_games / 5))
        session_days = sorted(set(rng.choices(days, weights=weights, k=sessions)))

        created = 0
        for day in session_days:
            present = [p for p in players if rng.random() < profiles[p.pk]["assiduity"]]
            if len(present) < 4:
                present = rng.sample(players, k=min(len(players), rng.randint(4, 6)))
            moment = timezone.make_aware(
                datetime.combine(day, time(20, 30)) + timedelta(minutes=rng.randint(0, 75)), tz
            )
            for _ in range(rng.randint(2, 8)):
                table = rng.sample(present, k=min(len(present), rng.randint(4, 8)))
                duration = timedelta(minutes=rng.randint(8, 28))
                self._play(rng, table, profiles, moment, duration)
                moment += duration + timedelta(minutes=rng.randint(2, 10))
                created += 1
        return created

    def _play(self, rng, table, profiles, start, duration):
        kinds, villains = ROLE_DECKS[len(table)]
        deck = [Role.KIND] * kinds + [Role.VILLAIN] * villains
        rng.shuffle(deck)
        roles = dict(zip((p.pk for p in table), deck, strict=False))
        if Role.VILLAIN not in roles.values():  # carte cachée = le seul méchant
            roles[rng.choice(table).pk] = Role.VILLAIN

        kind_skill = sum(profiles[pid]["kind"] for pid, r in roles.items() if r == Role.KIND)
        villain_skill = sum(
            profiles[pid]["villain"] for pid, r in roles.items() if r == Role.VILLAIN
        )
        # Léger avantage structurel aux méchants, puis le niveau des joueurs.
        p_kind = 1 / (1 + math.exp(-(kind_skill - villain_skill - 0.15)))
        winner = Role.KIND if rng.random() < p_kind else Role.VILLAIN

        game = Game.objects.create(started_at=start, ended_at=start + duration, winner_role=winner)
        winners = [p for p in table if roles[p.pk] == winner]
        losers = [p for p in table if roles[p.pk] != winner]
        best = rng.choice(winners) if winners and rng.random() < 0.8 else None
        worst = rng.choice(losers) if losers and rng.random() < 0.6 else None
        Participation.objects.bulk_create(
            Participation(
                game=game,
                player=p,
                role=roles[p.pk],
                info=Award.BEST if p == best else Award.WORST if p == worst else Award.NEUTRAL,
            )
            for p in table
        )
