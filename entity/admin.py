from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.widgets import ManyToManyWidget
from django.contrib import admin
from .models import AttributeBase
from .models import Entity
from user.models import User

admin.site.register(AttributeBase)
admin.site.register(Entity)


class EntityResource(resources.ModelResource):
    note = fields.Field(column_name='note', attribute='note')
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=ForeignKeyWidget(User, 'username'))
    attrs = fields.Field(column_name='attrs', attribute='attr_bases',
                         widget=ManyToManyWidget(model=AttributeBase, field='name'))

    class Meta:
        model = Entity
        fields = ('id', 'name')
        export_order = ('id', 'name', 'note', 'user', 'attrs')

    def get_or_init_instance(self, instance_loader, row):
        # make AttributeBase objects

        return super(EntityResource, self).get_or_init_instance(instance_loader, row)

class AttrBaseResource(resources.ModelResource):
    entity = fields.Field(column_name='entity',
                          attribute='parent_entity',
                          widget=ForeignKeyWidget(model=Entity, field='name'))

    class Meta:
        model = AttributeBase
        fields = ('id', 'name', 'type', 'referral__name')
        export_order = ('id', 'name', 'type', 'referral__name', 'entity')
