from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    try:
        # try convert numeric string keys to int for dict lookup
        try:
            if isinstance(key, str) and key.isdigit():
                key = int(key)
        except Exception:
            pass
        return dictionary.get(key)
    except Exception:
        return None
