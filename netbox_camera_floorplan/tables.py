import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from netbox.tables import ActionsColumn, NetBoxTable

from .models import CameraPlacement, CameraType, EquipmentCategory, FloorPlan


class EquipmentCategoryTable(NetBoxTable):
    name = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = EquipmentCategory
        fields = ("pk", "id", "name", "is_camera", "is_hub", "slot_label_format", "description", "tags")
        default_columns = ("name", "is_camera", "is_hub", "slot_label_format", "description")


class CameraTypeTable(NetBoxTable):
    name = tables.Column(linkify=True)
    category = tables.Column()
    device_type = tables.Column(linkify=True, verbose_name="NetBox Device Type")
    icon_preview = tables.Column(empty_values=(), orderable=False, verbose_name="Icon")
    swatch = tables.Column(empty_values=(), orderable=False, verbose_name="Color", accessor="color")

    class Meta(NetBoxTable.Meta):
        model = CameraType
        fields = ("pk", "id", "name", "category", "device_type", "icon_preview", "swatch", "fov_degrees", "channel_capacity", "description", "tags")
        default_columns = ("name", "category", "device_type", "icon_preview", "swatch", "fov_degrees", "channel_capacity", "description")

    def render_category(self, value, record):
        return str(value) if value else "—"

    def render_device_type(self, value, record):
        return str(value) if value else "—"

    def render_fov_degrees(self, value, record):
        # Stored value is meaningless for non-camera types (only the
        # camera-cone drawing code on the canvas reads it, already gated
        # on is_camera) — show that plainly instead of a confusing 90°
        # default that was never actually configured for this type.
        # Deliberately not adding a "°" suffix here, to avoid changing
        # the format of already-working camera rows — the column header
        # already says "(°)".
        return value if record.is_camera else "—"

    def render_channel_capacity(self, value, record):
        # channel_capacity is a plain integer now (not a choices field),
        # so `value` is already the raw number — only meaningful for hub
        # categories (NVR, Access Control).
        if not value or not record.is_hub:
            return "—"
        return str(value)

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


