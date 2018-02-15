from django.conf.urls import url, include

from . import views

urlpatterns = [
    url(r'^entry$', views.EntryAPI.as_view()),
]
