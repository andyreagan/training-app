from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("plans/", include("apps.plans.urls")),
    path("scheduler/", include("apps.scheduler.urls")),
    path("devices/", include("apps.devices.urls")),
    path("integrations/", include("apps.integrations.urls")),
    path("dashboard/", include("apps.accounts.dashboard_urls")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]
