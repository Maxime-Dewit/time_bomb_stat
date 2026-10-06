from itertools import groupby

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from game.forms import AddPlayersForm, GameResultForm, NewGameForm
from game.models import Game, Participation, Player, Role
from game.stats import Period, build_engine, session_day

PARTICIPATIONS = Prefetch(
    "participations", queryset=Participation.objects.select_related("player").order_by("role")
)


def home(request):
    today = session_day(timezone.now())
    all_time = build_engine()
    month = build_engine(Period.month(today.year, today.month))
    last_day = all_time.days[-1] if all_time.days else None
    recent = Game.objects.finished().select_related("master").prefetch_related(PARTICIPATIONS)[:6]
    context = {
        "active_games": Game.objects.in_progress()
        .select_related("master")
        .prefetch_related(PARTICIPATIONS),
        "recent_games": recent,
        "overview": all_time.overview,
        "month_label": Period.month(today.year, today.month).label,
        "month_podium": month.leaderboard(min_games=1)[:3],
        "last_session": all_time.day_summary(last_day) if last_day else None,
        "last_game": Game.objects.finished().first(),
        "today": today,
    }
    return render(request, "game/home.html", context)


def game_list(request):
    games = (
        Game.objects.select_related("master")
        .prefetch_related(PARTICIPATIONS)
        .order_by("-started_at", "-id")
    )
    page = Paginator(games, 30).get_page(request.GET.get("page"))
    groups = [
        (day, list(items))
        for day, items in groupby(
            page.object_list, key=lambda g: session_day(g.started_at) if g.started_at else None
        )
    ]
    return render(request, "game/games/list.html", {"page": page, "groups": groups})


@require_POST
def game_create(request):
    form = NewGameForm(request.POST)
    master = form.cleaned_data["master"] if form.is_valid() else None
    game = Game.objects.create(master=master, started_at=timezone.now())
    return redirect("game:game_manage", pk=game.pk)


def game_detail(request, pk):
    game = get_object_or_404(
        Game.objects.select_related("master").prefetch_related(PARTICIPATIONS), pk=pk
    )
    parts = list(game.participations.all())
    teams = [
        {
            "role": role,
            "label": label,
            "won": game.winner_role == role,
            "members": [p for p in parts if p.role == role],
        }
        for role, label in Role.choices
    ]
    day = session_day(game.started_at) if game.started_at else None
    return render(
        request, "game/games/detail.html", {"game": game, "teams": teams, "session_day": day}
    )


def game_manage(request, pk):
    """Composition de la partie, rôles, distinctions et résultat."""
    game = get_object_or_404(Game.objects.select_related("master"), pk=pk)
    if request.method == "POST":
        form = GameResultForm(request.POST, game=game)
        if form.is_valid():
            was_running = game.ended_at is None
            form.save()
            if was_running and game.ended_at:
                winner = game.get_winner_role_display().lower()
                messages.success(request, f"Partie terminée — victoire des {winner}s ! 🎉")
                return redirect(game)
            messages.success(request, "Partie enregistrée.")
            return redirect("game:game_manage", pk=game.pk)
    else:
        form = GameResultForm(game=game)

    available = (
        Player.objects.exclude(participations__game=game)
        .annotate(games=Count("participations"))
        .order_by("-games", "name")
    )
    return render(
        request,
        "game/games/manage.html",
        {"game": game, "form": form, "available": available, "add_form": AddPlayersForm()},
    )


@require_POST
def game_add_players(request, pk):
    game = get_object_or_404(Game, pk=pk)
    form = AddPlayersForm(request.POST)
    if form.is_valid():
        added = form.save(game)
        if added:
            messages.success(
                request, f"{added} joueur{'s' * (added > 1)} ajouté{'s' * (added > 1)}."
            )
    return redirect("game:game_manage", pk=game.pk)


@require_POST
def game_remove_player(request, pk, player_pk):
    game = get_object_or_404(Game, pk=pk)
    Participation.objects.filter(game=game, player_id=player_pk).delete()
    return redirect("game:game_manage", pk=game.pk)


@require_POST
def game_rematch(request, pk):
    old = get_object_or_404(Game, pk=pk)
    game = Game.objects.create(master=old.master, started_at=timezone.now())
    Participation.objects.bulk_create(
        Participation(game=game, player_id=pid)
        for pid in old.participations.values_list("player_id", flat=True)
    )
    messages.success(request, "Nouvelle manche avec les mêmes joueurs. Distribuez les rôles !")
    return redirect("game:game_manage", pk=game.pk)


@require_POST
def game_delete(request, pk):
    game = get_object_or_404(Game, pk=pk)
    game.delete()
    messages.success(request, "Partie supprimée.")
    return redirect("game:game_list")
