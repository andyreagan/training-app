from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Cycling Profile",
            {"fields": ("ftp", "max_hr", "weight_kg")},
        ),
        (
            "Strava",
            {
                "fields": (
                    "strava_athlete_id",
                    "strava_access_token",
                    "strava_refresh_token",
                    "strava_token_expires_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    list_display = ["username", "email", "ftp", "strava_connected", "is_staff"]
