import django_tables2 as tables
from django.utils.html import format_html

from netbox.tables import ActionsColumn, NetBoxTable

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeTable(NetBoxTable):
    name = tables.Column(linkify=True)
    icon_preview = tables.Column(empty_values=(), orderable=False, verbose_name="Icon")
    swatch = tables.Column(empty_values=(), orderable=False, verbose_name="Color", accessor="color")

    class Meta(NetBoxTable.Meta):
        model = CameraType
        fields = ("pk", "id", "name", "icon_preview", "swatch", "fov_degrees", "description", "tags")
        default_columns = ("name", "icon_preview", "swatch", "fov_degrees", "description")

    def render_icon_preview(self, record):
        icon_url = record.get_icon_url()
        if icon_url:
            return format_html('<img src="{}" style="width:24px;height:24px;object-fit:contain;">', icon_url)
        return format_html('<span class="text-muted">{}</span>', '—')

    def render_swatch(self, value):
        return format_html(
            '<span style="display:inline-block;width:16px;height:16px;border-radius:3px;background:{};vertical-align:middle;"></span> {}',
            value, value,
        )


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
    # No "edit" action here on purpose — a placement's position (x/y) can
    # only be set meaningfully by clicking on the floor plan canvas, not
    # from a blind form. This list is for viewing/deleting only; to move
    # a camera, open its floor plan and drag/re-click it there.
    actions = ActionsColumn(actions=("delete",))

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
