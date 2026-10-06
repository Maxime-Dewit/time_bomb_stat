"""Statistiques Time Bomb : chargement des parties, périodes et moteur de calcul."""

from game.models import Player

from .engine import PairLine, PeriodSummary, PlayerLine, StatsEngine
from .periods import Period
from .records import GameRecord, Seat, load_records, session_day


def build_engine(period: Period | None = None) -> StatsEngine:
    period = period or Period.all()
    return StatsEngine(load_records(period.start, period.end), Player.objects.all())


__all__ = [
    "GameRecord",
    "PairLine",
    "Period",
    "PeriodSummary",
    "PlayerLine",
    "Seat",
    "StatsEngine",
    "build_engine",
    "load_records",
    "session_day",
]
