import django_filters
from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet

from .models import CameraPlacement, FloorPlan


class FloorPlanFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = FloorPlan
        fields = ("id", "name", "site", "location")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(comments__icontains=value)
        )


class CameraPlacementFilterSet(NetBoxModelFilterSet):
    floorplan_id = django_filters.NumberFilter(field_name="floorplan_id")

    class Meta:
        model = CameraPlacement
        fields = ("id", "floorplan", "device")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value) | Q(notes__icontains=value)
        )