def _render_reachability_summary_badges(summary):
    """
    Shared badge-rendering logic for a reachability summary dict (as
    returned by FloorPlan.get_reachability_summary() or its camera-scoped
    counterpart get_camera_reachability_summary()) — used by both
    FloorPlanTable and CCTVFloorPlanTable so the visual logic never
    drifts out of sync between the two.
    """
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
    Read-only, camera-only counterpart to FloorPlanTable — same shape,
    but its "name" link goes to the restricted read-only canvas (not the
    editable one), its device count and status badges are computed from
    camera-category placements only (get_camera_reachability_summary(),
    not get_reachability_summary()), and there are no action buttons at
    all (not even a permission-gated one — the column itself is empty).
    """

    name = tables.Column()
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    camera_count = tables.Column(
        empty_values=(), orderable=False, verbose_name="Cameras", accessor="pk",
    )
    reachability = tables.Column(
        empty_values=(), orderable=False, verbose_name="Status", accessor="pk",
    )
    actions = ActionsColumn(actions=())

    class Meta(NetBoxTable.Meta):
        model = FloorPlan
        fields = ("pk", "id", "name", "site", "location", "camera_count", "reachability")
        default_columns = ("name", "site", "location", "camera_count", "reachability")

    def render_name(self, record):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("plugins:netbox_camera_floorplan:cctv_floorplan", args=[record.pk]),
            record.name,
        )

    def render_camera_count(self, record):
        return record.get_camera_reachability_summary()["total"]

    def render_reachability(self, record):
        return _render_reachability_summary_badges(record.get_camera_reachability_summary())


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
    connected_hub = tables.Column(verbose_name="Connected Hub", empty_values=())
    channel = tables.Column(
        empty_values=(), orderable=False, accessor="hub_slot",
    )
    setup_status = tables.Column(
        empty_values=(), orderable=False, verbose_name="Setup", accessor="pk",
    )
    # "edit" here is deliberately scoped to Device Type ONLY (see
    # CameraPlacementDeviceTypeForm) — position (x/y), direction, and
    # hub/slot still can't be set meaningfully from a blind list-page
    # form, those stay canvas-only. Device Type has no such visual
    # requirement, so it gets a fast path for clearing a "Needs Device
    # Type" Setup warning without hunting down the actual floor plan.
    actions = ActionsColumn(actions=("edit", "delete"))

    class Meta(NetBoxTable.Meta):
        model = CameraPlacement
        fields = (
            "pk",
            "id",
            "device",
            "floorplan",
            "camera_type",
            "setup_status",
            "placed",
            "reachability",
            "connected_hub",
            "channel",
            "direction_degrees",
            "power_source_override",
            "tags",
        )
        default_columns = ("device", "floorplan", "camera_type", "setup_status", "placed", "reachability", "connected_hub", "channel", "power_source_override")

    def render_setup_status(self, record):
        # mark_safe, not format_html: every branch here is a fully
        # static or pre-escaped string with no {}-based interpolation,
        # and format_html requires at least one positional/keyword arg
        # even when the format string has no placeholders to fill —
        # calling it with zero args raises TypeError("args or kwargs
        # must be provided") regardless of whether interpolation is
        # actually needed.
        missing = []
        device = record.device

        # What floor plan SHOULD this placement point to, given the
        # device's CURRENT Location right now — not whatever it was
        # when this placement was first created. The auto-create signal
        # only ever fires for a device with no placement yet, so if the
        # device's Location changes afterward, nothing currently updates
        # this placement's floorplan to match — it silently goes stale.
        # This check is what surfaces that instead of hiding it.
        #
        # When device.location_id is None, there's nothing specific to
        # compare against — an unset Location isn't a location that
        # CONTRADICTS the placement's floor plan, there's simply no data
        # to check. In that case only the Site is verified (a real,
        # correctly hand-placed device shouldn't get flagged "stale"
        # just because its Location field happens to be blank in DCIM —
        # that's an incomplete-data situation, not a mismatch).
        is_stale = False
        if device.location_id:
            expected = FloorPlan.objects.filter(site_id=device.site_id, location_id=device.location_id).first()
            expected_floorplan_id = expected.pk if expected else None
            is_stale = record.floorplan_id != expected_floorplan_id
        elif record.floorplan_id and record.floorplan.site_id != device.site_id:
            is_stale = True

        if is_stale:
            missing.append(
                "this device's Location has changed since it was placed — its placement "
                "still points at the old floor plan (or none at all); review and re-place "
                "it if the new location is where it actually belongs"
            )
        elif record.floorplan_id is None:
            missing.append("no floor plan exists yet for this device's Location")

        if not record.camera_type_id:
            missing.append("no plugin Device Type is mapped to this device's hardware type")

        if not missing:
            return mark_safe(
                '<span class="text-success" title="Floor plan and Device Type are both set — everything needed to place this is ready">✓ Ready</span>'
            )
        tooltip = "; ".join(missing).replace('"', "&quot;")
        return mark_safe(
            f'<span class="text-warning" title="{tooltip}">⚠ Needs attention</span>'
        )

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
        if record.floorplan_id is None:
            # No floor plan exists yet for this device's Location at all
            # — nothing to open or click toward yet. Distinct from the
            # normal "Unplaced" state (floor plan exists, just no x/y
            # set), which is why this isn't just an early return of that
            # same badge — the Setup column already explains the "why"
            # in more detail; this stays a quick visual flag.
            return format_html('<span class="badge text-bg-secondary">{}</span>', "No floor plan")
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

    def render_connected_hub(self, value, record):
        if value:
            return format_html('<a href="{}">{}</a>', value.get_absolute_url(), str(value))
        if record.camera_type and record.camera_type.is_camera:
            return format_html(
                '<span class="badge text-bg-orange" title="This camera isn\'t linked to any NVR/hub yet">{}</span>',
                "Needs NVR",
            )
        # Not a camera (hub/switch/AP/etc.) — the field genuinely doesn't
        # apply, so no badge, just the same blank dash as any other N/A cell.
        return "—"

    def render_channel(self, record):
        if record.camera_type and record.camera_type.is_hub:
            usage = record.get_hub_slot_usage()
            if usage:
                return format_html(
                    '<span title="{} of {} slots used">{}/{} used</span>',
                    usage["used"], usage["capacity"], usage["used"], usage["capacity"],
                )
            return "—"  # hub type with no channel_capacity configured
        return record.get_hub_slot_label() or "—"
