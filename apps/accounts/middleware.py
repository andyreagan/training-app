"""
Demo mode middleware.

When the logged-in user is the demo account (username == settings.DEMO_USERNAME),
sets ``request.is_demo = True`` so the banner is shown.

That's it — demo users can do everything a real user can.
Data is reset by the ``setup_demo`` management command, run hourly via cron.
"""

import os

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")


class DemoModeMiddleware:
    """Tag demo sessions so the banner template variable is available."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_demo = request.user.is_authenticated and request.user.username == DEMO_USERNAME
        return self.get_response(request)
