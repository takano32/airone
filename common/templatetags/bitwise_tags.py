from django import template

register = template.Library()


@register.filter
def bitwise_and(value, arg):
    return value and arg and int(value) & int(arg)

@register.filter
def isin(obj, entries):
    return entries.filter(id=obj['id']).exists()
