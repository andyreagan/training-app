# training.andyreagan.com

A personal cycling training app: Strava sync, fatigue monitoring (Banister CTL/ATL/TSB),
power analysis, FTP history, HR-based TSS, difficulty prediction, and a training calendar.

## Quick start (local dev)

```bash
uv sync --dev
python manage.py migrate
python manage.py seed_plans          # populate workout library
python manage.py createsuperuser
python manage.py runserver
```

## Demo mode

A live, read-only demo account is available at `/demo/`. It auto-logs you in
as the `demo` user and shows 90 days of pre-seeded training data.

### Seeding / resetting demo data

```bash
python manage.py setup_demo          # create or reset demo user + data
python manage.py setup_demo --quiet  # same, no output (for cron)
```

**Cron — reset every hour on the production server:**

```cron
0 * * * * /path/to/venv/bin/python /path/to/manage.py setup_demo --quiet
```

### Environment variables

| Variable        | Default       | Purpose                              |
|-----------------|---------------|--------------------------------------|
| `DEMO_USERNAME` | `demo`        | Username for the demo account        |
| `DEMO_PASSWORD` | `demo1234`    | Password shown in the demo banner    |
| `DEMO_EMAIL`    | `demo@example.com` | Email for the demo account      |

### What the demo shows

- 90 days of synthetic ride activities (power + HR streams, TSS, perceived effort)
- FTP history across three test entries
- Fatigue dashboard (CTL/ATL/TSB chart, power profile)
- Training calendar with 4 weeks of upcoming workouts
- Difficulty predictions per workout

### What the demo user can do

Everything a real user can — rate efforts, edit FTP, schedule workouts, update
their profile, connect Strava. Changes are real and visible immediately.
The `setup_demo` cron job wipes and re-seeds everything hourly, so no cleanup
is needed.

## Architecture

See inline docstrings. Key files:

```
apps/fatigue/banister.py   — pure CTL/ATL/TSB engine (no Django)
apps/fatigue/power.py      — power curves, FTP estimation (no Django)
apps/fatigue/hr.py         — HR-based TSS, effort, FTP adjustment (no Django)
apps/difficulty/predict.py — difficulty probability distribution (no Django)
apps/fatigue/queries.py    — only file in fatigue/ that imports from other apps
apps/scheduler/queries.py  — only file in scheduler/ that imports from other apps
apps/accounts/middleware.py — DemoModeMiddleware
apps/accounts/management/commands/setup_demo.py — demo seeder
```
