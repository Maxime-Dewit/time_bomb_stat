from datetime import UTC, date, datetime, timedelta

from django.test import SimpleTestCase, TestCase, override_settings

from game.models import Award, Player, Role
from game.stats import GameRecord, Period, Seat, StatsEngine, session_day
from game.stats.engine import streaks

K, V = Role.KIND, Role.VILLAIN


def make_players(*names):
    return [Player(pk=i, name=n) for i, n in enumerate(names, start=1)]


def record(game_id, day, winner, *seats, hour=21):
    start = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
    return GameRecord(
        id=game_id,
        started_at=start,
        ended_at=start + timedelta(minutes=15),
        winner=winner,
        day=day,
        seats=tuple(Seat(pid, role, award) for pid, role, award in seats),
    )


D1, D2 = date(2026, 3, 6), date(2026, 4, 10)
A, B, C, D = make_players("Alice", "Bob", "Chloé", "Dan")


def engine():
    records = [
        # Alice & Bob méchants gagnent
        record(
            1,
            D1,
            V,
            (1, V, Award.BEST),
            (2, V, Award.NEUTRAL),
            (3, K, Award.WORST),
            (4, K, "neutre"),
        ),
        # Alice & Chloé gentilles gagnent
        record(2, D1, K, (1, K, "neutre"), (3, K, Award.BEST), (2, V, "neutre"), (4, V, "neutre")),
        # Alice & Dan méchants perdent
        record(
            3, D2, K, (1, V, "neutre"), (4, V, Award.WORST), (2, K, Award.BEST), (3, K, "neutre")
        ),
    ]
    return StatsEngine(records, [A, B, C, D])


class StreakTests(SimpleTestCase):
    def test_streaks(self):
        self.assertEqual(streaks([True, True, False, True, True, True]), (3, 1, 3))
        self.assertEqual(streaks([False, False]), (0, 2, -2))
        self.assertEqual(streaks([]), (0, 0, 0))


class PlayerLineTests(SimpleTestCase):
    def test_counts_and_percentages(self):
        alice = engine().lines[1]
        self.assertEqual((alice.games, alice.wins, alice.losses), (3, 2, 1))
        self.assertEqual((alice.villain_games, alice.villain_wins), (2, 1))
        self.assertEqual((alice.kind_games, alice.kind_wins), (1, 1))
        self.assertEqual(alice.villain_pct, 50.0)
        self.assertEqual(alice.kind_pct, 100.0)
        self.assertEqual(alice.best, 1)
        self.assertEqual(alice.current_streak, -1)
        self.assertEqual(alice.best_streak, 2)
        self.assertEqual(alice.villain_run, 1)

    def test_leaderboard_respects_min_games(self):
        eng = engine()
        self.assertEqual([line.player.name for line in eng.leaderboard(min_games=4)], [])
        board = eng.leaderboard(min_games=1)
        self.assertEqual(board[0].player.name, "Alice")
        self.assertEqual([line.rank for line in board], [1, 2, 3, 4])

    def test_overview(self):
        o = engine().overview
        self.assertEqual(o["games"], 3)
        self.assertEqual((o["kind_wins"], o["villain_wins"]), (2, 1))
        self.assertEqual(o["sessions"], 2)
        self.assertEqual(o["avg_minutes"], 15)


class PairTests(SimpleTestCase):
    def test_same_team_and_opposed(self):
        pairs = engine().pairs
        ab = pairs[(1, 2)]  # Alice & Bob
        self.assertEqual((ab.together, ab.same, ab.same_wins), (3, 1, 1))
        self.assertEqual((ab.both_villain, ab.both_villain_wins), (1, 1))
        self.assertEqual((ab.opposed, ab.a_wins_opposed), (2, 1))

    def test_oriented_view(self):
        ab = engine().pairs[(1, 2)]
        ba = ab.oriented(2)
        self.assertEqual(ba.a.name, "Bob")
        self.assertEqual(ba.a_wins_opposed, ab.b_wins_opposed)

    def test_matrix_is_square(self):
        m = engine().matrix(min_games=1)
        self.assertEqual(len(m["rows"]), 4)
        self.assertTrue(all(len(r["cells"]) == 4 for r in m["rows"]))


