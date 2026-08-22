import django_tables2 as tables

from netbox.tables import NetBoxTable

from .models import CameraPlacement, FloorPlan


class FloorPlanTable(NetBoxTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    camera_count = tables.Column(
        accessor="cameras__count", verbose_name="Cameras", orderable=False
    )

    class Meta(NetBoxTable.Meta):
        model = FloorPlan
        fields = ("pk", "id", "name", "site", "location", "camera_count", "tags")
        default_columns = ("name", "site", "location", "camera_count")


class CameraPlacementTable(NetBoxTable):
    device = tables.Column(linkify=True)
    floorplan = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CameraPlacement
        fields = (
            "pk",
            "id",
            "device",
            "floorplan",
            "camera_type",
            "direction_degrees",
            "power_source_override",
            "tags",
        )
        default_columns = ("device", "floorplan", "camera_type", "direction_degrees", "power_source_override")
