"""
Strava API client — thin wrapper around the REST API.

We avoid pulling in stravalib as a hard dependency for now; the raw
requests calls keep things transparent and easy to adapt for Garmin
or any other source later.
"""

import datetime

import requests
from django.conf import settings
from django.utils import timezone


def _strava_base_url() -> str:
    """Return the base URL for Strava (overridable via settings.STRAVA_BASE_URL for testing)."""
    return getattr(settings, "STRAVA_BASE_URL", "https://www.strava.com")


STRAVA_TOKEN_URL_PATH = "/oauth/token"
STRAVA_API_BASE_PATH = "/api/v3"


class StravaClient:
    def __init__(self, user):
        self.user = user

    def _refresh_if_needed(self):
        if not self.user.strava_refresh_token:
            raise ValueError("User has not connected Strava.")
        expires = self.user.strava_token_expires_at
        if expires and expires > timezone.now() + datetime.timedelta(minutes=5):
            return  # token still valid

        resp = requests.post(
            f"{_strava_base_url()}{STRAVA_TOKEN_URL_PATH}",
            data={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self.user.strava_refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self.user.strava_access_token = data["access_token"]
        self.user.strava_refresh_token = data["refresh_token"]
        self.user.strava_token_expires_at = datetime.datetime.fromtimestamp(
            data["expires_at"], tz=datetime.UTC
        )
        self.user.save(
            update_fields=[
                "strava_access_token",
                "strava_refresh_token",
                "strava_token_expires_at",
            ]
        )

    def _get(self, path, **params):
        self._refresh_if_needed()
        resp = requests.get(
            f"{_strava_base_url()}{STRAVA_API_BASE_PATH}{path}",
            headers={"Authorization": f"Bearer {self.user.strava_access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_athlete(self):
        return self._get("/athlete")

    def get_activities(
        self, after: datetime.datetime | None = None, per_page: int = 50, page: int = 1
    ):
        params = {"per_page": per_page, "page": page}
        if after:
            params["after"] = int(after.timestamp())
        return self._get("/athlete/activities", **params)

    def get_activity(self, activity_id: int):
        return self._get(f"/activities/{activity_id}")

    def get_activity_streams(self, activity_id: int, stream_types: list[str] | None = None):
        """Fetch second-by-second stream data for an activity.

        Returns a dict keyed by stream type, each value being a dict with
        at least ``{"data": [...], "original_size": N}``.
        """
        if stream_types is None:
            stream_types = ["time", "watts", "heartrate"]
        keys = ",".join(stream_types)
        return self._get(
            f"/activities/{activity_id}/streams",
            keys=keys,
            key_by_type="true",
        )


def get_oauth_url(redirect_uri: str, client_id: str) -> str:
    base = _strava_base_url()
    return (
        f"{base}/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=activity:read_all"
    )


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        f"{_strava_base_url()}{STRAVA_TOKEN_URL_PATH}",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
