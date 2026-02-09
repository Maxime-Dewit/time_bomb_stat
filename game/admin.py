from django.contrib import admin
from .models import Player, Game, Participation


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'master', 'started_at', 'ended_at')


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ('player', 'game', 'role', 'created_at')
