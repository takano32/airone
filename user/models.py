from django.db import models


class Member(models.Model):
    name = models.CharField(max_length=200)
    created_time = models.DateTimeField(auto_now=True)

class User(Member):
    userid = models.CharField(max_length=200)
    passwd = models.CharField(max_length=200)
    type = models.IntegerField(default=0)
    logined_time = models.DateTimeField(auto_now=True)

class Group(Member):
    users = models.ManyToManyField(User)
