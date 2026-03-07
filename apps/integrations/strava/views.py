import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.conf import settings

from apps.integrations.models import Activity, DataSource
from .client import StravaClient, exchange_code, get_oauth_url


@login_required
def strava_connect(request):
    url = get_oauth_url(
        redirect_uri=settings.STRAVA_REDIRECT_URI,
        client_id=settings.STRAVA_CLIENT_ID,
    )
    return redirect(url)


@login_required
def strava_callback(request):
    code = request.GET.get("code")
    error = request.GET.get("error")

    if error or not code:
        messages.error(request, f"Strava authorization failed: {error or 'no code'}")
        return redirect("integrations_home")

    try:
        data = exchange_code(
            code=code,
            client_id=settings.STRAVA_CLIENT_ID,
            client_secret=settings.STRAVA_CLIENT_SECRET,
            redirect_uri=settings.STRAVA_REDIRECT_URI,
        )
    except Exception as e:
        messages.error(request, f"Strava token exchange failed: {e}")
        return redirect("integrations_home")

    athlete = data.get("athlete", {})
    request.user.strava_athlete_id = athlete.get("id")
    request.user.strava_access_token = data["access_token"]
    request.user.strava_refresh_token = data["refresh_token"]
    request.user.strava_token_expires_at = datetime.datetime.fromtimestamp(
        data["expires_at"], tz=datetime.timezone.utc
    )
    request.user.save(
        update_fields=[
            "strava_athlete_id",
            "strava_access_token",
            "strava_refresh_token",
            "strava_token_expires_at",
        ]
    )
    messages.success(request, f"Connected to Strava as {athlete.get('firstname', '')} {athlete.get('lastname', '')}.")
    return redirect("integrations_home")


@login_required
def strava_disconnect(request):
    if request.method == "POST":
        request.user.strava_athlete_id = None
        request.user.strava_access_token = None
        request.user.strava_refresh_token = None
        request.user.strava_token_expires_at = None
        request.user.save(
            update_fields=[
                "strava_athlete_id",
                "strava_access_token",
                "strava_refresh_token",
                "strava_token_expires_at",
            ]
        )
        messages.info(request, "Disconnected from Strava.")
    return redirect("integrations_home")


@login_required
def strava_sync(request):
    """Pull recent Strava activities and upsert into Activity table."""
    if not request.user.strava_connected:
        messages.error(request, "Connect Strava first.")
        return redirect("integrations_home")

    client = StravaClient(request.user)
    # Sync from the most recent activity we have, or last 90 days
    last = Activity.objects.filter(user=request.user, source=DataSource.STRAVA).order_by("-start_datetime").first()
    after = last.start_datetime if last else datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=90)

    try:
        page = 1
        synced = 0
        while True:
            activities = client.get_activities(after=after, per_page=50, page=page)
            if not activities:
                break
            for raw in activities:
                _upsert_activity(request.user, raw)
                synced += 1
            if len(activities) < 50:
                break
            page += 1
    except Exception as e:
        messages.error(request, f"Strava sync failed: {e}")
        return redirect("integrations_home")

    messages.success(request, f"Synced {synced} activities from Strava.")
    return redirect("integrations_home")


def _upsert_activity(user, raw: dict):
    """Create or update an Activity from a Strava activity dict."""
    start_dt = datetime.datetime.fromisoformat(raw["start_date"].replace("Z", "+00:00"))

    ftp = user.ftp or 0
    avg_watts = raw.get("average_watts")
    np = raw.get("weighted_average_watts") or avg_watts
    if_val = round(np / ftp, 3) if (np and ftp) else None
    tss = round((raw.get("moving_time", 0) * np * if_val) / (ftp * 3600) * 100, 1) if (np and if_val and ftp) else None

    Activity.objects.update_or_create(
        source=DataSource.STRAVA,
        external_id=str(raw["id"]),
        defaults={
            "user": user,
            "name": raw.get("name", "Strava Activity"),
            "sport_type": raw.get("sport_type", raw.get("type", "Ride")),
            "start_datetime": start_dt,
            "duration_seconds": raw.get("moving_time", 0),
            "distance_meters": raw.get("distance"),
            "elevation_gain_meters": raw.get("total_elevation_gain"),
            "average_watts": avg_watts,
            "normalized_power": np,
            "intensity_factor": if_val,
            "tss": tss,
            "average_hr": raw.get("average_heartrate"),
            "max_hr": raw.get("max_heartrate"),
            "strava_kudos": raw.get("kudos_count"),
            "strava_url": f"https://www.strava.com/activities/{raw['id']}",
            "raw_data": raw,
        },
    )