class PeriodSummaryTests(SimpleTestCase):
    def test_champions_and_titles(self):
        eng = engine()
        march = next(s for s in eng.by_month if s.start == date(2026, 3, 1))
        self.assertEqual(march.key, "m2026-03")
        self.assertEqual([c.player.name for c in march.champions], ["Alice"])
        alice_titles = next(t for t in eng.titles if t["line"].player.name == "Alice")
        self.assertEqual(alice_titles["month"], 1)

    def test_ties_are_shared(self):
        eng = engine()
        april = eng.day_summary(D2)
        # Bob et Chloé gagnent tous les deux l'unique partie du jour
        self.assertEqual(sorted(c.player.name for c in april.champions), ["Bob", "Chloé"])


class EloTests(SimpleTestCase):
    def test_elo_is_zero_sum_for_equal_teams(self):
        eng = engine()
        total = sum(rating for rating, _ in eng.elo_final.values())
        self.assertAlmostEqual(total, 4000, places=6)

    def test_winner_gains(self):
        eng = StatsEngine([record(1, D1, K, (1, K, "neutre"), (2, V, "neutre"))], [A, B])
        self.assertGreater(eng.lines[1].elo, 1000)
        self.assertLess(eng.lines[2].elo, 1000)


class TimelineTests(SimpleTestCase):
    def test_timeline_has_one_value_per_day(self):
        t = engine().timeline()
        self.assertEqual(t["labels"], ["2026-03-06", "2026-04-10"])
        alice = next(p for p in t["players"] if p["name"] == "Alice")
        self.assertEqual(alice["series"]["wins"], [2, 2])
        self.assertEqual(alice["series"]["villain"], [1, 1])

    def test_calendar_covers_a_year(self):
        cal = engine().calendar()
        self.assertGreaterEqual(len(cal["weeks"]), 52)
        self.assertEqual(cal["total_days"], 2)


class EmptyEngineTests(SimpleTestCase):
    def test_everything_works_without_games(self):
        eng = StatsEngine([], [A])
        self.assertTrue(eng.is_empty)
        self.assertEqual(eng.leaderboard(), [])
        self.assertEqual(eng.records_board, [])
        self.assertEqual(eng.timeline()["labels"], [])
        self.assertEqual(eng.superlatives(1), [])


class PeriodParsingTests(SimpleTestCase):
    today = date(2026, 10, 6)

    def test_parse(self):
        self.assertEqual(Period.parse("y2025", self.today, None).start, date(2025, 1, 1))
        self.assertEqual(Period.parse("m2026-02", self.today, None).end, date(2026, 2, 28))
        self.assertEqual(Period.parse("last", self.today, D2).start, D2)
        self.assertEqual(Period.parse("30d", self.today, None).start, date(2026, 9, 7))

    def test_invalid_falls_back_to_all(self):
        for raw in ("nimporte", "m2026-13", "d2026-02-30", None, ""):
            self.assertTrue(Period.parse(raw, self.today, None).is_all, raw)


@override_settings(TIME_ZONE="Europe/Paris", TIMEBOMB_DAY_CUTOFF_HOUR=6)
class SessionDayTests(TestCase):
    def test_after_midnight_counts_for_previous_evening(self):
        # 1h30 à Paris le 7 mars = 0h30 UTC
        self.assertEqual(session_day(datetime(2026, 3, 7, 0, 30, tzinfo=UTC)), date(2026, 3, 6))
        self.assertEqual(session_day(datetime(2026, 3, 6, 20, 0, tzinfo=UTC)), date(2026, 3, 6))
