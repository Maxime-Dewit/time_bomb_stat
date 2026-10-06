"""Chargement des parties terminées sous une forme légère, indépendante de l'ORM.

Le moteur de statistiques ne manipule que ces objets immuables : il est donc
facile à tester et ne fait aucune requête SQL supplémentaire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from game.models import Award, Game, Role

# Au-delà, on considère que la partie a été oubliée ouverte : durée ignorée.
MAX_PLAUSIBLE_MINUTES = 180


def session_day(moment: datetime) -> date:
    """Jour de la « soirée » d'une partie (une partie à 1h compte pour la veille)."""
    local = timezone.localtime(moment)
    return (local - timedelta(hours=settings.TIMEBOMB_DAY_CUTOFF_HOUR)).date()


@dataclass(frozen=True, slots=True)
class Seat:
    player_id: int
    role: str
    award: str

    @property
    def is_villain(self) -> bool:
        return self.role == Role.VILLAIN

    @property
    def is_best(self) -> bool:
        return self.award == Award.BEST

    @property
    def is_worst(self) -> bool:
        return self.award == Award.WORST


@dataclass(frozen=True, slots=True)
class GameRecord:
    id: int
    started_at: datetime
    ended_at: datetime | None
    winner: str
    day: date
    seats: tuple[Seat, ...]

    def won(self, seat: Seat) -> bool:
        return seat.role == self.winner

    def seat_of(self, player_id: int) -> Seat | None:
        return next((s for s in self.seats if s.player_id == player_id), None)

    @property
    def size(self) -> int:
        return len(self.seats)

    @property
    def kind_won(self) -> bool:
        return self.winner == Role.KIND

    @property
    def villains(self) -> tuple[Seat, ...]:
        return tuple(s for s in self.seats if s.role == Role.VILLAIN)

    @property
    def kinds(self) -> tuple[Seat, ...]:
        return tuple(s for s in self.seats if s.role == Role.KIND)

    @property
    def duration_minutes(self) -> float | None:
        if not self.ended_at:
            return None
        minutes = (self.ended_at - self.started_at).total_seconds() / 60
        return minutes if 0 < minutes <= MAX_PLAUSIBLE_MINUTES else None


def to_record(game: Game) -> GameRecord:
    seats = tuple(
        Seat(player_id=p.player_id, role=p.role, award=p.info)
        for p in sorted(game.participations.all(), key=lambda p: p.player_id)
    )
    return GameRecord(
        id=game.pk,
        started_at=game.started_at,
        ended_at=game.ended_at,
        winner=game.winner_role,
        day=session_day(game.started_at),
        seats=seats,
    )


def load_records(start: date | None = None, end: date | None = None) -> list[GameRecord]:
    """Parties terminées (ordre chronologique), filtrées par jour de soirée inclusif."""
    qs = Game.objects.finished().prefetch_related("participations").order_by("started_at", "id")
    # Pré-filtre SQL large (marge d'un jour pour l'heure de bascule), filtre exact ensuite.
    if start:
        qs = qs.filter(started_at__date__gte=start - timedelta(days=1))
    if end:
        qs = qs.filter(started_at__date__lte=end + timedelta(days=1))
    records = [to_record(g) for g in qs]
    return [
        r
        for r in records
        if r.seats and (start is None or r.day >= start) and (end is None or r.day <= end)
    ]
