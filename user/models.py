from django.db import models
from django.contrib.auth.models import User as DjangoUser


class User(DjangoUser):
    authorized_type = models.IntegerField(default=0)

    # to make a polymorphism between the Group model
    @property
    def permissions(self):
        return self.user_permissions
