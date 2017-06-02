from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^(\d+)/$', views.index, name='index'),
    url(r'^create/(\d+)/$', views.create, name='create'),
    url(r'^do_create/(\d+)/$', views.do_create, name='do_create'),
    url(r'^edit/(\d+)/$', views.edit, name='edit'),
    url(r'^do_edit/$', views.do_edit, name='do_edit'),
    url(r'^history/(\d+)/$', views.history, name='history'),
]
