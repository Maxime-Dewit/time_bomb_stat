from datetime import date

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from game.models import Game
from game.stats import Period, build_engine, session_day
from game.stats.periods import month_label

MIN_CHOICES = [1, 3, 5, 10, 20, 50]


def _min_games(request) -> int:
    try:
        return max(1, min(100, int(request.GET.get("min", settings.TIMEBOMB_DEFAULT_MIN_GAMES))))
    except ValueError:
        return settings.TIMEBOMB_DEFAULT_MIN_GAMES


def stats_context(request) -> dict:
    """Contexte commun : période choisie, seuil de parties et moteur de stats."""
    last_game = Game.objects.finished().order_by("-started_at").first()
    last_day = session_day(last_game.started_at) if last_game else None
    today = session_day(timezone.now())
    period = Period.parse(request.GET.get("p"), today=today, last_day=last_day)
    months = Game.objects.finished().dates("started_at", "month", order="DESC")
    query = request.GET.copy()
    query.pop("page", None)
    return {
        "period": period,
        "min_games": _min_games(request),
        "engine": build_engine(period),
        "today": today,
        "last_day": last_day,
        "years": [(f"y{y}", y) for y in sorted({m.year for m in months}, reverse=True)],
        "min_choices": MIN_CHOICES,
        "months": [(f"m{m.year}-{m.month:02d}", month_label(m.year, m.month)) for m in months],
        "querystring": query.urlencode(),
    }


def overview(request):
    ctx = stats_context(request)
    engine, min_games = ctx["engine"], ctx["min_games"]
    ctx.update(
        {
            "leaderboard": engine.leaderboard(min_games),
            "podium": engine.leaderboard(min_games)[:3],
            "scatter": engine.scatter(min_games),
            "side_by_month": engine.side_by_month,
            "table_sizes": engine.by_table_size,
            "weekdays": engine.by_weekday,
            "weekday_max": max((d["games"] for d in engine.by_weekday), default=0),
            "superlatives": engine.superlatives(min_games),
            "top_villains": engine.ranked_by(lambda line: line.villain_wins, limit=5),
            "top_kinds": engine.ranked_by(lambda line: line.kind_wins, limit=5),
        }
    )
    return render(request, "game/stats/overview.html", ctx)


def evolution(request):
    ctx = stats_context(request)
    engine = ctx["engine"]
    ctx.update(
        {
            "timeline": engine.timeline(),
            "by_month": engine.by_month,
            "by_year": engine.by_year,
            "titles": engine.titles,
        }
    )
    return render(request, "game/stats/evolution.html", ctx)


def duos(request):
    ctx = stats_context(request)
    engine = ctx["engine"]
    pair_min = max(2, ctx["min_games"] // 2)
    ctx.update(
        {
            "pair_min": pair_min,
            "best_duos": engine.top_pairs(lambda p: p.same_pct, pair_min),
            "worst_duos": engine.top_pairs(lambda p: p.same_pct, pair_min, reverse=False),
            "villain_duos": engine.top_pairs(lambda p: p.villain_pct, pair_min, "both_villain"),
            "kind_duos": engine.top_pairs(lambda p: p.kind_pct, pair_min, "both_kind"),
            "frequent": engine.top_pairs(lambda p: p.together, 1, "together"),
            "rivalries": engine.rivalries(pair_min),
            "matrix": engine.matrix(ctx["min_games"]),
        }
    )
    return render(request, "game/stats/duos.html", ctx)


def _bars(lines, value, display=None) -> list[dict]:
    """Prépare une liste pour `partials/ranked_bars.html`."""
    display = display or value
    return [
        {"line": line, "value": value(line), "display": display(line)}
        for line in lines
        if value(line)
    ]


def records(request):
    ctx = stats_context(request)
    engine, min_games = ctx["engine"], ctx["min_games"]

    def best(line):
        return line.best

    def best_rate(line):
        return line.best_rate

    def worst(line):
        return line.worst

    def streak(line):
        return line.best_streak

    ctx.update(
        {
            "records": engine.records_board,
            "mvps": _bars(engine.ranked_by(best, limit=8), best),
            "mvp_rate": _bars(
                engine.ranked_by(best_rate, min_games, limit=8),
                best_rate,
                lambda line: f"{line.best_rate:.0f} %",
            ),
            "worsts": _bars(engine.ranked_by(worst, limit=8), worst),
            "streaks": _bars(engine.ranked_by(streak, limit=8), streak),
            "current": sorted(
                (line for line in engine.lines.values() if abs(line.current_streak) >= 2),
                key=lambda line: -line.current_streak,
            ),
        }
    )
    return render(request, "game/stats/records.html", ctx)


def sessions(request):
    ctx = stats_context(request)
    engine = ctx["engine"]
    period = ctx["period"]
    ctx.update(
        {
            "calendar": engine.calendar(
                start=None if period.is_all or period.is_day else period.start,
                end=None if period.is_all or period.is_day else min(period.end, ctx["today"]),
            ),
            "sessions": engine.by_day,
        }
    )
    return render(request, "game/stats/sessions.html", ctx)


def session_detail(request, day: str):
    try:
        day = date.fromisoformat(day)
    except ValueError as exc:
        raise Http404("Date invalide") from exc
    ctx = stats_context(request)
    period = Period.day(day)
    engine = build_engine(period)
    summary = engine.day_summary(day)
    if summary is None:
        raise Http404("Aucune partie ce jour-là")
    all_days = build_engine().days
    idx = all_days.index(day)
    games = (
        Game.objects.filter(pk__in=[r.id for r in engine.records])
        .prefetch_related("participations__player")
        .order_by("started_at")
    )
    ctx.update(
        {
            "period": period,
            "engine": engine,
            "summary": summary,
            "leaderboard": sorted(
                engine.leaderboard(1), key=lambda line: (-line.wins, -(line.win_pct or 0))
            ),
            "games": games,
            "prev_day": all_days[idx - 1] if idx > 0 else None,
            "next_day": all_days[idx + 1] if idx + 1 < len(all_days) else None,
            "timeline": engine.timeline(),
        }
    )
    return render(request, "game/stats/session_detail.html", ctx)
