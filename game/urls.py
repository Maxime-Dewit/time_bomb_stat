from django.urls import path

from .views import games, players, stats

app_name = "game"

urlpatterns = [
    path("", games.home, name="home"),
    # Parties
    path("parties/", games.game_list, name="game_list"),
    path("parties/nouvelle/", games.game_create, name="game_create"),
    path("parties/<int:pk>/", games.game_detail, name="game_detail"),
    path("parties/<int:pk>/gerer/", games.game_manage, name="game_manage"),
    path("parties/<int:pk>/joueurs/", games.game_add_players, name="game_add_players"),
    path(
        "parties/<int:pk>/joueurs/<int:player_pk>/retirer/",
        games.game_remove_player,
        name="game_remove_player",
    ),
    path("parties/<int:pk>/revanche/", games.game_rematch, name="game_rematch"),
    path("parties/<int:pk>/supprimer/", games.game_delete, name="game_delete"),
    # Joueurs
    path("joueurs/", players.player_list, name="player_list"),
    path("joueurs/nouveau/", players.player_create, name="player_create"),
    path("joueurs/<int:pk>/", players.player_detail, name="player_detail"),
    path("joueurs/<int:pk>/supprimer/", players.player_delete, name="player_delete"),
    # Statistiques
    path("stats/", stats.overview, name="stats"),
    path("stats/evolution/", stats.evolution, name="stats_evolution"),
    path("stats/duos/", stats.duos, name="stats_duos"),
    path("stats/records/", stats.records, name="stats_records"),
    path("stats/soirees/", stats.sessions, name="stats_sessions"),
    path("stats/soirees/<str:day>/", stats.session_detail, name="stats_session"),
]
