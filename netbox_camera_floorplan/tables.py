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
        fields = ("pk", "id", "name", "category", "icon_preview", "swatch", "fov_degrees", "channel_capacity", "description", "tags")
        default_columns = ("name", "category", "icon_preview", "swatch", "fov_degrees", "channel_capacity", "description")

    def render_category(self, value, record):
        return record.get_category_display()

    def render_fov_degrees(self, value, record):
        # Stored value is meaningless for non-camera types (only the
        # camera-cone drawing code on the canvas reads it, already gated
        # on is_camera) — show that plainly instead of a confusing 90°
        # default that was never actually configured for this type.
        # Deliberately not adding a "°" suffix here, to avoid changing
        # the format of already-working camera rows — the column header
        # already says "(°)".
        return value if record.is_camera else "—"

    def render_channel_capacity(self, value):
        # `value` here is already the human label from CHANNEL_CAPACITY_CHOICES
        # ("8 channels", not the raw int 8) — django-tables2 renders
        # choice-field columns via their display label automatically, so
        # appending " channels" again produced "8 channels channels".
        return value if value else "—"

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
        summary = record.get_reachability_summary()
        if summary["total"] == 0:
            return format_html('<span class="text-muted">{}</span>', "No devices")

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
            return format_html_join(
                " ", '<span class="badge text-bg-{}">{}</span>', issues
            )
        if summary["reachable"] == summary["total"]:
            return format_html('<span class="badge text-bg-green">{}</span>', "All reachable")
        # Remaining case: some reachable, some "no_data" (has an IP, just
        # no monitoring result recorded yet) — neutral, not alarming.
        return format_html('<span class="badge text-bg-secondary">{}</span>', "No data")


class CameraPlacementTable(NetBoxTable):
    device = tables.Column(linkify=True)
    floorplan = tables.Column(linkify=True)
    reachability = tables.Column(
        empty_values=(), orderable=False, verbose_name="Status", accessor="pk",
    )
    placed = tables.Column(
        empty_values=(), orderable=False, verbose_name="Placed",
        accessor="pk",  # dummy; render_placed does the real work
    )
    connected_nvr = tables.Column(verbose_name="Connected NVR", empty_values=())
    channel = tables.Column(
        empty_values=(), orderable=False, accessor="nvr_channel",
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
            "placed",
            "reachability",
            "connected_nvr",
            "channel",
            "direction_degrees",
            "power_source_override",
            "tags",
        )
        default_columns = ("device", "floorplan", "camera_type", "placed", "reachability", "connected_nvr", "channel", "power_source_override")

    def render_reachability(self, record):
        status = record.get_reachability_status()
        if status == "reachable":
            return format_html('<span class="badge text-bg-green">{}</span>', "Reachable")
        if status == "unreachable":
            return format_html('<span class="badge text-bg-red">{}</span>', "Unreachable")
        if status == "no_ip":
            return format_html('<span class="badge text-bg-orange">{}</span>', "No IP")
        return format_html('<span class="text-muted">{}</span>', "No data")

    def render_placed(self, record):
        url = record.floorplan.get_absolute_url()
        if record.is_placed:
            return format_html(
                '<a href="{}" class="btn btn-xs text-bg-green" title="Open on the floor plan canvas">{}</a>',
                url, "Placed",
            )
        return format_html(
            '<a href="{}" class="btn btn-xs text-bg-orange" title="Needs a canvas click to set its position">{}</a>',
            url, "Unplaced",
        )

    def render_connected_nvr(self, value, record):
        if value:
            return format_html('<a href="{}">{}</a>', value.get_absolute_url(), str(value))
        if record.camera_type and record.camera_type.is_camera:
            return format_html(
                '<span class="badge text-bg-orange" title="This camera isn\'t linked to any NVR/channel yet">{}</span>',
                "Needs NVR",
            )
        # Not a camera (NVR/switch/AP/etc.) — the field genuinely doesn't
        # apply, so no badge, just the same blank dash as any other N/A cell.
        return "—"

    def render_channel(self, record):
        if record.camera_type and record.camera_type.is_nvr:
            usage = record.get_nvr_channel_usage()
            if usage:
                return format_html(
                    '<span title="{} of {} channels used">{}/{} used</span>',
                    usage["used"], usage["capacity"], usage["used"], usage["capacity"],
                )
            return "—"  # NVR type with no channel_capacity configured
        return record.get_channel_label() or "—"
