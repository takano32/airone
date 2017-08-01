from airone.lib.resources import AironeModelResource
from django.contrib import admin
from import_export import fields, widgets
from user.models import User
from .models import Entry
from .models import Attribute, AttributeValue
from acl.models import ACLBase
from entity.models import Entity, AttributeBase
from entry.models import Entry

admin.site.register(Entry)
admin.site.register(Attribute)
admin.site.register(AttributeValue)


class AttrValueResource(AironeModelResource):
    COMPARING_KEYS = ['value', 'referral', 'created_time']
    DISALLOW_UPDATE_KEYS = ['created_time', 'created_user', 'parent_attr']

    attr_id = fields.Field(column_name='attribute_id', attribute='parent_attr',
                        widget=widgets.ForeignKeyWidget(model=Attribute, field='id'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = AttributeValue
        fields = ('id', 'name', 'value', 'created_time')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new AttributeValue object is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            attr = instance.parent_attr

            if not attr.values.filter(id=instance.id):
                attr.values.add(instance)

class AttrResource(AironeModelResource):
    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity', 'created_user']
    DISALLOW_UPDATE_KEYS = ['is_mandatory', 'parent_entity', 'created_user']

    entry = fields.Field(column_name='entry_id', attribute='parent_entry',
                         widget=widgets.ForeignKeyWidget(model=Entry, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    entity = fields.Field(column_name='entity',
                          attribute='parent_entity',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))

    class Meta:
        model = Attribute
        fields = ('id', 'name', 'schema_id')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new Attribute object is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            entry = instance.parent_entry

            if not entry.attrs.filter(id=instance.id):
                entry.attrs.add(instance)

class EntryResource(AironeModelResource):
    COMPARING_KEYS = ['name']

    entity = fields.Field(column_name='entity', attribute='schema',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = Entry
        fields = ('id', 'name')
