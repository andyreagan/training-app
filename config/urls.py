from django.apps import apps
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.views import demo_login_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("demo/", demo_login_view, name="demo"),  # top-level /demo/
    path("accounts/", include("apps.accounts.urls")),
    path("plans/", include("apps.plans.urls")),
    path("scheduler/", include("apps.scheduler.urls")),
    path("devices/", include("apps.devices.urls")),
    path("integrations/", include("apps.integrations.urls")),
    path("fatigue/", include("apps.fatigue.urls")),
    path("dashboard/", include("apps.accounts.dashboard_urls")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]

# Include mock Strava API routes when the mock app is installed (testing only)
if apps.is_installed("apps.mock_strava"):
    urlpatterns += [
        path("mock-strava/", include("apps.mock_strava.urls")),
    ]
