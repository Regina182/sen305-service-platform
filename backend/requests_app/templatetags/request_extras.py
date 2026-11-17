from django import template
from django.utils.http import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """Reusable query string: keeps q and status, replaces whatever is passed (e.g. page)."""
    request = context["request"]
    params = {}
    for key in ("q", "status"):
        value = request.GET.get(key, "").strip()
        if value:
            params[key] = value
    params.update(kwargs)
    return "?" + urlencode(params)
