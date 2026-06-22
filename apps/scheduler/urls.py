from django.urls import path

from . import views

urlpatterns = [
    path("", views.calendar_view, name="calendar"),
    path("api/events/", views.calendar_events_api, name="calendar_events_api"),
    path("api/add/", views.add_workout, name="add_workout"),
    path("api/move/<int:pk>/", views.move_workout, name="move_workout"),
    path("api/delete/<int:pk>/", views.delete_workout, name="delete_workout"),
    path("api/toggle/<int:pk>/", views.toggle_complete, name="toggle_complete"),
    path("populate/", views.populate_from_plan, name="populate_from_plan"),
]
