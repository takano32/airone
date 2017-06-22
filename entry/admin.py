from django.contrib import admin
from .models import Entry
from .models import Attribute, AttributeValue

admin.site.register(Entry)
admin.site.register(Attribute)
admin.site.register(AttributeValue)
