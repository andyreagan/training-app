"""
In-memory data store for the mock Strava API.

We avoid creating real Django models (and thus migrations) — this app
is only loaded during tests.  All state lives in module-level dicts
that are reset between tests via ``mock_strava_state.reset()``.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class MockAthlete:
    id: int
    firstname: str = "Test"
    lastname: str = "Athlete"
    username: str = "testathlete"
    city: str = "Burlington"
    state: str = "Vermont"
    country: str = "United States"
    sex: str = "M"
    premium: bool = False
    summit: bool = False
    ftp: int = 250
    weight: float = 75.0
    profile: str = "https://example.com/avatar.jpg"
    profile_medium: str = "https://example.com/avatar_medium.jpg"
    created_at: str = "2020-01-01T00:00:00Z"
    updated_at: str = "2024-01-01T00:00:00Z"


@dataclass
class MockActivity:
    id: int
    athlete_id: int
    name: str = "Morning Ride"
    sport_type: str = "Ride"
    type: str = "Ride"
    start_date: str = "2024-06-15T10:00:00Z"
    start_date_local: str = "2024-06-15T06:00:00Z"
    timezone: str = "(GMT-05:00) America/New_York"
    utc_offset: float = -18000.0
    moving_time: int = 3600
    elapsed_time: int = 3900
    distance: float = 40000.0  # meters
    total_elevation_gain: float = 500.0
    average_speed: float = 11.11
    max_speed: float = 15.0
    average_watts: float = 200.0
    weighted_average_watts: int = 210
    kilojoules: float = 720.0
    device_watts: bool = True
    average_heartrate: float = 145.0
    max_heartrate: int = 175
    average_cadence: float = 85.0
    kudos_count: int = 5
    comment_count: int = 1
    achievement_count: int = 3
    athlete_count: int = 1
    photo_count: int = 0
    total_photo_count: int = 0
    trainer: bool = False
    commute: bool = False
    manual: bool = False
    private: bool = False
    flagged: bool = False
    has_heartrate: bool = True
    has_kudoed: bool = False
    hide_from_home: bool = False
    gear_id: str | None = None
    map: dict = field(default_factory=lambda: {"id": "a1", "summary_polyline": "", "polyline": ""})
    start_latlng: list = field(default_factory=lambda: [44.4759, -73.2121])
    end_latlng: list = field(default_factory=lambda: [44.4760, -73.2120])
    external_id: str | None = None
    upload_id: int | None = None
    pr_count: int = 0
    suffer_score: int | None = None
    workout_type: int | None = None
    perceived_exertion: int | None = None
    description: str = ""
    calories: float = 500.0
    visibility: str = "everyone"
    power_stream: list | None = None  # optional second-by-second watts for streams endpoint

    def to_summary_dict(self) -> dict:
        """Return the JSON shape Strava sends for list endpoints."""
        return {
            "id": self.id,
            "athlete": {"id": self.athlete_id},
            "name": self.name,
            "sport_type": self.sport_type,
            "type": self.type,
            "start_date": self.start_date,
            "start_date_local": self.start_date_local,
            "timezone": self.timezone,
            "utc_offset": self.utc_offset,
            "moving_time": self.moving_time,
            "elapsed_time": self.elapsed_time,
            "distance": self.distance,
            "total_elevation_gain": self.total_elevation_gain,
            "average_speed": self.average_speed,
            "max_speed": self.max_speed,
            "average_watts": self.average_watts,
            "weighted_average_watts": self.weighted_average_watts,
            "kilojoules": self.kilojoules,
            "device_watts": self.device_watts,
            "average_heartrate": self.average_heartrate,
            "max_heartrate": self.max_heartrate,
            "average_cadence": self.average_cadence,
            "kudos_count": self.kudos_count,
            "comment_count": self.comment_count,
            "achievement_count": self.achievement_count,
            "athlete_count": self.athlete_count,
            "photo_count": self.photo_count,
            "total_photo_count": self.total_photo_count,
            "trainer": self.trainer,
            "commute": self.commute,
            "manual": self.manual,
            "private": self.private,
            "flagged": self.flagged,
            "has_heartrate": self.has_heartrate,
            "has_kudoed": self.has_kudoed,
            "hide_from_home": self.hide_from_home,
            "gear_id": self.gear_id,
            "map": self.map,
            "start_latlng": self.start_latlng,
            "end_latlng": self.end_latlng,
            "external_id": self.external_id,
            "upload_id": self.upload_id,
            "pr_count": self.pr_count,
            "suffer_score": self.suffer_score,
            "workout_type": self.workout_type,
            "visibility": self.visibility,
        }

    def to_detail_dict(self) -> dict:
        """Return the JSON shape Strava sends for single-activity endpoints."""
        d = self.to_summary_dict()
        d.update(
            {
                "perceived_exertion": self.perceived_exertion,
                "prefer_perceived_exertion": self.perceived_exertion is not None,
                "description": self.description,
                "calories": self.calories,
                "segment_efforts": [],
                "splits_metric": [],
                "splits_standard": [],
                "laps": [],
                "best_efforts": [],
                "photos": {"primary": None, "count": 0},
                "similar_activities": {"trend": None, "effort_count": 0},
                "device_name": "Mock Trainer",
                "embed_token": "abc123",
            }
        )
        return d


class MockStravaState:
    """
    Singleton-ish mutable state for the mock Strava server.

    Call ``reset()`` between tests to get a clean slate.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        # athlete_id → MockAthlete
        self.athletes: dict[int, MockAthlete] = {}
        # activity_id → MockActivity
        self.activities: dict[int, MockActivity] = {}
        # authorization_code → athlete_id
        self.auth_codes: dict[str, int] = {}
        # access_token → athlete_id
        self.access_tokens: dict[str, int] = {}
        # refresh_token → athlete_id
        self.refresh_tokens: dict[str, int] = {}
        # counters
        self._next_athlete_id = 1000
        self._next_activity_id = 5000

    # ── helpers for test setup ──────────────────────────────────────────

    def add_athlete(self, **kwargs) -> MockAthlete:
        """Register a mock athlete.  Returns the MockAthlete."""
        athlete_id = kwargs.pop("id", self._next_athlete_id)
        self._next_athlete_id = max(self._next_athlete_id, athlete_id + 1)
        athlete = MockAthlete(id=athlete_id, **kwargs)
        self.athletes[athlete_id] = athlete
        return athlete

    def add_activity(self, athlete_id: int, **kwargs) -> MockActivity:
        """Register a mock activity for an athlete.  Returns the MockActivity."""
        activity_id = kwargs.pop("id", self._next_activity_id)
        self._next_activity_id = max(self._next_activity_id, activity_id + 1)
        activity = MockActivity(id=activity_id, athlete_id=athlete_id, **kwargs)
        self.activities[activity_id] = activity
        return activity

    def create_auth_code(self, athlete_id: int) -> str:
        """Simulate user authorizing the app — returns an authorization code."""
        code = secrets.token_hex(16)
        self.auth_codes[code] = athlete_id
        return code

    def create_tokens(self, athlete_id: int) -> tuple[str, str, int]:
        """Create access + refresh tokens for an athlete.  Returns (access, refresh, expires_at)."""
        access = secrets.token_hex(20)
        refresh = secrets.token_hex(20)
        expires_at = int(time.time()) + 21600  # 6 hours from now
        self.access_tokens[access] = athlete_id
        self.refresh_tokens[refresh] = athlete_id
        return access, refresh, expires_at

    def get_athlete_for_token(self, access_token: str) -> MockAthlete | None:
        athlete_id = self.access_tokens.get(access_token)
        if athlete_id is None:
            return None
        return self.athletes.get(athlete_id)


# Module-level singleton
state = MockStravaState()
