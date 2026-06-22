from django.urls import path

from . import views

urlpatterns = [
    path("download/<int:pk>/<str:fmt>/", views.download_workout, name="download_workout"),
]
