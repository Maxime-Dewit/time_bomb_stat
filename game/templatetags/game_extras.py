from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def pct(value, decimals: int = 0):
    """57.14 -> « 57 % » ; None -> « — »."""
    if value is None or value == "":
        return "—"
    text = f"{float(value):.{int(decimals)}f}".replace(".", ",")
    return f"{text} %"


@register.filter
def signed(value):
    if value is None:
        return "—"
    return f"+{value}" if value > 0 else str(value)


@register.filter
def minutes(td):
    if not td:
        return "—"
    total = int(td.total_seconds() // 60)
    return f"{total // 60} h {total % 60:02d}" if total >= 60 else f"{total} min"


def heat(value):
    """Style CSS d'une cellule divergente centrée sur 50 % (voir .heat dans app.css)."""
    if value is None:
        return ""
    t = max(-1.0, min(1.0, (float(value) - 50) / 40))
    side = "hi" if t >= 0 else "lo"
    return f"--t:{abs(t):.2f}", side


@register.filter
def heat_style(value):
    res = heat(value)
    return res[0] if res else ""


@register.filter
def heat_side(value):
    res = heat(value)
    return res[1] if res else "none"


@register.filter
def bar(value, maximum):
    """Largeur en % d'une barre relative au maximum."""
    try:
        return round(float(value) / float(maximum) * 100, 1) if maximum else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag
def avatar(player, size="md"):
    return format_html(
        '<span class="avatar avatar--{}" style="--hue:{}" aria-hidden="true">{}</span>',
        size,
        player.hue,
        player.initials,
    )


@register.inclusion_tag("game/partials/form_dots.html")
def form_dots(results):
    return {"results": results}


@register.inclusion_tag("game/partials/player_chip.html")
def player_chip(player, extra=""):
    return {"player": player, "extra": extra}


@register.filter
def css(value):
    """Nombre au format CSS (point décimal, jamais localisé)."""
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "0"
