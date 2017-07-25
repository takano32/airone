from airone.lib.resources import AironeModelResource
from django.contrib import admin
from import_export import fields, widgets
from user.models import User
from .models import Entry
from .models import Attribute, AttributeValue
from acl.models import ACLBase
from entity.models import Entity
from entry.models import Entry

admin.site.register(Entry)
admin.site.register(Attribute)
admin.site.register(AttributeValue)


class AttrValueResource(AironeModelResource):
    attr_id = fields.Field(column_name='attribute_id', attribute='parent_attr',
                        widget=widgets.ForeignKeyWidget(model=Entry, field='id'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='name'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = AttributeValue
        fields = ('id', 'name', 'value', 'created_time')

class AttrResource(AironeModelResource):
    entry = fields.Field(column_name='entry_id', attribute='parent_entry',
                         widget=widgets.ForeignKeyWidget(model=Entry, field='id'))

    class Meta:
        model = Attribute
        fields = ('id', 'name', 'schema_id')

class EntryResource(AironeModelResource):
    entity = fields.Field(column_name='entity', attribute='schema',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))

    class Meta:
        model = Entry
        fields = ('id', 'name')
