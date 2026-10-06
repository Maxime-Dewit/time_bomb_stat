"""Calcul de toutes les statistiques à partir d'une liste de `GameRecord`.

`StatsEngine` est purement en mémoire : il reçoit les parties (déjà filtrées
sur une période) et les joueurs, et expose chaque statistique via des
propriétés mises en cache.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property
from itertools import combinations

from game.models import Player, Role

from .periods import month_label
from .records import GameRecord

ELO_START = 1000.0
ELO_K = 24.0
WEEKDAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def fmt_num(value: float) -> str:
    return f"{value:.1f}".replace(".", ",").removesuffix(",0")


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{fmt_num(value)} %"


def streaks(results: list[bool]) -> tuple[int, int, int]:
    """(plus longue série de victoires, de défaites, série en cours signée)."""
    best = worst = run = 0
    for won in results:
        run = (run + 1 if run > 0 else 1) if won else (run - 1 if run < 0 else -1)
        best = max(best, run)
        worst = max(worst, -run)
    return best, worst, run


# --------------------------------------------------------------------------- joueurs


@dataclass
class PlayerLine:
    player: Player
    games: int = 0
    wins: int = 0
    kind_games: int = 0
    kind_wins: int = 0
    villain_games: int = 0
    villain_wins: int = 0
    best: int = 0
    best_wins: int = 0
    worst: int = 0
    results: list[bool] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    days: set[date] = field(default_factory=set)
    first_day: date | None = None
    last_day: date | None = None
    elo: float = ELO_START
    elo_peak: float = ELO_START
    rank: int | None = None

    @property
    def losses(self) -> int:
        return self.games - self.wins

    @property
    def win_pct(self) -> float | None:
        return pct(self.wins, self.games)

    @property
    def kind_pct(self) -> float | None:
        return pct(self.kind_wins, self.kind_games)

    @property
    def villain_pct(self) -> float | None:
        return pct(self.villain_wins, self.villain_games)

    @property
    def villain_rate(self) -> float | None:
        return pct(self.villain_games, self.games)

    @property
    def best_rate(self) -> float | None:
        return pct(self.best, self.games)

    @property
    def role_gap(self) -> float | None:
        """Écart (points) entre % victoire en méchant et en gentil."""
        if self.kind_pct is None or self.villain_pct is None:
            return None
        return round(self.villain_pct - self.kind_pct, 1)

    @cached_property
    def _streaks(self) -> tuple[int, int, int]:
        return streaks(self.results)

    @property
    def best_streak(self) -> int:
        return self._streaks[0]

    @property
    def worst_streak(self) -> int:
        return self._streaks[1]

    @property
    def current_streak(self) -> int:
        return self._streaks[2]

    @property
    def form(self) -> list[bool]:
        return self.results[-5:]

    @property
    def villain_run(self) -> int:
        """Plus longue suite de parties consécutives en méchant."""
        best = run = 0
        for role in self.roles:
            run = run + 1 if role == Role.VILLAIN else 0
            best = max(best, run)
        return best

    @property
    def elo_rounded(self) -> int:
        return round(self.elo)


# --------------------------------------------------------------------------- paires


@dataclass
class PairLine:
    a: Player
    b: Player
    together: int = 0
    same: int = 0
    same_wins: int = 0
    both_villain: int = 0
    both_villain_wins: int = 0
    both_kind: int = 0
    both_kind_wins: int = 0
    opposed: int = 0
    a_wins_opposed: int = 0

    @property
    def same_pct(self) -> float | None:
        return pct(self.same_wins, self.same)

    @property
    def villain_pct(self) -> float | None:
        return pct(self.both_villain_wins, self.both_villain)

    @property
    def kind_pct(self) -> float | None:
        return pct(self.both_kind_wins, self.both_kind)

    @property
    def b_wins_opposed(self) -> int:
        return self.opposed - self.a_wins_opposed

    @property
    def a_vs_b_pct(self) -> float | None:
        return pct(self.a_wins_opposed, self.opposed)

    @property
    def dominance(self) -> float:
        """Écart à 50 % du face-à-face (plus c'est grand, plus c'est déséquilibré)."""
        return abs((self.a_vs_b_pct or 50) - 50)

    def oriented(self, player_id: int) -> PairLine:
        """La même paire vue depuis `player_id` (il devient `a`)."""
        if self.a.pk == player_id:
            return self
        return PairLine(
            a=self.b,
            b=self.a,
            together=self.together,
            same=self.same,
            same_wins=self.same_wins,
            both_villain=self.both_villain,
            both_villain_wins=self.both_villain_wins,
            both_kind=self.both_kind,
            both_kind_wins=self.both_kind_wins,
            opposed=self.opposed,
            a_wins_opposed=self.b_wins_opposed,
        )


# --------------------------------------------------------------------------- périodes


@dataclass
class PeriodSummary:
    key: str  # clé du filtre de période (d2026-10-05, m2026-10, y2026)
    granularity: str  # day | month | year
    label: str
    start: date
    games: int
    kind_wins: int
    villain_wins: int
    players: int
    champions: list[PlayerLine]
    top_villains: list[PlayerLine]
    top_kinds: list[PlayerLine]
    mvps: list[PlayerLine]

    @property
    def kind_pct(self) -> float | None:
        return pct(self.kind_wins, self.games)

    @property
    def champion_wins(self) -> int:
        return self.champions[0].wins if self.champions else 0


def _leaders(lines: Iterable[PlayerLine], metric, minimum: int = 1) -> list[PlayerLine]:
    """Tous les joueurs ex æquo en tête sur `metric` (au moins `minimum`)."""
    lines = list(lines)
    if not lines:
        return []
    top = max(metric(line) for line in lines)
    if top < minimum:
        return []
    return [line for line in lines if metric(line) == top]


# --------------------------------------------------------------------------- moteur


class StatsEngine:
    def __init__(self, records: list[GameRecord], players: Iterable[Player]):
        self.records = sorted(records, key=lambda r: (r.started_at, r.id))
        self.players = {p.pk: p for p in players}

    # ----- base -----------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self.records

    @cached_property
    def days(self) -> list[date]:
        return sorted({r.day for r in self.records})

    @cached_property
    def lines(self) -> dict[int, PlayerLine]:
        lines: dict[int, PlayerLine] = {}
        for r in self.records:
            for seat in r.seats:
                player = self.players.get(seat.player_id)
                if player is None:
                    continue
                line = lines.setdefault(seat.player_id, PlayerLine(player=player))
                won = r.won(seat)
                line.games += 1
                line.wins += won
                if seat.is_villain:
                    line.villain_games += 1
                    line.villain_wins += won
                else:
                    line.kind_games += 1
                    line.kind_wins += won
                line.best += seat.is_best
                line.best_wins += seat.is_best and won
                line.worst += seat.is_worst
                line.results.append(won)
                line.roles.append(seat.role)
                line.days.add(r.day)
                line.first_day = line.first_day or r.day
                line.last_day = r.day
        for pid, (rating, peak) in self.elo_final.items():
            if pid in lines:
                lines[pid].elo, lines[pid].elo_peak = rating, peak
        return lines

    def leaderboard(self, min_games: int = 1) -> list[PlayerLine]:
        """Classement par % de victoires (départage : nombre de victoires, Elo)."""
        ranked = sorted(
            (line for line in self.lines.values() if line.games >= min_games),
            key=lambda line: (-(line.win_pct or 0), -line.wins, -line.elo),
        )
        for i, line in enumerate(ranked, start=1):
            line.rank = i
        return ranked

    def ranked_by(self, metric, min_games: int = 1, reverse: bool = True, limit: int = 5):
        lines = [
            line
            for line in self.lines.values()
            if line.games >= min_games and metric(line) is not None
        ]
        return sorted(lines, key=lambda line: (metric(line), line.games), reverse=reverse)[:limit]

    # ----- vue d'ensemble ---------------------------------------------------------

    @cached_property
    def overview(self) -> dict:
        games = len(self.records)
        kind_wins = sum(r.kind_won for r in self.records)
        durations = [d for r in self.records if (d := r.duration_minutes)]
        per_day = Counter(r.day for r in self.records)
        return {
            "games": games,
            "players": len(self.lines),
            "kind_wins": kind_wins,
            "villain_wins": games - kind_wins,
            "kind_pct": pct(kind_wins, games),
            "villain_pct": pct(games - kind_wins, games),
            "avg_size": round(sum(r.size for r in self.records) / games, 1) if games else None,
            "avg_minutes": round(sum(durations) / len(durations)) if durations else None,
            "sessions": len(per_day),
            "games_per_session": round(games / len(per_day), 1) if per_day else None,
            "first_day": self.days[0] if self.days else None,
            "last_day": self.days[-1] if self.days else None,
        }

    # ----- Elo --------------------------------------------------------------------

    @cached_property
    def _elo(self) -> tuple[list[dict[int, float]], dict[int, tuple[float, float]]]:
        """Elo par équipe, corrigé du déséquilibre naturel entre les camps.

        On estime en continu la probabilité de victoire des gentils (lissage de
        Laplace) et on l'intègre comme avantage de camp : gagner avec le camp
        favori rapporte moins que gagner avec le camp défavorisé.
        """
        ratings: dict[int, float] = defaultdict(lambda: ELO_START)
        peaks: dict[int, float] = defaultdict(lambda: ELO_START)
        kind_wins, total = 1, 2
        history: list[dict[int, float]] = []
        for r in self.records:
            kinds, villains = r.kinds, r.villains
            if kinds and villains:
                p_kind = kind_wins / total
                side_bias = 400 * math.log10(p_kind / (1 - p_kind))
                r_kind = sum(ratings[s.player_id] for s in kinds) / len(kinds)
                r_villain = sum(ratings[s.player_id] for s in villains) / len(villains)
                expected_kind = 1 / (1 + 10 ** ((r_villain - r_kind - side_bias) / 400))
                delta = ELO_K * ((1.0 if r.kind_won else 0.0) - expected_kind)
                for s in kinds:
                    ratings[s.player_id] += delta
                for s in villains:
                    ratings[s.player_id] -= delta
                for s in r.seats:
                    peaks[s.player_id] = max(peaks[s.player_id], ratings[s.player_id])
            kind_wins += r.kind_won
            total += 1
            history.append({s.player_id: ratings[s.player_id] for s in r.seats})
        final = {pid: (ratings[pid], peaks[pid]) for pid in ratings}
        return history, final

    @property
    def elo_final(self) -> dict[int, tuple[float, float]]:
        return self._elo[1]

    # ----- séries temporelles (graphiques) -----------------------------------------

    def timeline(self) -> dict:
        """Données du graphique d'évolution : une valeur par soirée et par joueur."""
        labels = self.days
        index = {d: i for i, d in enumerate(labels)}
        n = len(labels)
        metrics = ("wins", "kind", "villain", "games", "elo", "winrate")
        series = {
            pid: {m: [None] * n for m in metrics} for pid in self.lines
        }  # rempli jour par jour
        totals: dict[int, Counter] = defaultdict(Counter)
        elo_history, _ = self._elo
        by_day: dict[date, list[tuple[GameRecord, dict[int, float]]]] = defaultdict(list)
        for r, elos in zip(self.records, elo_history, strict=True):
            by_day[r.day].append((r, elos))
        last_elo: dict[int, float] = {}
        for d in labels:
            i = index[d]
            for r, elos in by_day[d]:
                for seat in r.seats:
                    if seat.player_id not in series:
                        continue
                    won = r.won(seat)
                    t = totals[seat.player_id]
                    t["games"] += 1
                    t["wins"] += won
                    t["kind" if not seat.is_villain else "villain"] += won
                    last_elo[seat.player_id] = elos[seat.player_id]
            for pid, s in series.items():
                t = totals.get(pid)
                if not t:
                    continue  # pas encore apparu : on laisse None
                s["wins"][i] = t["wins"]
                s["kind"][i] = t["kind"]
                s["villain"][i] = t["villain"]
                s["games"][i] = t["games"]
                s["winrate"][i] = pct(t["wins"], t["games"])
                s["elo"][i] = round(last_elo[pid])
        return {
            "labels": [d.isoformat() for d in labels],
            "players": [
                {"id": pid, "name": self.lines[pid].player.name, "series": s}
                for pid, s in sorted(series.items(), key=lambda kv: self.lines[kv[0]].player.name)
            ],
        }

    def player_timeline(self, player_id: int) -> dict:
        """Évolution d'un joueur partie par partie (Elo et % de victoire cumulé)."""
        elo_history, _ = self._elo
        labels, elo, winrate, results = [], [], [], []
        games = wins = 0
        for r, elos in zip(self.records, elo_history, strict=True):
            seat = r.seat_of(player_id)
            if not seat:
                continue
            games += 1
            wins += r.won(seat)
            labels.append(r.day.isoformat())
            elo.append(round(elos[player_id]))
            winrate.append(pct(wins, games))
            results.append(1 if r.won(seat) else 0)
        return {"labels": labels, "elo": elo, "winrate": winrate, "results": results}

    @cached_property
    def side_by_month(self) -> dict:
        months: dict[tuple[int, int], Counter] = defaultdict(Counter)
        for r in self.records:
            months[(r.day.year, r.day.month)]["kind" if r.kind_won else "villain"] += 1
        keys = sorted(months)
        return {
            "labels": [month_label(y, m, short=True) for y, m in keys],
            "kind": [months[k]["kind"] for k in keys],
            "villain": [months[k]["villain"] for k in keys],
        }

    @cached_property
    def by_table_size(self) -> list[dict]:
        sizes: dict[int, Counter] = defaultdict(Counter)
        for r in self.records:
            sizes[r.size]["games"] += 1
            sizes[r.size]["kind"] += r.kind_won
            sizes[r.size]["villains"] += len(r.villains)
        return [
            {
                "size": size,
                "games": c["games"],
                "kind_pct": pct(c["kind"], c["games"]),
                "villain_pct": pct(c["games"] - c["kind"], c["games"]),
                "avg_villains": round(c["villains"] / c["games"], 1),
            }
            for size, c in sorted(sizes.items())
        ]

    @cached_property
    def by_weekday(self) -> list[dict]:
        days: dict[int, Counter] = defaultdict(Counter)
        for r in self.records:
            days[r.day.weekday()]["games"] += 1
            days[r.day.weekday()]["kind"] += r.kind_won
        return [
            {
                "label": WEEKDAYS_FR[wd],
                "games": days[wd]["games"],
                "kind_pct": pct(days[wd]["kind"], days[wd]["games"]),
            }
            for wd in range(7)
        ]

    # ----- calendrier ---------------------------------------------------------------

    def calendar(self, start: date | None = None, end: date | None = None) -> dict:
        """Grille type GitHub : semaines en colonnes, jours (lun→dim) en lignes."""
        counts = Counter(r.day for r in self.records)
        end = end or (self.days[-1] if self.days else date.today())
        start = start or end - timedelta(days=364)
        start -= timedelta(days=start.weekday())
        peak = max(counts.values(), default=0)
        weeks, months = [], []
        current = start
        while current <= end:
            week = []
            for _ in range(7):
                n = counts.get(current, 0)
                level = 0 if not n else min(4, 1 + int(3 * (n - 1) / max(peak - 1, 1)))
                week.append({"date": current, "count": n, "level": level, "out": current > end})
                current += timedelta(days=1)
            # libellé du mois sur la semaine qui contient le 1er (sauf trop près du précédent)
            first = next((d["date"] for d in week if d["date"].day == 1), None)
            if first is None and not weeks:
                first = week[0]["date"]
            label = ""
            if first and (not months or len(weeks) - months[-1] >= 3):
                months.append(len(weeks))
                label = month_label(first.year, first.month, short=True).split()[0]
            weeks.append({"days": week, "label": label})
        return {"weeks": weeks, "peak": peak, "total_days": len(counts)}

    # ----- paires -------------------------------------------------------------------

    @cached_property
    def pairs(self) -> dict[tuple[int, int], PairLine]:
        pairs: dict[tuple[int, int], PairLine] = {}
        for r in self.records:
            seats = [s for s in r.seats if s.player_id in self.players]
            for s1, s2 in combinations(seats, 2):
                a, b = (s1, s2) if s1.player_id < s2.player_id else (s2, s1)
                key = (a.player_id, b.player_id)
                line = pairs.get(key)
                if line is None:
                    line = pairs[key] = PairLine(
                        a=self.players[a.player_id], b=self.players[b.player_id]
                    )
                line.together += 1
                if a.role == b.role:
                    won = r.won(a)
                    line.same += 1
                    line.same_wins += won
                    if a.is_villain:
                        line.both_villain += 1
                        line.both_villain_wins += won
                    else:
                        line.both_kind += 1
                        line.both_kind_wins += won
                else:
                    line.opposed += 1
                    line.a_wins_opposed += r.won(a)
        return pairs

    def top_pairs(self, metric, min_games: int, games_attr: str = "same", reverse=True, limit=8):
        candidates = [
            p
            for p in self.pairs.values()
            if getattr(p, games_attr) >= min_games and metric(p) is not None
        ]
        return sorted(
            candidates, key=lambda p: (metric(p), getattr(p, games_attr)), reverse=reverse
        )[:limit]

    def rivalries(self, min_games: int, limit: int = 8) -> list[PairLine]:
        """Face-à-face les plus déséquilibrés, orientés vers le dominant."""
        candidates = [p for p in self.pairs.values() if p.opposed >= min_games]
        candidates.sort(key=lambda p: (p.dominance, p.opposed), reverse=True)
        out = []
        for p in candidates[:limit]:
            out.append(p if (p.a_vs_b_pct or 0) >= 50 else p.oriented(p.b.pk))
        return out

    def matrix(self, min_games: int = 1) -> dict:
        """Matrice joueur × joueur : % de victoire en équipe et face-à-face."""
        players = [line.player for line in self.leaderboard(min_games)]
        rows = []
        for p in players:
            cells = []
            for q in players:
                if p.pk == q.pk:
                    cells.append(None)
                    continue
                key = (min(p.pk, q.pk), max(p.pk, q.pk))
                pair = self.pairs.get(key)
                if pair is None:
                    cells.append({"same": None, "n_same": 0, "vs": None, "n_vs": 0})
                    continue
                o = pair.oriented(p.pk)
                cells.append(
                    {
                        "same": o.same_pct,
                        "n_same": o.same,
                        "vs": o.a_vs_b_pct,
                        "n_vs": o.opposed,
                    }
                )
            rows.append({"player": p, "cells": cells})
        return {"players": [{"id": p.pk, "name": p.name} for p in players], "rows": rows}

    def partners_of(self, player_id: int) -> list[PairLine]:
        return sorted(
            (p.oriented(player_id) for (a, b), p in self.pairs.items() if player_id in (a, b)),
            key=lambda p: -p.together,
        )

    # ----- palmarès par période -------------------------------------------------------

    def _summaries(self, granularity, key_fn, label_fn, start_fn) -> list[PeriodSummary]:
        prefix = granularity[0]
        groups: dict = defaultdict(list)
        for r in self.records:
            groups[key_fn(r.day)].append(r)
        out = []
        for key, records in groups.items():
            sub = StatsEngine(records, self.players.values())
            lines = list(sub.lines.values())
            winners = _leaders(lines, lambda line: line.wins)
            if len(winners) > 1:  # départage au % de victoire
                winners = _leaders(winners, lambda line: line.win_pct or 0)
            kind_wins = sum(r.kind_won for r in records)
            out.append(
                PeriodSummary(
                    key=prefix + start_fn(key).isoformat()[: {"d": 10, "m": 7, "y": 4}[prefix]],
                    granularity=granularity,
                    label=label_fn(key),
                    start=start_fn(key),
                    games=len(records),
                    kind_wins=kind_wins,
                    villain_wins=len(records) - kind_wins,
                    players=len(lines),
                    champions=winners,
                    top_villains=_leaders(lines, lambda line: line.villain_wins),
                    top_kinds=_leaders(lines, lambda line: line.kind_wins),
                    mvps=_leaders(lines, lambda line: line.best),
                )
            )
        return sorted(out, key=lambda s: s.start, reverse=True)

    @cached_property
    def by_day(self) -> list[PeriodSummary]:
        return self._summaries(
            "day",
            key_fn=lambda d: d,
            label_fn=lambda d: d.strftime("%d/%m/%Y"),
            start_fn=lambda d: d,
        )

    @cached_property
    def by_month(self) -> list[PeriodSummary]:
        return self._summaries(
            "month",
            key_fn=lambda d: (d.year, d.month),
            label_fn=lambda k: month_label(*k).capitalize(),
            start_fn=lambda k: date(k[0], k[1], 1),
        )

    @cached_property
    def by_year(self) -> list[PeriodSummary]:
        return self._summaries(
            "year",
            key_fn=lambda d: d.year,
            label_fn=str,
            start_fn=lambda y: date(y, 1, 1),
        )

    @cached_property
    def titles(self) -> list[dict]:
        """Nombre de fois où chaque joueur a fini n°1 d'une soirée / d'un mois / d'une année."""
        counts: dict[int, Counter] = defaultdict(Counter)
        for kind, summaries in (
            ("day", self.by_day),
            ("month", self.by_month),
            ("year", self.by_year),
        ):
            for s in summaries:
                for champ in s.champions:
                    counts[champ.player.pk][kind] += 1
                for v in s.top_villains:
                    counts[v.player.pk][f"{kind}_villain"] += 1
                for k in s.top_kinds:
                    counts[k.player.pk][f"{kind}_kind"] += 1
        rows = [{"line": self.lines[pid], **c} for pid, c in counts.items() if pid in self.lines]
        return sorted(
            rows, key=lambda row: (-row.get("year", 0), -row.get("month", 0), -row.get("day", 0))
        )

    # ----- records ----------------------------------------------------------------------

    @cached_property
    def records_board(self) -> list[dict]:
        """Records et faits marquants (liste de cartes prêtes à afficher)."""
        if self.is_empty:
            return []
        lines = list(self.lines.values())
        cards: list[dict] = []

        def add(icon, title, value, unit, who, detail="", tone=""):
            cards.append(
                {"icon": icon, "title": title, "value": value, "unit": unit,
                 "who": who, "detail": detail, "tone": tone}
            )  # fmt: skip

        best = max(lines, key=lambda line: (line.best_streak, line.wins))
        add(
            "🔥",
            "Plus longue série de victoires",
            best.best_streak,
            "victoires d'affilée",
            [best.player],
        )
        worst = max(lines, key=lambda line: (line.worst_streak, line.losses))
        add(
            "🧊",
            "Plus longue série de défaites",
            worst.worst_streak,
            "défaites d'affilée",
            [worst.player],
        )
        villain = max(lines, key=lambda line: (line.villain_run, line.villain_games))
        add("😈", "Méchant en série", villain.villain_run, "parties de suite en méchant",
            [villain.player], tone="villain")  # fmt: skip

        busiest = max(self.by_day, key=lambda s: s.games)
        add("🌙", "Plus grosse soirée", busiest.games, "parties", [],
            detail=busiest.label, tone="link:" + busiest.start.isoformat())  # fmt: skip

        king = max(
            ((s, c) for s in self.by_day for c in s.champions),
            key=lambda sc: (sc[1].wins, sc[1].win_pct or 0),
        )
        add("👑", "Plus de victoires en une soirée", king[1].wins, "victoires",
            [king[1].player], detail=king[0].label)  # fmt: skip

        mvp = max(lines, key=lambda line: (line.best, line.games))
        if mvp.best:
            add("⭐", "Le plus souvent meilleur joueur", mvp.best, "fois MVP", [mvp.player])
        boulet = max(lines, key=lambda line: (line.worst, line.games))
        if boulet.worst:
            add("🫠", "Le plus souvent pire joueur", boulet.worst, "fois", [boulet.player])

        peak = max(lines, key=lambda line: line.elo_peak)
        add("📈", "Record Elo", round(peak.elo_peak), "points au sommet", [peak.player])

        timed = [r for r in self.records if r.duration_minutes]
        if timed:
            longest = max(timed, key=lambda r: r.duration_minutes)
            shortest = min(timed, key=lambda r: r.duration_minutes)
            add("⏳", "Partie la plus longue", round(longest.duration_minutes), "minutes", [],
                detail=f"Partie #{longest.id}", tone=f"game:{longest.id}")  # fmt: skip
            add("⚡", "Partie la plus rapide", round(shortest.duration_minutes), "minutes", [],
                detail=f"Partie #{shortest.id}", tone=f"game:{shortest.id}")  # fmt: skip

        loyal = max(lines, key=lambda line: (len(line.days), line.games))
        add("📅", "Le plus assidu", len(loyal.days), "soirées jouées", [loyal.player])
        return cards

    def superlatives(self, min_games: int) -> list[dict]:
        """Profils marquants : meilleur méchant, gentil le plus fiable, caméléon…"""
        eligible = [
            line
            for line in self.lines.values()
            if line.kind_games >= max(2, min_games // 2)
            and line.villain_games >= max(2, min_games // 2)
        ]
        out = []

        def add(icon, title, line, value, hint):
            out.append({"icon": icon, "title": title, "line": line, "value": value, "hint": hint})

        if v := self.ranked_by(lambda line: line.villain_pct, min_games, limit=1):
            add("🗡️", "Le méchant le plus redoutable", v[0], fmt_pct(v[0].villain_pct),
                f"{v[0].villain_wins}/{v[0].villain_games} en méchant")  # fmt: skip
        if k := self.ranked_by(lambda line: line.kind_pct, min_games, limit=1):
            add("🛡️", "Le gentil le plus fiable", k[0], fmt_pct(k[0].kind_pct),
                f"{k[0].kind_wins}/{k[0].kind_games} en gentil")  # fmt: skip
        if eligible:
            cham = min(eligible, key=lambda line: abs(line.role_gap))
            add("🦎", "Le caméléon", cham, f"±{fmt_num(abs(cham.role_gap))} pts",
                "même niveau dans les deux camps")  # fmt: skip
            spec = max(eligible, key=lambda line: abs(line.role_gap))
            side = "méchant" if spec.role_gap > 0 else "gentil"
            add("🎭", "Le spécialiste", spec, f"+{fmt_num(abs(spec.role_gap))} pts",
                f"bien meilleur en {side}")  # fmt: skip
        if lucky := self.ranked_by(lambda line: line.villain_rate, min_games, limit=1):
            add("🎲", "Abonné au rôle de méchant", lucky[0], fmt_pct(lucky[0].villain_rate),
                "des parties jouées en méchant")  # fmt: skip
        if cat := self.ranked_by(lambda line: line.win_pct, min_games, reverse=False, limit=1):
            add("🐈‍⬛", "Le chat noir", cat[0], fmt_pct(cat[0].win_pct),
                "plus faible taux de victoire")  # fmt: skip
        return out

    # ----- soirée -------------------------------------------------------------------

    def day_summary(self, day: date) -> PeriodSummary | None:
        return next((s for s in self.by_day if s.start == day), None)

    # ----- graphiques joueur ----------------------------------------------------------

    def scatter(self, min_games: int) -> list[dict]:
        """Nuage gentil × méchant : un point par joueur, taille = nombre de victoires."""
        return [
            {
                "id": line.player.pk,
                "name": line.player.name,
                "url": line.player.get_absolute_url(),
                "x": line.kind_pct,
                "y": line.villain_pct,
                "wins": line.wins,
                "games": line.games,
                "win_pct": line.win_pct,
                "kind_games": line.kind_games,
                "villain_games": line.villain_games,
            }
            for line in self.lines.values()
            if line.games >= min_games
            and line.kind_pct is not None
            and line.villain_pct is not None
        ]

    def monthly_results(self, player_id: int) -> dict:
        months: dict[tuple[int, int], Counter] = defaultdict(Counter)
        for r in self.records:
            if seat := r.seat_of(player_id):
                months[(r.day.year, r.day.month)]["win" if r.won(seat) else "loss"] += 1
        keys = sorted(months)
        return {
            "labels": [month_label(y, m, short=True) for y, m in keys],
            "wins": [months[k]["win"] for k in keys],
            "losses": [months[k]["loss"] for k in keys],
        }

    def recent_games(self, player_id: int, limit: int = 12) -> list[tuple[GameRecord, bool, str]]:
        out = []
        for r in reversed(self.records):
            if seat := r.seat_of(player_id):
                out.append((r, r.won(seat), seat))
                if len(out) >= limit:
                    break
        return out
