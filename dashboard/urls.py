from django.conf.urls import url
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^login/$', auth_views.login, {'template_name': 'login.html'}, name='login'),
    url(r'^logout/$', auth_views.logout, {'template_name': 'logout.html'}, name='logout'),
    url(r'^import/$', views.import_data, name='import'),
    url(r'^do_import/$', views.do_import_data, name='do_import'),
    url(r'^search/$', views.search, name='search'),
    url(r'^advanced_search$', views.advanced_search, name='advanced_search'),
    url(r'^advanced_search_result$', views.advanced_search_result, name='advanced_search_result'),
    url(r'^advanced_search_export$', views.export_search_result, name='export_search_result'),
]
