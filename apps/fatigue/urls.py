from django.urls import path

from . import views

urlpatterns = [
    path("", views.fatigue_dashboard, name="fatigue_dashboard"),
    path("api/data/", views.fatigue_data_api, name="fatigue_data_api"),
    path("api/calendar-tsb/", views.calendar_tsb_api, name="calendar_tsb_api"),
    path("api/power-profile/", views.power_profile_api, name="power_profile_api"),
]
