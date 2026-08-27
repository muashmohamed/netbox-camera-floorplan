import django_tables2 as tables
from django.utils.html import format_html, format_html_join

from netbox.tables import ActionsColumn, NetBoxTable

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeTable(NetBoxTable):
    name = tables.Column(linkify=True)
    category = tables.Column()
    icon_preview = tables.Column(empty_values=(), orderable=False, verbose_name="Icon")
    swatch = tables.Column(empty_values=(), orderable=False, verbose_name="Color", accessor="color")

    class Meta(NetBoxTable.Meta):
        model = CameraType
        fields = ("pk", "id", "name", "category", "icon_preview", "swatch", "fov_degrees", "description", "tags")
        default_columns = ("name", "category", "icon_preview", "swatch", "fov_degrees", "description")

    def render_category(self, value, record):
        return record.get_category_display()

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


def _render_reachability_summary_badges(summary, empty_label="No devices"):
    """
    Shared badge-rendering logic for a reachability summary dict (as
    returned by FloorPlan.get_reachability_summary() or its camera-scoped
    counterpart) — used by both FloorPlanTable and CCTVFloorPlanTable so
    the visual logic never drifts out of sync between the two.
    """
    if summary["total"] == 0:
        return format_html('<span class="text-muted">{}</span>', empty_label)

    # Show every issue that actually applies, not just the highest
    # priority one — an earlier version only ever showed one badge,
    # which silently hid a "no IP" device whenever an "unreachable"
    # device also existed on the same floor plan.
    issues = []
    if summary["unreachable"] > 0:
        issues.append(("red", f"{summary['unreachable']} unreachable"))
    if summary["no_ip"] > 0:
        issues.append(("orange", f"{summary['no_ip']} no IP"))

    if issues:
        return format_html_join(" ", '<span class="badge text-bg-{}">{}</span>', issues)
    if summary["reachable"] == summary["total"]:
        return format_html('<span class="badge text-bg-green">{}</span>', "All reachable")
    # Remaining case: some reachable, some "no_data" (has an IP, just
    # no monitoring result recorded yet) — neutral, not alarming.
    return format_html('<span class="badge text-bg-secondary">{}</span>', "No data")


class FloorPlanTable(NetBoxTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    camera_count = tables.Column(
        accessor="cameras__count", verbose_name="Devices", orderable=False
    )
    reachability = tables.Column(
        empty_values=(), orderable=False, verbose_name="Status",
        accessor="pk",  # dummy accessor; render_reachability does the real work
    )

    class Meta(NetBoxTable.Meta):
        model = FloorPlan
        fields = ("pk", "id", "name", "site", "location", "camera_count", "reachability", "tags")
        default_columns = ("name", "site", "location", "camera_count", "reachability")

    def render_reachability(self, record):
        return _render_reachability_summary_badges(record.get_reachability_summary())


class CCTVFloorPlanTable(NetBoxTable):
    """
    Read-only list of floor plans for restricted security staff — counts
    and status here are scoped to camera-category devices only, via
    FloorPlan.get_camera_count()/get_camera_reachability_summary(), and
    the name links to the read-only CCTV canvas view, not the editable
    one.
    """

    name = tables.Column(
        linkify=dict(viewname="plugins:netbox_camera_floorplan:cctv_floorplan", args=[tables.A("pk")])
    )
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    camera_count = tables.Column(
        empty_values=(), orderable=False, verbose_name="Cameras", accessor="pk",
    )
    reachability = tables.Column(
        empty_values=(), orderable=False, verbose_name="Status", accessor="pk",
    )
    # No edit/delete action buttons at all — this page must be genuinely
    # read-only, not just permission-blocked-if-clicked.
    actions = ActionsColumn(actions=())

    class Meta(NetBoxTable.Meta):
        model = FloorPlan
        fields = ("pk", "id", "name", "site", "location", "camera_count", "reachability")
        default_columns = ("name", "site", "location", "camera_count", "reachability")

    def render_camera_count(self, record):
        return record.get_camera_count()

    def render_reachability(self, record):
        return _render_reachability_summary_badges(
            record.get_camera_reachability_summary(), empty_label="No cameras"
        )


class CameraPlacementTable(NetBoxTable):
    device = tables.Column(linkify=True)
    floorplan = tables.Column(linkify=True)
    reachability = tables.Column(
        empty_values=(), orderable=False, verbose_name="Status", accessor="pk",
    )
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
            "reachability",
            "direction_degrees",
            "power_source_override",
            "tags",
        )
        default_columns = ("device", "floorplan", "camera_type", "reachability", "power_source_override")

    def render_reachability(self, record):
        status = record.get_reachability_status()
        if status == "reachable":
            return format_html('<span class="badge text-bg-green">{}</span>', "Reachable")
        if status == "unreachable":
            return format_html('<span class="badge text-bg-red">{}</span>', "Unreachable")
        if status == "no_ip":
            return format_html('<span class="badge text-bg-orange">{}</span>', "No IP")
        return format_html('<span class="text-muted">{}</span>', "No data")
