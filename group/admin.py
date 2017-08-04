from airone.lib.resources import AironeModelResource
from django.contrib import admin
from django.contrib.auth.models import Permission
from import_export import fields

from user.models import User
from .models import Group


class GroupResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name'],
        'mandatory_keys':       ['name'],
        'resource_module':      'group.admin',
        'resource_model_name':  'GroupResource',
    }
    COMPARING_KEYS = ['name']

    class Meta:
        model = Group
        fields = ('id', 'name')
