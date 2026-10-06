"""Filtre de période partagé par toutes les pages de statistiques.

Un seul paramètre GET `p` :
    all            toutes les parties (défaut)
    last           la dernière soirée jouée
    30d            les 30 derniers jours
    y2026          une année
    m2026-10       un mois
    d2026-10-05    une soirée précise
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils.formats import date_format

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip


MONTHS_FR_SHORT = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]  # fmt: skip


def month_label(year: int, month: int, short: bool = False) -> str:
    name = (MONTHS_FR_SHORT if short else MONTHS_FR)[month - 1]
    return f"{name} {year}"


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: date | None = None
    end: date | None = None

    @property
    def is_all(self) -> bool:
        return self.key == "all"

    @property
    def is_day(self) -> bool:
        return self.key.startswith("d") or self.key == "last"

    @classmethod
    def all(cls) -> Period:
        return cls("all", "Depuis le début")

    @classmethod
    def year(cls, year: int) -> Period:
        return cls(f"y{year}", f"Année {year}", date(year, 1, 1), date(year, 12, 31))

    @classmethod
    def month(cls, year: int, month: int) -> Period:
        last = calendar.monthrange(year, month)[1]
        return cls(
            f"m{year}-{month:02d}",
            month_label(year, month).capitalize(),
            date(year, month, 1),
            date(year, month, last),
        )

    @classmethod
    def day(cls, day: date) -> Period:
        return cls(f"d{day.isoformat()}", f"Soirée du {date_format(day, 'l j F Y')}", day, day)

    @classmethod
    def parse(cls, raw: str | None, today: date, last_day: date | None) -> Period:
        raw = (raw or "all").strip()
        try:
            if raw == "last" and last_day:
                return cls.day(last_day)
            if raw == "30d":
                return cls("30d", "30 derniers jours", today - timedelta(days=29), today)
            if m := re.fullmatch(r"y(\d{4})", raw):
                return cls.year(int(m[1]))
            if m := re.fullmatch(r"m(\d{4})-(\d{2})", raw):
                return cls.month(int(m[1]), int(m[2]))
            if m := re.fullmatch(r"d(\d{4}-\d{2}-\d{2})", raw):
                return cls.day(date.fromisoformat(m[1]))
        except ValueError:
            pass
        return cls.all()
