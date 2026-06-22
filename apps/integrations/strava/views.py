import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

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
        data["expires_at"], tz=datetime.UTC
    )
    request.user.save(
        update_fields=[
            "strava_athlete_id",
            "strava_access_token",
            "strava_refresh_token",
            "strava_token_expires_at",
        ]
    )
    messages.success(
        request,
        f"Connected to Strava as {athlete.get('firstname', '')} {athlete.get('lastname', '')}.",
    )
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
    last = (
        Activity.objects.filter(user=request.user, source=DataSource.STRAVA)
        .order_by("-start_datetime")
        .first()
    )
    after = (
        last.start_datetime
        if last
        else datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=90)
    )

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

    # Fetch power streams for activities that have power data but no stream yet
    _sync_power_streams(request.user, client)

    messages.success(request, f"Synced {synced} activities from Strava.")
    return redirect("integrations_home")


def _sync_power_streams(user, client):
    """Fetch power and HR streams for recent activities that are missing stream data."""
    activities = Activity.objects.filter(
        user=user,
        source=DataSource.STRAVA,
        power_data__isnull=True,
    ).order_by("-start_datetime")[:20]  # limit to avoid rate-limiting

    for activity in activities:
        try:
            streams = client.get_activity_streams(int(activity.external_id))
            time_data = streams.get("time", {}).get("data", [])
            watts_data = streams.get("watts", {}).get("data", [])
            hr_data_raw = streams.get("heartrate", {}).get("data", [])

            update_fields = []
            if time_data and watts_data:
                activity.power_data = {"time": time_data, "watts": watts_data}
                update_fields.append("power_data")
            if time_data and hr_data_raw:
                activity.hr_data = {"time": time_data, "heartrate": hr_data_raw}
                update_fields.append("hr_data")

                # Compute hrTSS if we don't have power-based TSS
                if activity.tss is None and user.max_hr:
                    from apps.fatigue.hr import compute_hr_tss_from_stream

                    resting_hr = user.resting_hr or 60
                    result = compute_hr_tss_from_stream(
                        hr_data_raw,
                        max_hr=user.max_hr,
                        resting_hr=resting_hr,
                    )
                    if result:
                        activity.hr_tss = result.hr_tss
                        update_fields.append("hr_tss")

                # Estimate effort from HR if no rating exists
                if activity.perceived_effort is None and user.max_hr:
                    from apps.fatigue.hr import estimate_effort_from_hr

                    resting_hr = user.resting_hr or 60
                    avg_hr = activity.average_hr or (sum(hr_data_raw) / len(hr_data_raw))
                    effort_est = estimate_effort_from_hr(
                        avg_hr=avg_hr,
                        max_hr=user.max_hr,
                        resting_hr=resting_hr,
                    )
                    if effort_est:
                        activity.perceived_effort = effort_est.effort
                        activity.effort_source = "hr_estimate"
                        update_fields.extend(["perceived_effort", "effort_source"])

            if update_fields:
                activity.save(update_fields=update_fields)
        except Exception:
            continue  # stream fetch failures are non-fatal


def _upsert_activity(user, raw: dict):
    """Create or update an Activity from a Strava activity dict."""
    start_dt = datetime.datetime.fromisoformat(raw["start_date"].replace("Z", "+00:00"))

    # Use the FTP that was effective on the activity date, not the current FTP
    ftp = user.ftp_on_date(start_dt.date()) or 0
    avg_watts = raw.get("average_watts")
    np = raw.get("weighted_average_watts") or avg_watts
    if_val = round(np / ftp, 3) if (np and ftp) else None
    tss = (
        round((raw.get("moving_time", 0) * np * if_val) / (ftp * 3600) * 100, 1)
        if (np and if_val and ftp)
        else None
    )

    # HR-based TSS fallback when no power data
    hr_tss = None
    if tss is None and raw.get("average_heartrate") and user.max_hr:
        from apps.fatigue.hr import compute_hr_tss

        resting_hr = user.resting_hr or 60
        hr_result = compute_hr_tss(
            avg_hr=raw["average_heartrate"],
            max_hr=user.max_hr,
            duration_seconds=raw.get("moving_time", 0),
            resting_hr=resting_hr,
        )
        if hr_result:
            hr_tss = hr_result.hr_tss

    # Build defaults for perceived effort
    effort_defaults = {}
    strava_rpe = raw.get("perceived_exertion")
    if strava_rpe is not None:
        # Only set from Strava if user hasn't manually overridden
        existing = (
            Activity.objects.filter(
                source=DataSource.STRAVA,
                external_id=str(raw["id"]),
            )
            .values_list("effort_source", flat=True)
            .first()
        )
        if existing != "manual":
            effort_defaults["perceived_effort"] = int(strava_rpe)
            effort_defaults["effort_source"] = "strava"

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
            "hr_tss": hr_tss,
            "strava_kudos": raw.get("kudos_count"),
            "strava_url": f"https://www.strava.com/activities/{raw['id']}",
            "raw_data": raw,
            **effort_defaults,
        },
    )
