from django.db import models
from django.contrib.auth.models import User as DjangoUser


class User(DjangoUser):
    authorized_type = models.IntegerField(default=0)
