from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from game.forms import PlayerForm
from game.models import Player

from .stats import stats_context

SORTS = {
    "elo": ("Elo", lambda line: -line.elo),
    "win": ("% victoires", lambda line: -(line.win_pct or 0)),
    "games": ("Parties", lambda line: -line.games),
    "name": ("Nom", lambda line: line.player.name.lower()),
}


def player_list(request):
    ctx = stats_context(request)
    engine = ctx["engine"]
    sort = request.GET.get("tri", "elo")
    sort = sort if sort in SORTS else "elo"
    lines = sorted(engine.lines.values(), key=SORTS[sort][1])
    inactive = Player.objects.exclude(pk__in=engine.lines.keys())
    ctx.update(
        {
            "lines": lines,
            "inactive": inactive,
            "sort": sort,
            "sorts": {k: v[0] for k, v in SORTS.items()},
            "form": PlayerForm(),
        }
    )
    return render(request, "game/players/list.html", ctx)


@require_POST
def player_create(request):
    form = PlayerForm(request.POST)
    if form.is_valid():
        player = form.save()
        messages.success(request, f"{player.name} a rejoint la bande 🎉")
    else:
        messages.error(request, " ".join(form.errors.get("name", ["Nom invalide."])))
    return redirect("game:player_list")


def player_detail(request, pk):
    player = get_object_or_404(Player, pk=pk)
    ctx = stats_context(request)
    engine = ctx["engine"]
    line = engine.lines.get(player.pk)
    min_games = min(3, settings.TIMEBOMB_DEFAULT_MIN_GAMES)
    partners = engine.partners_of(player.pk) if line else []
    allies = sorted(
        (p for p in partners if p.same >= min_games), key=lambda p: (-(p.same_pct or 0), -p.same)
    )
    rivals = sorted(
        (p for p in partners if p.opposed >= min_games),
        key=lambda p: ((p.a_vs_b_pct or 0), -p.opposed),
    )
    titles = next((t for t in engine.titles if t["line"].player.pk == player.pk), {})
    ranking = engine.leaderboard(min_games=1)
    ctx.update(
        {
            "player": player,
            "line": line,
            "rank": next((r.rank for r in ranking if r.player.pk == player.pk), None),
            "ranked_count": len(ranking),
            "partners": partners,
            "allies": allies[:5],
            "rivals": rivals[:5],
            "titles": titles,
            "recent": engine.recent_games(player.pk),
            "timeline": engine.player_timeline(player.pk) if line else None,
            "monthly": engine.monthly_results(player.pk) if line else None,
            "partner_min": min_games,
        }
    )
    return render(request, "game/players/detail.html", ctx)


@require_POST
def player_delete(request, pk):
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    messages.success(request, f"{player.name} a été supprimé, ainsi que ses participations.")
    return redirect("game:player_list")
