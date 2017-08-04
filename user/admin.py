from airone.lib.resources import AironeModelResource
from django.contrib import admin
from import_export import fields, widgets

from .models import User

admin.site.register(User)


class UserResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'username', 'email'],
        'mandatory_keys':       ['username', 'email'],
        'resource_module':      'user.admin',
        'resource_model_name':  'UserResource',
    }
    COMPARING_KEYS = ['name', 'email']

    groups = fields.Field(column_name='groups', attribute='groups',
                          widget=widgets.ManyToManyWidget(model=User, field='name'))

    class Meta:
        model = User
        fields = ('id', 'username', 'email')
