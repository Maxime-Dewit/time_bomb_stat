from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q, F
from .models import Player, Game, Participation


def index(request):
    active_game = Game.objects.filter(started_at__isnull=False, ended_at__isnull=True).first()
    games = list(Game.objects.order_by('-id')[:10])
    players = Player.objects.order_by('name')

    # attach available players (not yet in the game) to each game object
    for g in games:
        g.available_players = Player.objects.exclude(participations__game=g).order_by('name')

    # also attach available players to the active game (if any)
    if active_game:
        active_game.available_players = Player.objects.exclude(participations__game=active_game).order_by('name')

    return render(request, 'index.html', {
        'active_game': active_game,
        'games': games,
        'players': players,
    })


def create_player(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Player.objects.get_or_create(name=name.strip())
    return redirect('game:index')


def create_game(request):
    if request.method == 'POST':
        master_name = request.POST.get('master')
        master = None
        if master_name:
            master, _ = Player.objects.get_or_create(name=master_name.strip())
        Game.objects.create(master=master)
    return redirect('game:index')


def start_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game.started_at = timezone.now()
    game.ended_at = None
    game.save()
    return redirect('game:index')


def end_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game.ended_at = timezone.now()
    # optional: set winner role if posted
    winner_role = request.POST.get('winner_role')
    if winner_role:
        game.winner_role = winner_role
    game.save()
    return redirect('game:index')


def join_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    # refuse normal joins if the game has ended; allow only via edit mode (hidden 'edit' flag)
    if request.method == 'POST':
        if game.ended_at and request.POST.get('edit') != '1':
            return redirect('game:index')
        player_name = request.POST.get('player')
        role = request.POST.get('role')
        info = request.POST.get('info', '')
        if player_name and role:
            player, _ = Player.objects.get_or_create(name=player_name.strip())
            Participation.objects.update_or_create(player=player, game=game, defaults={'role': role, 'info': info})
    return redirect('game:index')


def submit_info(request, game_id):
    return join_game(request, game_id)


def delete_game(request, game_id):
    if request.method == 'POST':
        game = get_object_or_404(Game, pk=game_id)
        game.delete()
    return redirect('game:index')


def delete_player(request, player_id):
    if request.method == 'POST':
        player = get_object_or_404(Player, pk=player_id)
        player.delete()
    return redirect('game:index')


def stats(request):
    # wins per player: a player wins a game when their participation.role equals the game's winner_role
    wins = Player.objects.annotate(
        wins_count=Count('participations', filter=Q(participations__game__winner_role=F('participations__role')))
    ).order_by('-wins_count')

    # role counts
    role_counts = Player.objects.annotate(
        villains=Count('participations', filter=Q(participations__role='villain')),
        kinds=Count('participations', filter=Q(participations__role='kind')),
    ).order_by('-villains')

    # top pairs: count of games where both players participated
    from django.db import connection
    pairs = []
    with connection.cursor() as cursor:
        # count games together and wins per player when together (win if participation.role == game.winner_role)
        cursor.execute('''
            SELECT p1.player_id as a, p2.player_id as b,
                   COUNT(DISTINCT p1.game_id) as cnt,
                   SUM(CASE WHEN g.winner_role = p1.role THEN 1 ELSE 0 END) as wins_a,
                   SUM(CASE WHEN g.winner_role = p2.role THEN 1 ELSE 0 END) as wins_b
            FROM game_participation p1
            JOIN game_participation p2 ON p1.game_id = p2.game_id AND p1.player_id < p2.player_id
            LEFT JOIN game_game g ON g.id = p1.game_id
            GROUP BY a, b
            ORDER BY cnt DESC
            LIMIT 20
        ''')
        for a, b, cnt, wins_a, wins_b in cursor.fetchall():
            pa = Player.objects.filter(pk=a).first()
            pb = Player.objects.filter(pk=b).first()
            pairs.append({
                'a': pa,
                'b': pb,
                'count': cnt,
                'wins_a': wins_a or 0,
                'wins_b': wins_b or 0,
            })

    return render(request, 'stats.html', {
        'wins': wins,
        'role_counts': role_counts,
        'pairs': pairs,
    })


def players_list(request):
    # list players as clickable cards with their total number of participations
    players = Player.objects.annotate(total=Count('participations')).order_by('-total', 'name')
    return render(request, 'players.html', {
        'players': players,
    })


def edit_game(request, game_id):
    # allow adding/removing participants even after a game ended
    game = get_object_or_404(Game, pk=game_id)
    # players not in this game
    available = Player.objects.exclude(participations__game=game).order_by('name')
    if request.method == 'POST':
        # reuse join logic but force edit mode
        player_name = request.POST.get('player')
        role = request.POST.get('role')
        info = request.POST.get('info', '')
        if player_name and role:
            player, _ = Player.objects.get_or_create(name=player_name.strip())
            Participation.objects.update_or_create(player=player, game=game, defaults={'role': role, 'info': info})
            return redirect('game:edit_game', game_id=game.id)
    return render(request, 'edit_game.html', {
        'game': game,
        'available': available,
    })


def game_detail(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    participants = game.participations.select_related('player').all()
    # determine for each participation whether that player is considered a winner in this game
    # a participation 'wins' when its role == game.winner_role
    p_list = []
    for p in participants:
        is_winner = False
        if game.winner_role and p.role == game.winner_role:
            is_winner = True
        p_list.append({
            'player': p.player,
            'role': p.get_role_display(),
            'info': p.info,
            'is_winner': is_winner,
        })

    return render(request, 'game_detail.html', {
        'game': game,
        'participants': p_list,
    })


def player_detail(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    # total participations (games played)
    from django.db.models import F
    total_games = player.participations.count()
    # wins: count participations where the participation.role equals the game's winner_role
    wins_count = Participation.objects.filter(player=player).filter(role=F('game__winner_role')).count()
    villains = player.participations.filter(role='villain').count()
    kinds = player.participations.filter(role='kind').count()
    losses = total_games - wins_count
    win_pct = (wins_count / total_games * 100) if total_games > 0 else 0
    # partners: who played with this player, counts and wins when together
    from django.db import connection
    partners = []
    with connection.cursor() as cursor:
        # First get top partners by number of games together
        cursor.execute('''
            SELECT CASE WHEN p1.player_id = %s THEN p2.player_id ELSE p1.player_id END as partner_id,
                   COUNT(DISTINCT p1.game_id) as cnt
            FROM game_participation p1
            JOIN game_participation p2 ON p1.game_id = p2.game_id AND p1.player_id < p2.player_id
            WHERE p1.player_id = %s OR p2.player_id = %s
            GROUP BY partner_id
            ORDER BY cnt DESC
            LIMIT 20
        ''', [player.id, player.id, player.id])
        rows = cursor.fetchall()
        for partner_id, cnt in rows:
            part = Player.objects.filter(pk=partner_id).first()
            # compute wins by role when together and how many times the given player won when together
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN ((p1.player_id = %s AND g.winner_role = p1.role) OR (p2.player_id = %s AND g.winner_role = p2.role)) THEN 1 ELSE 0 END) as wins_player,
                    SUM(CASE WHEN ((p1.player_id = %s AND g.winner_role = p1.role) OR (p2.player_id = %s AND g.winner_role = p2.role)) THEN 1 ELSE 0 END) as wins_partner,
                    SUM(CASE WHEN g.winner_role = 'villain' THEN 1 ELSE 0 END) as wins_villain,
                    SUM(CASE WHEN g.winner_role = 'kind' THEN 1 ELSE 0 END) as wins_kind,
                    SUM(CASE WHEN p1.role = 'villain' AND p2.role = 'villain' THEN 1 ELSE 0 END) as together_villain,
                    SUM(CASE WHEN p1.role = 'kind' AND p2.role = 'kind' THEN 1 ELSE 0 END) as together_kind,
                    SUM(CASE WHEN p1.role = 'villain' AND p2.role = 'villain' AND g.winner_role = 'villain' THEN 1 ELSE 0 END) as wins_both_villain,
                    SUM(CASE WHEN p1.role = 'kind' AND p2.role = 'kind' AND g.winner_role = 'kind' THEN 1 ELSE 0 END) as wins_both_kind
                FROM game_participation p1
                JOIN game_participation p2 ON p1.game_id = p2.game_id AND p1.player_id < p2.player_id
                LEFT JOIN game_game g ON g.id = p1.game_id
                WHERE (p1.player_id = %s AND p2.player_id = %s) OR (p1.player_id = %s AND p2.player_id = %s)
            ''', [player.id, player.id, partner_id, partner_id, player.id, partner_id, partner_id, player.id])
            wp, wpartner, wv, wk, tv, tk, wbv, wbk = cursor.fetchone()
            partners.append({
                'player': part,
                'count': cnt,
                'wins_villain': wv or 0,
                'wins_kind': wk or 0,
                'wins_player': wp or 0,
                'wins_partner': wpartner or 0,
                'together_villain': tv or 0,
                'together_kind': tk or 0,
                'wins_both_villain': wbv or 0,
                'wins_both_kind': wbk or 0,
                'losses_both_villain': (tv or 0) - (wbv or 0),
                'losses_both_kind': (tk or 0) - (wbk or 0),
            })
            # compute win percentage vs this partner
            try:
                wins = int(wp or 0)
                total = int(cnt or 0)
                losses_with_partner = total - wins
                win_pct_partner = round((wins / total * 100), 1) if total > 0 else 0
            except Exception:
                wins = wp or 0
                total = cnt or 0
                losses_with_partner = (total or 0) - (wins or 0)
                win_pct_partner = 0
            partners[-1]['win_pct'] = win_pct_partner
            partners[-1]['losses_with_partner'] = losses_with_partner
    return render(request, 'player_detail.html', {
        'player': player,
        'total_games': total_games,
        'wins': wins_count,
        'villains': villains,
        'kinds': kinds,
        'losses': losses,
        'win_pct': round(win_pct, 1),
        'partners': partners,
    })
