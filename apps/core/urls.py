from django.urls import path

from apps.core.views import HealthView

urlpatterns = [
    path("", HealthView.as_view(), name="health"),
]
