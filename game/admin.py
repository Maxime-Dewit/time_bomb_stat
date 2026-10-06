from django.contrib import admin

from .models import Game, Participation, Player


class ParticipationInline(admin.TabularInline):
    model = Participation
    extra = 0
    autocomplete_fields = ["player"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ["id", "started_at", "ended_at", "winner_role", "master"]
    list_filter = ["winner_role", "started_at"]
    date_hierarchy = "started_at"
    inlines = [ParticipationInline]


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ["player", "game", "role", "info"]
    list_filter = ["role", "info"]
    search_fields = ["player__name"]
