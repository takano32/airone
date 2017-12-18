from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^get_referrals/(\d+)/$', views.get_referrals, name='get_referrals'),
    url(r'^get_entries/(\d+)/$', views.get_entries, name='get_entries'),
]
