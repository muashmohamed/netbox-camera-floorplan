import django_filters
from django.db.models import Q

from dcim.models import Location, Site, SiteGroup
from netbox.filtersets import NetBoxModelFilterSet

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = CameraType
        fields = ("id", "name", "slug", "category")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )


class FloorPlanFilterSet(NetBoxModelFilterSet):
    # Explicit _id filters (NetBox's standard naming convention) so the
    # Site Group -> Site -> Location cascading dropdowns in
    # FloorPlanFilterForm bind to the right query parameters.
    site_group_id = django_filters.ModelMultipleChoiceFilter(
        field_name="site__group",
        queryset=SiteGroup.objects.all(),
        label="Site Group",
    )
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
    # These reach through the floorplan relationship, since CameraPlacement
    # doesn't have Site/Location fields of its own.
    site_group_id = django_filters.ModelMultipleChoiceFilter(
        field_name="floorplan__site__group",
        queryset=SiteGroup.objects.all(),
        label="Site Group",
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name="floorplan__site",
        queryset=Site.objects.all(),
        label="Site",
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name="floorplan__location",
        queryset=Location.objects.all(),
        label="Location",
    )
    # is_placed isn't a real database column (it's a Python property
    # derived from x_pct/y_pct being null or not), so it needs an
    # explicit BooleanFilter with a custom method rather than the
    # automatic Meta.fields machinery, which only works on actual fields.
    is_placed = django_filters.BooleanFilter(
        method="filter_is_placed",
        label="Placed on canvas",
    )
    # Same "isn't a real column" situation as is_placed: "needs an NVR"
    # means camera-category AND connected_nvr is null. Non-camera types
    # (NVR/switch/AP/etc.) never "need" one, so they're excluded from
    # both sides of this filter rather than counted as satisfying either.
    needs_nvr = django_filters.BooleanFilter(
        method="filter_needs_nvr",
        label="Needs NVR assignment",
    )

    class Meta:
        model = CameraPlacement
        fields = ("id", "floorplan", "device", "camera_type", "connected_nvr")

    def filter_is_placed(self, queryset, name, value):
        if value:
            return queryset.filter(x_pct__isnull=False, y_pct__isnull=False)
        return queryset.filter(Q(x_pct__isnull=True) | Q(y_pct__isnull=True))

    def filter_needs_nvr(self, queryset, name, value):
        camera_without_nvr = Q(camera_type__category=CameraType.CATEGORY_CAMERA, connected_nvr__isnull=True)
        if value:
            return queryset.filter(camera_without_nvr)
        return queryset.exclude(camera_without_nvr)

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value) | Q(notes__icontains=value)
        )
