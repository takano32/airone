from django.conf.urls import url, include

from . import views

urlpatterns = [
    url(r'^(\d+)/$', views.index, name='index'),
    url(r'^create/(\d+)/$', views.create, name='create'),
    url(r'^do_create/(\d+)/$', views.do_create, name='do_create'),
    url(r'^edit/(\d+)/$', views.edit, name='edit'),
    url(r'^do_edit/(\d+)$', views.do_edit, name='do_edit'),
    url(r'^show/(\d+)/$', views.show, name='show'),
    url(r'^export/(\d+)/$', views.export, name='export'),
    url(r'^do_delete/(\d+)/$', views.do_delete, name='do_delete'),
    url(r'^search_referral/(\d+)/$', views.do_delete, name='do_delete'),
    url(r'^api/v1/', include('entry.api_v1.urls', namespace='entry.api_v1', app_name='api_v1')),
]
