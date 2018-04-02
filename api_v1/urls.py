from django.conf.urls import url, include

from . import views
from .user import views as user_views
from .entity.urls import urlpatterns as entity_urlpatterns
from .entry.urls import urlpatterns as entry_urlpatterns

urlpatterns = [
    url(r'^entry$', views.EntryAPI.as_view()),
    url(r'^user/access_token$', user_views.AccessTokenAPI.as_view()),
    url(r'^entity/', include(entity_urlpatterns)),
    url(r'^entry/', include(entry_urlpatterns)),
]
