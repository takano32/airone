from django.contrib import admin
from .models import Attribute
from .models import AttributeBase
from .models import AttributeValue
from .models import Entity

admin.site.register(Attribute)
admin.site.register(AttributeBase)
admin.site.register(AttributeValue)
admin.site.register(Entity)
