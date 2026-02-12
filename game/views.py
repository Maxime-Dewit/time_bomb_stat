from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Q, F
import logging
from .models import Player, Game, Participation, INFO_VALUES

logger = logging.getLogger(__name__)


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
    # Redirect back to the referring page if available (keeps user on manage/edit pages)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('game:index')


def create_game(request):
    if request.method == 'POST':
        master_name = request.POST.get('master')
        master = None
        if master_name:
            master, _ = Player.objects.get_or_create(name=master_name.strip())
        game = Game.objects.create(master=master)
        return start_game(request, game.id) # start immediately
    return redirect('game:index')


def start_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game.started_at = timezone.now()
    game.ended_at = None
    game.save()
    return redirect('game:manage_game', game_id=game.id)


def end_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    game.ended_at = timezone.now()
    # optional: set winner role if posted
    winner_role = request.POST.get('winner_role')
    if winner_role:
        game.winner_role = winner_role

    # If roles/infos for participants were posted (from manage page), update them now
    try:
        for p in game.participations.select_related('player').all():
            # role: checkbox 'villain_<player_id>' means villain when present
            role_field = request.POST.get(f'villain_{p.player.id}')
            role = 'villain' if role_field == 'on' or role_field == '1' else 'kind'
            info = request.POST.get(f'info_{p.player.id}')
            if info not in INFO_VALUES:
                info = p.info
            p.role = role
            p.info = info
            p.save()
    except Exception:
        # ignore if no role fields posted
        pass

    game.save()
    return redirect('game:manage_game', game_id=game.id)


