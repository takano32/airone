from import_export import fields, widgets
from django.contrib import admin
from .models import AttributeBase
from .models import Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.resources import AironeModelResource

admin.site.register(AttributeBase)
admin.site.register(Entity)


class EntityResource(AironeModelResource):
    COMPARING_KEYS = ['name', 'note', 'created_user']

    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = Entity
        fields = ('id', 'name', 'note')
        export_order = ('id', 'name', 'note', 'user')

class AttrBaseResource(AironeModelResource):
    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity', 'created_user']

    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='name'))
    entity = fields.Field(column_name='entity',
                          attribute='parent_entity',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))

    class Meta:
        model = AttributeBase
        fields = ('id', 'name', 'type', 'is_mandatory')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new AttributeBase objects is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            entity = instance.parent_entity

            if not entity.attr_bases.filter(id=instance.id):
                entity.attr_bases.add(instance)
