from django.contrib.auth.models import Group

Group.get_acls = (lambda x, obj: x.permissions.filter(codename__regex=(r'^%d\.' % obj.id)))
