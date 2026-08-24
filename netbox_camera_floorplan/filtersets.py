import django_filters
from django.db.models import Q

from dcim.models import Location, Site
from netbox.filtersets import NetBoxModelFilterSet

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = CameraType
        fields = ("id", "name", "slug")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )


class FloorPlanFilterSet(NetBoxModelFilterSet):
    # Explicit _id filters (NetBox's standard naming convention) so the
    # Site -> Location cascading dropdowns in FloorPlanFilterForm bind to
    # the right query parameters.
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name="site",
        queryset=Site.objects.all(),
        label="Site",
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name="location",
        queryset=Location.objects.all(),
        label="Location",
    )

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
        fields = ("id", "floorplan", "device", "camera_type")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value) | Q(notes__icontains=value)
        )
