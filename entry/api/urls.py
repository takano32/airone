from django.conf.urls import url

from . import v1

urlpatterns = [
    url(r'^v1/get_referrals/(\d+)/$', v1.get_referrals, name='get_referrals'),
    url(r'^v1/get_entries/(\d+)/$', v1.get_entries, name='get_entries'),
]
