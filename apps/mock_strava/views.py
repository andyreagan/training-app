"""
Mock Strava API views.

Implements the subset of Strava's API that our app (and stravalib) use:

OAuth:
  GET  /oauth/authorize   → redirect with ?code=...
  POST /oauth/token        → exchange code / refresh token

API v3:
  GET  /api/v3/athlete              → authenticated athlete
  GET  /api/v3/athlete/activities   → list activities (paginated)
  GET  /api/v3/activities/{id}      → single activity detail
"""

from __future__ import annotations

import json

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import state

# ── OAuth endpoints ────────────────────────────────────────────────────────────


@require_GET
def authorize(request):
    """
    GET /oauth/authorize?client_id=...&redirect_uri=...&scope=...&response_type=code

    In real Strava this renders a consent page.  Our mock auto-approves
    and redirects back with a code for the first registered athlete,
    or you can pass ``mock_athlete_id`` as a query param.
    """
    redirect_uri = request.GET.get("redirect_uri", "")
    a_state = request.GET.get("state", "")

    # Pick which athlete to authorize
    mock_athlete_id = request.GET.get("mock_athlete_id")
    if mock_athlete_id:
        athlete_id = int(mock_athlete_id)
    elif state.athletes:
        athlete_id = next(iter(state.athletes))
    else:
        return JsonResponse({"error": "No mock athletes registered"}, status=400)

    code = state.create_auth_code(athlete_id)

    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={code}"
    if a_state:
        location += f"&state={a_state}"
    return HttpResponseRedirect(location)


@csrf_exempt
@require_http_methods(["POST"])
def token(request):
    """
    POST /oauth/token

    Handles both grant_type=authorization_code and grant_type=refresh_token.
    Accepts params in the POST body (form-encoded or JSON) or as query params
    (stravalib sends them as query params via requests' ``params=``).
    """
    # stravalib sends POST params as query-string params (requests lib behavior)
    params = {**request.GET.dict(), **request.POST.dict()}

    # Also try JSON body
    if not params.get("grant_type") and request.content_type == "application/json":
        try:
            params.update(json.loads(request.body))
        except (json.JSONDecodeError, ValueError):
            pass

    grant_type = params.get("grant_type")

    if grant_type == "authorization_code":
        return _handle_code_exchange(params)
    elif grant_type == "refresh_token":
        return _handle_refresh(params)
    else:
        return JsonResponse({"error": f"Unsupported grant_type: {grant_type}"}, status=400)


def _handle_code_exchange(params: dict) -> HttpResponse:
    code = params.get("code", "")
    athlete_id = state.auth_codes.pop(code, None)
    if athlete_id is None:
        return JsonResponse({"error": "Invalid authorization code"}, status=400)

    athlete = state.athletes.get(athlete_id)
    if athlete is None:
        return JsonResponse({"error": "Athlete not found"}, status=404)

    access, refresh, expires_at = state.create_tokens(athlete_id)
    return JsonResponse(
        {
            "token_type": "Bearer",
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expires_at,
            "expires_in": 21600,
            "athlete": {
                "id": athlete.id,
                "firstname": athlete.firstname,
                "lastname": athlete.lastname,
                "username": athlete.username,
                "city": athlete.city,
                "state": athlete.state,
                "country": athlete.country,
                "sex": athlete.sex,
                "premium": athlete.premium,
                "summit": athlete.summit,
                "profile": athlete.profile,
                "profile_medium": athlete.profile_medium,
                "created_at": athlete.created_at,
                "updated_at": athlete.updated_at,
            },
        }
    )


