from django import template

register = template.Library()


@register.filter
def bitwise_and(value, arg):
    return int(value) & int(arg)
