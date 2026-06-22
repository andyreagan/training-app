from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FTPHistory, User, WeightHistory


class FTPHistoryInline(admin.TabularInline):
    model = FTPHistory
    extra = 0
    readonly_fields = ["created_at"]
    ordering = ["-effective_date"]


class WeightHistoryInline(admin.TabularInline):
    model = WeightHistory
    extra = 0
    readonly_fields = ["created_at"]
    ordering = ["-effective_date"]


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Cycling Profile",
            {"fields": ("max_hr",)},
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
    list_display = ["username", "email", "strava_connected", "is_staff"]
    inlines = [FTPHistoryInline, WeightHistoryInline]


@admin.register(FTPHistory)
class FTPHistoryAdmin(admin.ModelAdmin):
    list_display = ["user", "ftp", "effective_date", "source", "created_at"]
    list_filter = ["source", "user"]
    ordering = ["-effective_date"]
    readonly_fields = ["created_at"]


@admin.register(WeightHistory)
class WeightHistoryAdmin(admin.ModelAdmin):
    list_display = ["user", "weight_kg", "effective_date", "created_at"]
    list_filter = ["user"]
    ordering = ["-effective_date"]
    readonly_fields = ["created_at"]