def _handle_refresh(params: dict) -> HttpResponse:
    refresh_token = params.get("refresh_token", "")
    athlete_id = state.refresh_tokens.pop(refresh_token, None)
    if athlete_id is None:
        return JsonResponse({"error": "Invalid refresh token"}, status=400)

    access, new_refresh, expires_at = state.create_tokens(athlete_id)
    return JsonResponse(
        {
            "token_type": "Bearer",
            "access_token": access,
            "refresh_token": new_refresh,
            "expires_at": expires_at,
            "expires_in": 21600,
        }
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_authenticated_athlete(request) -> tuple:
    """
    Extract access_token from Authorization header or query param
    (stravalib sends it as a query param ``access_token``).
    Returns (MockAthlete, None) or (None, JsonResponse).
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
    else:
        token_str = request.GET.get("access_token", "")

    if not token_str:
        return None, JsonResponse({"error": "Authorization required"}, status=401)

    athlete = state.get_athlete_for_token(token_str)
    if athlete is None:
        return None, JsonResponse({"error": "Invalid access token"}, status=401)

    return athlete, None


# ── API v3 endpoints ───────────────────────────────────────────────────────────


@require_GET
def api_athlete(request):
    """GET /api/v3/athlete — returns the authenticated athlete."""
    athlete, error = _get_authenticated_athlete(request)
    if error:
        return error

    return JsonResponse(
        {
            "id": athlete.id,
            "firstname": athlete.firstname,
            "lastname": athlete.lastname,
            "username": athlete.username,
            "city": athlete.city,
            "state": athlete.state,
            "country": athlete.country,
            "sex": athlete.sex,
            "premium": athlete.premium,
            "summit": athlete.summit,
            "ftp": athlete.ftp,
            "weight": athlete.weight,
            "profile": athlete.profile,
            "profile_medium": athlete.profile_medium,
            "created_at": athlete.created_at,
            "updated_at": athlete.updated_at,
            "resource_state": 3,
            "follower_count": 10,
            "friend_count": 20,
            "measurement_preference": "meters",
            "bikes": [],
            "shoes": [],
            "clubs": [],
        }
    )


@require_GET
def api_athlete_activities(request):
    """
    GET /api/v3/athlete/activities?before=&after=&page=&per_page=

    Returns paginated list of activities for the authenticated athlete.
    """
    athlete, error = _get_authenticated_athlete(request)
    if error:
        return error

    # Filter activities for this athlete
    activities = [a for a in state.activities.values() if a.athlete_id == athlete.id]

    # Sort by start_date descending (newest first) — Strava default
    activities.sort(key=lambda a: a.start_date, reverse=True)

    # Time filters
    before = request.GET.get("before")
    after = request.GET.get("after")
    if before:
        before_ts = int(before)
        activities = [a for a in activities if _parse_iso_timestamp(a.start_date) < before_ts]
    if after:
        after_ts = int(after)
        activities = [a for a in activities if _parse_iso_timestamp(a.start_date) > after_ts]

    # Pagination
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 30))
    start = (page - 1) * per_page
    end = start + per_page
    page_results = activities[start:end]

    return JsonResponse([a.to_summary_dict() for a in page_results], safe=False)


@require_GET
def api_activity_detail(request, activity_id):
    """GET /api/v3/activities/{id} — returns detailed activity."""
    athlete, error = _get_authenticated_athlete(request)
    if error:
        return error

    activity = state.activities.get(activity_id)
    if activity is None:
        return JsonResponse({"error": "Activity not found"}, status=404)

    # Strava returns 404 if the activity doesn't belong to the authenticated
    # athlete (unless the activity is visible to them)
    if activity.athlete_id != athlete.id:
        return JsonResponse({"error": "Activity not found"}, status=404)

    return JsonResponse(activity.to_detail_dict())


@require_GET
def api_activity_streams(request, activity_id):
    """GET /api/v3/activities/{id}/streams?keys=time,watts&key_by_type=true"""
    athlete, error = _get_authenticated_athlete(request)
    if error:
        return error

    activity = state.activities.get(activity_id)
    if activity is None or activity.athlete_id != athlete.id:
        return JsonResponse({"error": "Activity not found"}, status=404)

    keys = request.GET.get("keys", "time,watts,heartrate").split(",")
    result = {}

    import random

    random.seed(activity_id)  # reproducible

    watts = activity.power_stream
    if watts is None:
        base = int(activity.average_watts or 200)
        watts = [max(0, base + random.randint(-30, 30)) for _ in range(activity.moving_time)]

    time_data = list(range(len(watts)))

    if "time" in keys:
        result["time"] = {
            "data": time_data,
            "series_type": "time",
            "original_size": len(time_data),
            "resolution": "high",
        }
    if "watts" in keys:
        result["watts"] = {
            "data": watts,
            "series_type": "time",
            "original_size": len(watts),
            "resolution": "high",
        }
    if "heartrate" in keys and activity.has_heartrate:
        base_hr = int(activity.average_heartrate or 140)
        hr_data = [max(60, base_hr + random.randint(-10, 10)) for _ in range(activity.moving_time)]
        result["heartrate"] = {
            "data": hr_data,
            "series_type": "time",
            "original_size": len(hr_data),
            "resolution": "high",
        }

    return JsonResponse(result)


# ── Utilities ──────────────────────────────────────────────────────────────────


def _parse_iso_timestamp(iso_str: str) -> int:
    """Parse an ISO 8601 datetime string to a Unix timestamp (int)."""
    import datetime

    dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp())
