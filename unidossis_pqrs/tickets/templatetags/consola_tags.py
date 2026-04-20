"""
Custom template filters for the Consola Central and other admin views.
Usage: {% load consola_tags %}
"""
from django import template

register = template.Library()


@register.filter(name='getattr')
def getattr_filter(obj, attr):
    """
    Access an object's attribute dynamically in templates.
    Usage: {{ obj|getattr:"field_name" }}
    """
    try:
        return getattr(obj, attr)
    except (AttributeError, TypeError):
        return ''


@register.filter(name='get_item')
def get_item_filter(dictionary, key):
    """
    Access a dictionary value by key in templates.
    Usage: {{ dict|get_item:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''


@register.filter(name='split_csv')
def split_csv(value):
    """
    Split a comma-separated string into a list.
    Usage: {% for item in value|split_csv %}
    """
    if isinstance(value, str):
        return [v.strip() for v in value.split(',') if v.strip()]
    return []


@register.filter(name='resolve_url')
def resolve_url(url_name):
    """
    Safely resolve a Django URL name. Returns '#' if it can't be resolved
    (e.g., URLs requiring parameters like ticket_detail).
    Usage: {{ 'login'|resolve_url }}
    """
    from django.urls import reverse, NoReverseMatch
    if not url_name:
        return '#'
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return '#'


