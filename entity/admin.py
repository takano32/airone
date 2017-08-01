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
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'note', 'created_user'],
        'mandatory_keys':       ['name', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityResource',
    }

    COMPARING_KEYS = ['name', 'note', 'created_user']
    DISALLOW_UPDATE_KEYS = ['created_user']

    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = Entity
        fields = ('id', 'name', 'note')
        export_order = ('id', 'name', 'note', 'user')

class AttrBaseResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'type', 'refer', 'entity',
                                 'created_user', 'is_mandatory'],
        'mandatory_keys':       ['name', 'type', 'entity', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'AttrBaseResource',
    }

    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity', 'created_user']
    DISALLOW_UPDATE_KEYS = ['parent_entity', 'created_user']

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
        # If a new AttributeBase object is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            entity = instance.parent_entity

            if not entity.attr_bases.filter(id=instance.id):
                entity.attr_bases.add(instance)

    def import_obj(self, instance, data, dry_run):
        if Entity.objects.filter(name=data['entity']).count() > 0:
            super(AttrBaseResource, self).import_obj(instance, data, dry_run)
        else:
            raise RuntimeError('failed to identify entity object')
