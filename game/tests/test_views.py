from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.models import Award, Game, Participation, Player, Role
from game.stats import session_day


class GameFlowTests(TestCase):
    def setUp(self):
        self.players = [Player.objects.create(name=n) for n in ("Alice", "Bob", "Chloé", "Dan")]

    def _post_result(self, game, action, winner=Role.VILLAIN, villains=("Alice", "Bob"), **extra):
        data = {"action": action, "winner_role": winner, **extra}
        for p in self.players:
            data[f"role_{p.pk}"] = Role.VILLAIN if p.name in villains else Role.KIND
            data[f"info_{p.pk}"] = Award.NEUTRAL
        return self.client.post(reverse("game:game_manage", args=[game.pk]), data)

    def test_full_game_flow(self):
        response = self.client.post(reverse("game:game_create"))
        game = Game.objects.get()
        self.assertRedirects(response, reverse("game:game_manage", args=[game.pk]))
        self.assertTrue(game.is_active)

        self.client.post(
            reverse("game:game_add_players", args=[game.pk]),
            {"players": [p.pk for p in self.players[:3]], "new_names": "Dan, Eve"},
        )
        self.players.append(Player.objects.get(name="Eve"))
        self.assertEqual(game.participations.count(), 5)
        self.assertEqual(Player.objects.filter(name="Dan").count(), 1)  # pas de doublon

        response = self._post_result(game, "finish")
        game.refresh_from_db()
        self.assertRedirects(response, game.get_absolute_url())
        self.assertTrue(game.is_finished)
        self.assertEqual(game.winner_role, Role.VILLAIN)
        self.assertEqual(game.participations.filter(role=Role.VILLAIN).count(), 2)

    def test_finish_requires_winner_and_both_sides(self):
        game = Game.objects.create(started_at=timezone.now())
        for p in self.players:
            Participation.objects.create(game=game, player=p)
        response = self._post_result(game, "finish", winner="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choisis le camp gagnant")
        response = self._post_result(game, "finish", villains=())
        self.assertContains(response, "au moins un gentil et un méchant")
        game.refresh_from_db()
        self.assertIsNone(game.ended_at)

    def test_save_without_finishing(self):
        game = Game.objects.create(started_at=timezone.now())
        for p in self.players:
            Participation.objects.create(game=game, player=p)
        self._post_result(game, "save", winner="")
        game.refresh_from_db()
        self.assertIsNone(game.ended_at)
        self.assertEqual(game.participations.filter(role=Role.VILLAIN).count(), 2)

    def test_rematch_copies_players(self):
        game = Game.objects.create(started_at=timezone.now())
        for p in self.players:
            Participation.objects.create(game=game, player=p, role=Role.VILLAIN)
        self.client.post(reverse("game:game_rematch", args=[game.pk]))
        new = Game.objects.exclude(pk=game.pk).get()
        self.assertEqual(new.participations.count(), 4)
        self.assertFalse(new.participations.filter(role=Role.VILLAIN).exists())

    def test_mutations_require_post(self):
        game = Game.objects.create(started_at=timezone.now())
        for name in ("game_delete", "game_rematch", "game_add_players"):
            self.assertEqual(
                self.client.get(reverse(f"game:{name}", args=[game.pk])).status_code, 405
            )
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())

    def test_remove_and_delete(self):
        game = Game.objects.create(started_at=timezone.now())
        Participation.objects.create(game=game, player=self.players[0])
        self.client.post(reverse("game:game_remove_player", args=[game.pk, self.players[0].pk]))
        self.assertFalse(game.participations.exists())
        self.client.post(reverse("game:game_delete", args=[game.pk]))
        self.assertFalse(Game.objects.exists())

    def test_player_create_rejects_duplicates(self):
        self.client.post(reverse("game:player_create"), {"name": "  alice "})
        self.assertEqual(Player.objects.filter(name__iexact="alice").count(), 1)
        self.client.post(reverse("game:player_create"), {"name": "Zoé"})
        self.assertTrue(Player.objects.filter(name="Zoé").exists())


class PagesTests(TestCase):
    """Toutes les pages s'affichent, avec et sans données."""

    PAGES = [
        ("game:home", []),
        ("game:game_list", []),
        ("game:player_list", []),
        ("game:stats", []),
        ("game:stats_evolution", []),
        ("game:stats_duos", []),
        ("game:stats_records", []),
        ("game:stats_sessions", []),
    ]

    def test_pages_without_data(self):
        for name, args in self.PAGES:
            with self.subTest(name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_pages_with_simulated_data(self):
        call_command("simulate_games", games=60, seed=1, months=3, force=True, stdout=StringIO())
        game = Game.objects.finished().first()
        player = Player.objects.first()
        day = session_day(game.started_at).isoformat()
        urls = [reverse(name, args=args) for name, args in self.PAGES] + [
            reverse("game:game_detail", args=[game.pk]),
            reverse("game:game_manage", args=[game.pk]),
            reverse("game:player_detail", args=[player.pk]),
            reverse("game:stats_session", args=[day]),
        ]
        for url in urls:
            for query in ("", "?p=last", "?p=30d&min=1", "?p=y2020"):
                with self.subTest(url=url + query):
                    self.assertEqual(self.client.get(url + query).status_code, 200)

    def test_unknown_session_is_404(self):
        self.assertEqual(
            self.client.get(reverse("game:stats_session", args=["2001-01-01"])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("game:stats_session", args=["pas-une-date"])).status_code, 404
        )


class SimulateCommandTests(TestCase):
    def test_refuses_without_debug(self):
        from django.core.management.base import CommandError

        with self.settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("simulate_games", games=5)

    def test_generates_valid_games(self):
        call_command("simulate_games", games=30, seed=3, force=True, stdout=StringIO())
        self.assertGreater(Game.objects.finished().count(), 10)
        for game in Game.objects.prefetch_related("participations"):
            roles = {p.role for p in game.participations.all()}
            self.assertEqual(roles, {Role.KIND, Role.VILLAIN})
            self.assertTrue(4 <= game.participations.count() <= 8)
