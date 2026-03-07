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


STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


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
            STRAVA_TOKEN_URL,
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
            data["expires_at"], tz=datetime.timezone.utc
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
            f"{STRAVA_API_BASE}{path}",
            headers={"Authorization": f"Bearer {self.user.strava_access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_athlete(self):
        return self._get("/athlete")

    def get_activities(self, after: datetime.datetime = None, per_page: int = 50, page: int = 1):
        params = {"per_page": per_page, "page": page}
        if after:
            params["after"] = int(after.timestamp())
        return self._get("/athlete/activities", **params)

    def get_activity(self, activity_id: int):
        return self._get(f"/activities/{activity_id}")


def get_oauth_url(redirect_uri: str, client_id: str) -> str:
    return (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=activity:read_all"
    )


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        STRAVA_TOKEN_URL,
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