def join_game(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    # refuse normal joins if the game has ended; allow only via edit mode (hidden 'edit' flag)
    if request.method == 'POST':
        if game.ended_at and request.POST.get('edit') != '1':
            return redirect('game:index')
        player_name = request.POST.get('player')
        role = request.POST.get('role')
        info = request.POST.get('info', 'neutre')
        if info not in INFO_VALUES:
            info = 'neutre'
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

    # role counts: separate querysets so we can sort each list independently
    role_counts_villains = Player.objects.annotate(
        villains=Count('participations', filter=Q(participations__role='villain')),
        kinds=Count('participations', filter=Q(participations__role='kind')),
    ).order_by('-villains')

    role_counts_kinds = Player.objects.annotate(
        villains=Count('participations', filter=Q(participations__role='villain')),
        kinds=Count('participations', filter=Q(participations__role='kind')),
    ).order_by('-kinds')

    # top pairs: count of games where both players participated
    # keep the raw pairs query for compatibility (top frequent pairs)
    from django.db import connection
    pairs = []
    with connection.cursor() as cursor:
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

    # Build cross-tab matrices: for each ordered pair (row player, col player) compute
    # percentage of games together that were won by 'kind' and by 'villain'.
    players = list(Player.objects.order_by('name'))
    player_ids = [p.id for p in players]
    for k in players :
        print(f'DEBUG stats: player {k.name} id={k.id}')
    # precompute game ids per player to speed up intersections
    game_ids_by_player = {p.id: set(Participation.objects.filter(player=p).values_list('game_id', flat=True)) for p in players}

    kind_matrix = {pid: {} for pid in player_ids}
    villain_matrix = {pid: {} for pid in player_ids}
    total_matrix = {pid: {} for pid in player_ids}

    for pid in player_ids:
        ids_a = game_ids_by_player.get(pid, set())
        for qid in player_ids:
            if pid == qid:
                kind_matrix[pid][qid] = None
                villain_matrix[pid][qid] = None
                total_matrix[pid][qid] = 0
                continue
            ids_b = game_ids_by_player.get(qid, set())
            common = ids_a.intersection(ids_b)
            total = len(common)
            total_matrix[pid][qid] = total
            if total == 0:
                kind_matrix[pid][qid] = None
                villain_matrix[pid][qid] = None
                continue
            # count wins where winner_role == 'kind' among common games
            together_villain = Game.objects.filter(id__in=common, participations__player_id=pid, participations__role='villain')\
                    .filter(participations__player_id=qid, participations__role='villain')\
                    .distinct().count()

            together_kind = Game.objects.filter(id__in=common, participations__player_id=pid, participations__role='kind')\
                  .filter(participations__player_id=qid, participations__role='kind')\
                  .distinct().count()
            kinds_wins = Game.objects.filter(id__in=common, participations__player_id=pid, participations__role='kind')\
                    .filter(participations__player_id=qid, participations__role='kind', winner_role='kind')\
                    .distinct().count()
            
            villains_wins = Game.objects.filter(id__in=common, participations__player_id=pid, participations__role='villain')\
                    .filter(participations__player_id=qid, participations__role='villain', winner_role='villain')\
                    .distinct().count()
            kind_pct = round(kinds_wins / together_kind * 100, 1) if together_kind > 0 else None
            villain_pct = round(villains_wins / together_villain * 100, 1) if together_villain > 0 else None
            kind_matrix[pid][qid] = kind_pct
            villain_matrix[pid][qid] = villain_pct

    # determine per-row max/min for highlighting (ignore None)
    row_max_kind = {}
    row_min_kind = {}
    row_max_villain = {}
    row_min_villain = {}
    for pid in player_ids:
        row = kind_matrix[pid]
        vals = [(qid, v) for qid, v in row.items() if v is not None]
        if vals:
            # support multiple equal best/worst values: collect all qids with max/min value
            max_val = max(v for _, v in vals)
            min_val = min(v for _, v in vals)
            best_ids = [qid for qid, v in vals if v == max_val]
            worst_ids = [qid for qid, v in vals if v == min_val]
            row_max_kind[pid] = best_ids
            row_min_kind[pid] = worst_ids
        else:
            row_max_kind[pid] = None
            row_min_kind[pid] = None
        rowv = villain_matrix[pid]
        valsv = [(qid, v) for qid, v in rowv.items() if v is not None]
        if valsv:
            max_valv = max(v for _, v in valsv)
            min_valv = min(v for _, v in valsv)
            bestv_ids = [qid for qid, v in valsv if v == max_valv]
            worstv_ids = [qid for qid, v in valsv if v == min_valv]
            row_max_villain[pid] = bestv_ids
            row_min_villain[pid] = worstv_ids
        else:
            row_max_villain[pid] = None
            row_min_villain[pid] = None

    # additional aggregations used by the template
    most_played = Player.objects.annotate(total=Count('participations')).order_by('-total')[:20]

    win_counts_villains = Player.objects.annotate(
        villain_wins=Count('participations', filter=Q(participations__role='villain', participations__game__winner_role='villain'))
    ).order_by('-villain_wins')[:20]
    win_counts_kinds = Player.objects.annotate(
        kind_wins=Count('participations', filter=Q(participations__role='kind', participations__game__winner_role='kind'))
    ).order_by('-kind_wins')[:20]

    info_counts_pire = Player.objects.annotate(pire_count=Count('participations', filter=Q(participations__info='pire'))).order_by('-pire_count')[:20]
    info_counts_meilleur = Player.objects.annotate(meilleur_count=Count('participations', filter=Q(participations__info='meilleur'))).order_by('-meilleur_count')[:20]

    return render(request, 'stats.html', {
        'wins': wins,
        'role_counts_villains': role_counts_villains,
        'role_counts_kinds': role_counts_kinds,
        'pairs': pairs,
        'players_cross': players,
        'kind_matrix': kind_matrix,
        'villain_matrix': villain_matrix,
        'total_matrix': total_matrix,
        'row_max_kind': row_max_kind,
        'row_min_kind': row_min_kind,
        'row_max_villain': row_max_villain,
        'row_min_villain': row_min_villain,
        'most_played': most_played,
        'win_counts_villains': win_counts_villains,
        'win_counts_kinds': win_counts_kinds,
        'info_counts_pire': info_counts_pire,
        'info_counts_meilleur': info_counts_meilleur,
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
    available = Player.objects.exclude(participations__game=game).annotate(total=Count('participations')).order_by('-total', 'name')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'select_players' or action == 'add':
            # add participant (same as join in edit mode)
            player_name = request.POST.get('player')
            role = request.POST.get('role')
            info = request.POST.get('info', 'neutre')
            if info not in INFO_VALUES:
                info = 'neutre'
            if player_name and role:
                player, _ = Player.objects.get_or_create(name=player_name.strip())
                Participation.objects.update_or_create(player=player, game=game, defaults={'role': role, 'info': info})
            return redirect('game:edit_game', game_id=game.id)
        elif action == 'set_roles':
            # update role/info for each participation and optionally winner_role
            for p in game.participations.select_related('player').all():
                role_field = request.POST.get(f'villain_{p.player.id}')
                role = 'villain' if role_field == 'on' or role_field == '1' else 'kind'
                info = request.POST.get(f'info_{p.player.id}', '')
                if info not in INFO_VALUES:
                    info = p.info
                p.role = role
                p.info = info
                p.save()
            winner_role = request.POST.get('winner_role')
            if winner_role:
                game.winner_role = winner_role
                game.save()
            return redirect('game:edit_game', game_id=game.id)
        elif action == 'remove_participation':
            # remove participation (edit mode allowed even if game ended)
            player_id = request.POST.get('player_id')
            if player_id:
                Participation.objects.filter(game=game, player_id=player_id).delete()
            return redirect('game:edit_game', game_id=game.id)

    participants = game.participations.select_related('player').annotate(player_games=Count('player__participations')).order_by('-player_games', 'player__name')
    return render(request, 'edit_game.html', {
        'game': game,
        'available': available,
        'participants': participants,
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
            'info': p.get_info_display(),
            'is_winner': is_winner,
        })

    return render(request, 'game_detail.html', {
        'game': game,
        'participants': p_list,
    })


def manage_game(request, game_id):
    """Page de gestion d'une partie en cours/créée —
    Deux phases :
    - sélectionner les joueurs disponibles (action=select_players)
    - définir rôle/info pour chaque participant (action=set_roles)
    """
    game = get_object_or_404(Game, pk=game_id)

    # Handle POST actions from the manage page
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'select_players':
            # multiple checkbox values 'player_id' or names
            selected = request.POST.getlist('player')
            for name in selected:
                if not name:
                    continue
                player, _ = Player.objects.get_or_create(name=name.strip())
                # default role = 'kind'
                Participation.objects.get_or_create(player=player, game=game, defaults={'role': 'kind'})
            return redirect('game:manage_game', game_id=game.id)
        elif action == 'set_roles':
            # update role/info for each participation
            for p in game.participations.select_related('player').all():
                # role checkbox: if 'villain_{player_id}' present -> villain else kind
                role_field = request.POST.get(f'villain_{p.player.id}')
                role = 'villain' if role_field == 'on' or role_field == '1' else 'kind'
                info = request.POST.get(f'info_{p.player.id}', '')
                if info not in INFO_VALUES:
                    info = p.info
                p.role = role
                p.info = info
                p.save()
            return redirect('game:manage_game', game_id=game.id)

    # GET: render page with available players and current participants
    available = Player.objects.exclude(participations__game=game).annotate(total=Count('participations')).order_by('-total', 'name')
    participants = game.participations.select_related('player').all()
    return render(request, 'manage_game.html', {
        'game': game,
        'available': available,
        'participants': participants,
    })


def rematch(request, game_id):
    """Create a new game pre-filled with the same participants as <game_id> and redirect to manage page."""
    if request.method != 'POST':
        return redirect('game:index')
    old = get_object_or_404(Game, pk=game_id)
    # create new game with same master
    new_game = Game.objects.create(master=old.master)
    # copy participations
    for p in old.participations.all():
        Participation.objects.create(player=p.player, game=new_game, role=p.role, info=p.info)
    return start_game(request, new_game.id)


def remove_participation(request, game_id, player_id):
    """Remove a Participation (player from game). Accepts POST (AJAX or form).
    Only allowed when the game has not ended from the manage page context.
    """
    game = get_object_or_404(Game, pk=game_id)
    if request.method == 'POST':
        # allow removal in edit mode even if game ended when caller includes edit=1
        if game.ended_at and request.POST.get('edit') != '1':
            if request.is_ajax():
                return JsonResponse({'status': 'error', 'message': 'Game already ended'}, status=400)
            return redirect('game:manage_game', game_id=game.id)

        Participation.objects.filter(game=game, player_id=player_id).delete()
        if request.is_ajax():
            return JsonResponse({'status': 'ok'})
    return redirect('game:manage_game', game_id=game.id)

def player_detail(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    # total participations (games played)
    from django.db.models import F
    total_games = player.participations.count()
    # wins: count participations where the participation.role equals the game's winner_role
    wins_count = Participation.objects.filter(player=player).filter(role=F('game__winner_role')).count()
    cnt_villains = player.participations.filter(role='villain').count()
    cnt_kinds = player.participations.filter(role='kind').count()
    pct_games_villain = round((cnt_villains / total_games * 100),1) if total_games > 0 else 0
    pct_games_kind = round((cnt_kinds / total_games * 100),1) if total_games > 0 else 0
    losses = total_games - wins_count
    win_pct = (wins_count / total_games * 100) if total_games > 0 else 0
    wins_villain = player.participations.filter(role='villain', game__winner_role='villain').count()
    wins_kind = player.participations.filter(role='kind', game__winner_role='kind').count()
    losses_villain = player.participations.filter(role='villain', game__winner_role='kind').count()
    losses_kind = player.participations.filter(role='kind', game__winner_role='villain').count()
    pct_wins_villain = round((wins_villain / cnt_villains * 100),1) if cnt_villains > 0 else 0
    pct_wins_kind = round((wins_kind / cnt_kinds * 100),1) if cnt_kinds > 0 else 0
    # partners: who played with this player, counts and wins when together
    partners = []
    # get game ids the player participated in
    game_ids = list(Participation.objects.filter(player=player).values_list('game_id', flat=True))
    logger.debug('player_detail: player=%s total_games=%s', player.id, len(game_ids))
    print(f'DEBUG player_detail: player={player.id} total_games={len(game_ids)}')
    # top partners by distinct games together using ORM
    partner_rows_qs = (Participation.objects
                    .filter(game_id__in=game_ids)
                    .exclude(player=player)
                    .values('player')
                    .annotate(cnt=Count('game_id', distinct=True))
                    .order_by('-cnt')[:20])

    partner_rows = list(partner_rows_qs)
    logger.debug('player_detail: found %s partner rows', len(partner_rows))
    print(f'DEBUG player_detail: found {len(partner_rows)} partner rows -> {partner_rows}')

    for row in partner_rows:
        partner_id = row['player']
        part = Player.objects.filter(pk=partner_id).first()
        # use ORM for accurate, readable counts on the games where both played
        games_qs = Game.objects.filter(id__in=game_ids).filter(participations__player=part).distinct()
        # totals
        together_count = games_qs.count()
        logger.debug('player_detail partner %s: games_qs_count=%s', partner_id, games_qs.count())
        print(f'DEBUG partner {partner_id}:games_qs_count={games_qs.count()}')
        # games where both specific players had the villain/kind role
        together_villain = Game.objects.filter(id__in=game_ids, participations__player=player, participations__role='villain')\
                    .filter(participations__player=part, participations__role='villain')\
                    .distinct().count()
        together_kind = Game.objects.filter(id__in=game_ids, participations__player=player, participations__role='kind')\
                  .filter(participations__player=part, participations__role='kind')\
                  .distinct().count()
        # wins where both specific players were villain/kind and that side won
        wins_both_villain = Game.objects.filter(id__in=game_ids, participations__player=player, participations__role='villain')\
                    .filter(participations__player=part, participations__role='villain', winner_role='villain')\
                    .distinct().count()
        wins_both_kind = Game.objects.filter(id__in=game_ids, participations__player=player, participations__role='kind')\
                      .filter(participations__player=part, participations__role='kind', winner_role='kind')\
                      .distinct().count()

        total = together_count or 0

        wins_same_team = wins_both_villain + wins_both_kind
        together_play_same_team = together_villain + together_kind
        win_pct_partner = round((wins_same_team / together_play_same_team * 100), 1) if together_play_same_team > 0 else 0
        logger.debug('player_detail partner %s summary: wins_same_team=%s total=%s win_pct=%s', partner_id, wins_same_team, total, win_pct_partner)
        print(f'DEBUG partner {partner_id} summary: wins_same_team={wins_same_team} total={total} win_pct={win_pct_partner}')
        
        partners.append({
            'player': part,
            'count': total,
            'together_play_same_team': together_play_same_team,
            'wins_partner': wins_same_team,
            'together_villain': together_villain,
            'together_kind': together_kind,
            'wins_both_villain': wins_both_villain,
            'wins_both_kind': wins_both_kind,
            'losses_both_villain': together_villain - wins_both_villain,
            'losses_both_kind': together_kind - wins_both_kind,
            'win_pct': win_pct_partner,
        })
    # info distribution overall and when player's side won/lost
    info_qs = Participation.objects.filter(player=player).values('info').annotate(cnt=Count('id'))
    cnt_pire = 0; cnt_neutre = 0; cnt_meilleur = 0
    for it in info_qs:
        if it['info'] == 'pire': cnt_pire = it['cnt']
        if it['info'] == 'neutre': cnt_neutre = it['cnt']
        if it['info'] == 'meilleur': cnt_meilleur = it['cnt']

    info_win_qs = Participation.objects.filter(player=player, role=F('game__winner_role')).values('info').annotate(cnt=Count('id'))
    win_pire = win_neutre = win_meilleur = 0
    for it in info_win_qs:
        if it['info'] == 'pire': win_pire = it['cnt']
        if it['info'] == 'neutre': win_neutre = it['cnt']
        if it['info'] == 'meilleur': win_meilleur = it['cnt']

    info_loss_qs = Participation.objects.filter(player=player).exclude(role=F('game__winner_role')).values('info').annotate(cnt=Count('id'))
    loss_pire = loss_neutre = loss_meilleur = 0
    for it in info_loss_qs:
        if it['info'] == 'pire': loss_pire = it['cnt']
        if it['info'] == 'neutre': loss_neutre = it['cnt']
        if it['info'] == 'meilleur': loss_meilleur = it['cnt']

    return render(request, 'player_detail.html', {
        'player': player,
        'total_games': total_games,
        'total_games_villain': cnt_villains,
        'total_games_kind': cnt_kinds,
        'pct_games_villain': pct_games_villain,
        'pct_games_kind': pct_games_kind,
        'wins': wins_count,
        'wins_villain': wins_villain,
        'wins_kind': wins_kind,
        'pct_wins_villain': pct_wins_villain, 'pct_wins_kind': pct_wins_kind,
        'cnt_villains': cnt_villains,
        'cnt_kinds': cnt_kinds,
        'losses': losses,
        'losses_villain': losses_villain,
        'losses_kind': losses_kind,
        'win_pct': round(win_pct, 1),
        'partners': partners,
        'cnt_pire': cnt_pire,
        'cnt_neutre': cnt_neutre,
        'cnt_meilleur': cnt_meilleur,
        'win_pire': win_pire,
        'win_neutre': win_neutre,
        'win_meilleur': win_meilleur,
        'loss_pire': loss_pire,
        'loss_neutre': loss_neutre,
        'loss_meilleur': loss_meilleur,
    })
