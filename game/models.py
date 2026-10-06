import zlib
from datetime import timedelta

from django.db import models
from django.urls import reverse


class Role(models.TextChoices):
    KIND = "kind", "Gentil"
    VILLAIN = "villain", "Méchant"


class Award(models.TextChoices):
    WORST = "pire", "Pire joueur"
    NEUTRAL = "neutre", "Neutre"
    BEST = "meilleur", "Meilleur joueur"


class Player(models.Model):
    name = models.CharField("nom", max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "joueur"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("game:player_detail", args=[self.pk])

    @property
    def initials(self) -> str:
        parts = self.name.split()
        letters = "".join(p[0] for p in parts[:2]) if len(parts) > 1 else self.name[:2]
        return letters.upper()

    @property
    def hue(self) -> int:
        """Teinte stable dérivée du nom, pour l'avatar."""
        return round(zlib.crc32(self.name.encode()) * 137.508) % 360


class GameQuerySet(models.QuerySet):
    def finished(self):
        """Parties terminées avec un camp gagnant : les seules prises en compte dans les stats."""
        return self.filter(
            ended_at__isnull=False, winner_role__isnull=False, started_at__isnull=False
        )

    def in_progress(self):
        return self.filter(ended_at__isnull=True)


class Game(models.Model):
    master = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mastered_games",
        verbose_name="maître du jeu",
    )
    started_at = models.DateTimeField("début", null=True, blank=True)
    ended_at = models.DateTimeField("fin", null=True, blank=True)
    # NULL = partie pas encore terminée (conservé tel quel pour les données existantes).
    winner_role = models.CharField(  # noqa: DJ001
        "camp gagnant", max_length=20, choices=Role.choices, null=True, blank=True
    )

    objects = GameQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "partie"
        indexes = [models.Index(fields=["started_at"], name="game_started_idx")]

    def __str__(self) -> str:
        return f"Partie #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("game:game_detail", args=[self.pk])

    @property
    def is_finished(self) -> bool:
        return bool(self.ended_at and self.winner_role)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration(self) -> timedelta | None:
        if self.started_at and self.ended_at and self.ended_at > self.started_at:
            return self.ended_at - self.started_at
        return None


class Participation(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="participations")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="participations")
    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.KIND)
    info = models.CharField(
        "distinction", max_length=20, choices=Award.choices, default=Award.NEUTRAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["player__name"]
        constraints = [
            models.UniqueConstraint(fields=["player", "game"], name="unique_player_per_game"),
        ]

    def __str__(self) -> str:
        return f"{self.player} — {self.game} ({self.get_role_display()})"

    @property
    def is_winner(self) -> bool:
        return bool(self.game.winner_role) and self.role == self.game.winner_role
