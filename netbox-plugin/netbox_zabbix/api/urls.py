from django.urls import path

from .views import AwxInventoryView

urlpatterns = [
    path("awx-inventory/", AwxInventoryView.as_view(), name="awx-inventory"),
]
