from import_export.resources import ModelResource


class AironeModelResource(ModelResource):
    def __init__(self, *args, **kwargs):
        super(AironeModelResource, self).__init__(*args, **kwargs)

        # This parameter is needed to check that imported object has permission
        # to add/update it by the user who import data.
        self.request_user = None

    """
    This private method checks that two instance has same content in each attribute.
    """
    def _is_updated(self, comp1, comp2):
        return any([getattr(comp1, x) != getattr(comp2, x) for x in self.COMPARING_KEYS])

    def skip_row(self, instance, original):
        # the case of creating new instance
        if self._meta.model.objects.filter(id=instance.id).count() == 0:
            # Inhibits the spoofing
            if instance.created_user != self.request_user:
                return True

        # the case of instance is updated
        elif self._is_updated(instance, original):
            # Prevents the permission breaking
            if not self.request_user.has_permission(instance, 'writable'):
                return True

        return False
