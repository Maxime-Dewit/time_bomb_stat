from django.db import models


# rôle possible dans une partie
ROLE_CHOICES = (
    ('villain', 'Méchant'),
    ('kind', 'Gentil'),
)

# info possible values for a participation
INFO_CHOICES = (
    ('pire', 'Pire joueur'),
    ('neutre', 'Neutre'),
    ('meilleur', 'Meilleur joueur'),
)

INFO_VALUES = [v[0] for v in INFO_CHOICES]


class Player(models.Model):
    name = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Game(models.Model):
    master = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='mastered_games')
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # store which role won the game (villain/kind)
    winner_role = models.CharField(max_length=20, choices=ROLE_CHOICES, null=True, blank=True)

    def is_active(self):
        return self.started_at and not self.ended_at

    def __str__(self):
        return f"Game {self.id}"


class Participation(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='participations')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='participations')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    info = models.CharField(max_length=20, choices=INFO_CHOICES, default='neutre')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('player', 'game')

    def __str__(self):
        return f"{self.player} in {self.game} ({self.role})"
