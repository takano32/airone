from django.db import models
from user.models import User, Member


class Group(Member):
    users = models.ManyToManyField(User)
