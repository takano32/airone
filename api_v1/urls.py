from django.conf.urls import url, include

from . import views
from .user import views as user_views
from .entity.urls import urlpatterns as entity_urlpatterns
from .entry.urls import urlpatterns as entry_urlpatterns
from .job.urls import urlpatterns as job_urlpatterns

urlpatterns = [
    url(r'^user/access_token$', user_views.AccessTokenAPI.as_view()),
    url(r'^entity/', include(entity_urlpatterns)),
    url(r'^entry/', include(entry_urlpatterns)),
    url(r'^job/', include(job_urlpatterns)),
]

# Custom view is prioritized to handle if it exists.
try:
    from custom_view.api_v1 import views as custom_views
    urlpatterns.append(url(r'^entry$', custom_views.CustomEntryAPI.as_view()))
except ImportError as e:
    urlpatterns.append(url(r'^entry$', views.EntryAPI.as_view()))
