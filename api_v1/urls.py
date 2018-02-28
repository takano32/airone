from django.conf.urls import url, include

from . import views
from .user import views as user_views

urlpatterns = [
    url(r'^entry$', views.EntryAPI.as_view()),
    url(r'^user/access_token$', user_views.AccessTokenAPI.as_view()),
]
