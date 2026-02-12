from django.urls import path
from . import views

app_name = 'game'

urlpatterns = [
    path('', views.index, name='index'),
    path('create_player/', views.create_player, name='create_player'),
    path('create_game/', views.create_game, name='create_game'),
    path('start_game/<int:game_id>/', views.start_game, name='start_game'),
    path('end_game/<int:game_id>/', views.end_game, name='end_game'),
    path('join_game/<int:game_id>/', views.join_game, name='join_game'),
    path('submit_info/<int:game_id>/', views.submit_info, name='submit_info'),
    path('stats/', views.stats, name='stats'),
    path('player/<int:player_id>/', views.player_detail, name='player_detail'),
    path('delete_game/<int:game_id>/', views.delete_game, name='delete_game'),
    path('delete_player/<int:player_id>/', views.delete_player, name='delete_player'),
    path('players/', views.players_list, name='players_list'),
    path('edit_game/<int:game_id>/', views.edit_game, name='edit_game'),
    path('game/<int:game_id>/', views.game_detail, name='game_detail'),
    path('manage/<int:game_id>/', views.manage_game, name='manage_game'),
    path('rematch/<int:game_id>/', views.rematch, name='rematch'),
    path('remove_participation/<int:game_id>/<int:player_id>/', views.remove_participation, name='remove_participation'),
]
