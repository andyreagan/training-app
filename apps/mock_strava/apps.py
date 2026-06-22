from django.apps import AppConfig


class MockStravaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mock_strava"
    verbose_name = "Mock Strava API"
