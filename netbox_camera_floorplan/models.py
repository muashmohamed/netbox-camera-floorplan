from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse

from dcim.models import Device, DeviceType, Location, Site
from netbox.models import NetBoxModel


class FloorPlan(NetBoxModel):
    """
    A single floor plan image (e.g. exported from AutoCAD) tied to a Site,
    optionally narrowed to a specific Location within that site.
    """

    name = models.CharField(max_length=100)
    site = models.ForeignKey(
        to=Site,
        on_delete=models.CASCADE,
        related_name="camera_floorplans",
    )
    location = models.ForeignKey(
        to=Location,
        on_delete=models.CASCADE,
        related_name="camera_floorplans",
        blank=True,
        null=True,
        help_text="Optional: narrow this floor plan to a specific location within the site.",
    )
    image = models.ImageField(
        upload_to="camera_floorplans/",
        help_text="Floor plan image (PNG/JPG export from AutoCAD or similar).",
    )
    comments = models.TextField(blank=True)

    def __str__(self):
        if self.location:
            return f"{self.site.name} / {self.location.name} / {self.name}"
        return f"{self.site.name} / {self.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_camera_floorplan:floorplan", args=[self.pk])

    def get_reachability_summary(self):
        """
        Quick-triage counts for the Floor Plans list: how many placements
        on this floor plan are reachable/unreachable/no_ip/no_data, per
        CameraPlacement.get_reachability_status(). Reuses that method
        (not a separate implementation) so this summary and the
        per-placement badges on the Device Placements list never
        disagree with each other.

        Callers building a list of many FloorPlans should select_related
        "cameras__device" first (or otherwise ensure it's prefetched) —
        this method itself doesn't add prefetching, since doing so on
        every call would defeat prefetching done once across a whole
        queryset upstream.
        """
        counts = {"total": 0, "reachable": 0, "unreachable": 0, "no_ip": 0, "no_data": 0}
        for placement in self.cameras.all():
            counts["total"] += 1
            counts[placement.get_reachability_status()] += 1
        return counts

    def get_camera_reachability_summary(self):
        """
        Same as get_reachability_summary(), but scoped to camera-category
        placements only — used by the restricted CCTV Floor Plans list,
        which should never reflect or leak counts for switches/APs/UPS/
        NVRs even in aggregate.
        """
        counts = {"total": 0, "reachable": 0, "unreachable": 0, "no_ip": 0, "no_data": 0}
        for placement in self.cameras.all():
            if not placement.camera_type or not placement.camera_type.is_camera:
                continue
            counts["total"] += 1
            counts[placement.get_reachability_status()] += 1
        return counts

    class Meta:
        ordering = ["site__name", "location__name", "name"]
        verbose_name = "Device Floor Plan"
        verbose_name_plural = "Device Floor Plans"
        permissions = [
            (
                # Deliberately NOT "view_cctv_floorplan" here — NetBox's
                # permission system automatically appends "_floorplan"
                # (the model name) when constructing the actual
                # has_perm()-checkable string. Including that suffix in
                # the codename itself produced a doubled
                # "view_cctv_floorplan_floorplan" in practice (confirmed
                # via user.get_all_permissions() in a live shell) that
                # never matched what permission_required actually checks
                # for. Omitting it here lets NetBox's automatic
                # single-appending produce the correct final string:
                # "netbox_camera_floorplan.view_cctv_floorplan".
                "view_cctv",
                "Can view read-only CCTV camera floor plans",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "location", "name"],
                name="unique_floorplan_per_site_location_name",
            )
        ]


class EquipmentCategory(NetBoxModel):
    """
    An admin-editable equipment category — replaces what used to be a
    hardcoded Python choices list (CATEGORY_CHOICES on CameraType).
    Adding a brand-new equipment type (e.g. "Fire Alarm Panel" someday)
    becomes a plain "Add" click here, not a code change/migration/
    redeploy cycle.

    `is_hub` and `slot_label_format` are what let this same category
    system cover both simple standalone devices (Access Point, Switch,
    UPS — is_hub=False) and capacity-limited hub devices (NVR, Access
    Control panels — is_hub=True), reusing one shared mechanism
    (CameraPlacement.connected_hub / hub_slot) instead of duplicating
    the whole channel/capacity/locked-picker/usage-tracking/delete-
    warning feature set for every new hub-like category that comes up.
    """

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    is_camera = models.BooleanField(
        default=False,
        verbose_name="is a camera",
        help_text="Enables Direction and Field of View (the coverage cone) — meaningless for non-camera equipment.",
    )
    is_hub = models.BooleanField(
        default=False,
        verbose_name="is a hub (has capacity/slots)",
        help_text=(
            "Enables channel/slot capacity, a locked slot picker on connected devices, "
            "live usage tracking, and a delete-time warning listing anything connected to it. "
            "Examples: NVR (video channels), Access Control panel (door slots). "
            "Leave unchecked for simple standalone equipment (Access Point, Switch, UPS, Panic Button)."
        ),
    )
    slot_label_format = models.CharField(
        max_length=20,
        blank=True,
        default="{n}",
        help_text=(
            'Only used when "is a hub" is checked. A template for how slot numbers are '
            'displayed — {n} is replaced with the slot number. Examples: "D{n}" for NVR '
            'channels (shows "D1", "D2"...), "Door {n}" for Access Control (shows "Door 1", '
            '"Door 2"...).'
        ),
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Equipment Category"
        verbose_name_plural = "Equipment Categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_camera_floorplan:equipmentcategory_list")

    def format_slot_label(self, slot_number):
        """Returns e.g. "D5" or "Door 5" for slot_number=5, per this
        category's own slot_label_format — or just the plain number if
        no format is set (or this isn't a hub category at all)."""
        if not self.is_hub or slot_number is None:
            return None
        template = self.slot_label_format or "{n}"
        try:
            return template.format(n=slot_number)
        except (KeyError, IndexError):
            # A malformed format string (e.g. missing {n}) shouldn't
            # break the whole page — fall back to the plain number.
            return str(slot_number)


class CameraType(NetBoxModel):
    """
    A manageable device type (e.g. Dome, PTZ, Bullet, Fisheye, AP,
    Switch...) with its own icon, marker color, and category. Displayed
    in the UI as "Device Type" — kept as CameraType internally since
    this plugin started camera-only, and NetBox core already has its own
    unrelated DeviceType model (hardware/rack specs) that this must not
    be confused with.

    `category` is a ForeignKey to EquipmentCategory (an admin-editable
    table — see that model's docstring), not a hardcoded choices field.
    It determines which fields actually apply: direction and
    field-of-view (the coverage cone) only make sense for cameras, and
    channel/slot capacity only makes sense for hub categories (NVR,
    Access Control) — an access point or a switch doesn't have either.
    """

    PRESET_DOME = "dome"
    PRESET_PTZ = "ptz"
    PRESET_BULLET = "bullet"
    PRESET_FISHEYE = "fisheye"
    PRESET_AP = "ap"
    PRESET_ACCESS_CONTROL = "access_control"
    PRESET_SWITCH = "switch"
    PRESET_UPS = "ups"
    PRESET_SERVER = "server"
    PRESET_ROUTER = "router"
    PRESET_FIREWALL = "firewall"
    PRESET_NVR = "nvr"
    PRESET_ONT = "ont"
    PRESET_MODEM = "modem"
    PRESET_GENERIC = "generic"
    PRESET_CHOICES = [
        ("", "None (use color swatch only)"),
        (PRESET_DOME, "Dome camera (built-in)"),
        (PRESET_PTZ, "PTZ camera (built-in)"),
        (PRESET_BULLET, "Bullet camera (built-in)"),
        (PRESET_FISHEYE, "Fisheye camera (built-in)"),
        (PRESET_AP, "Access Point (built-in)"),
        (PRESET_ACCESS_CONTROL, "Access Control (built-in)"),
        (PRESET_SWITCH, "Switch (built-in)"),
        (PRESET_UPS, "UPS (built-in)"),
        (PRESET_SERVER, "Server (built-in)"),
        (PRESET_ROUTER, "Router (built-in)"),
        (PRESET_FIREWALL, "Firewall (built-in)"),
        (PRESET_NVR, "NVR (built-in)"),
        (PRESET_ONT, "ONT (built-in)"),
        (PRESET_MODEM, "Modem (built-in)"),
        (PRESET_GENERIC, "Generic device (built-in)"),
    ]
    # Maps each built-in preset icon to the slug of the EquipmentCategory
    # it should suggest when picked (e.g. picking the AP icon suggests
    # the "Access Point" category) — used by the edit-form JS. Kept here,
    # next to PRESET_CHOICES, so the two lists are edited together.
    PRESET_SUGGESTED_CATEGORY_SLUG = {
        PRESET_DOME: "camera",
        PRESET_BULLET: "camera",
        PRESET_PTZ: "camera",
        PRESET_FISHEYE: "camera",
        PRESET_AP: "ap",
        PRESET_ACCESS_CONTROL: "access_control",
        PRESET_SWITCH: "switch",
        PRESET_UPS: "ups",
        PRESET_SERVER: "server",
        PRESET_ROUTER: "router",
        PRESET_FIREWALL: "firewall",
        PRESET_NVR: "nvr",
        PRESET_ONT: "ont",
        PRESET_MODEM: "modem",
        PRESET_GENERIC: "camera",
    }

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    category = models.ForeignKey(
        to="EquipmentCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=False,
        related_name="camera_types",
        help_text=(
            "Determines which fields apply — Direction and Field of View "
            "(the coverage cone) are Camera-only, and channel/slot capacity "
            "is Hub-only (NVR, Access Control) — hidden otherwise, since "
            "they don't apply to an AP, switch, or UPS."
        ),
    )
    preset_icon = models.CharField(
        max_length=20,
        blank=True,
        choices=PRESET_CHOICES,
        help_text="Pick a built-in icon, or leave blank and upload your own below.",
    )
    icon_image = models.ImageField(
        upload_to="camera_floorplan_icons/",
        blank=True,
        null=True,
        help_text="Optional: upload your own icon (PNG/SVG, ~32x32). Overrides the built-in preset if set.",
    )
    color = models.CharField(
        max_length=7,
        default="#f2a65a",
        help_text="Hex color used for the marker ring and (for cameras) direction cone (e.g. #f2a65a).",
    )
    fov_degrees = models.PositiveSmallIntegerField(
        default=90,
        verbose_name="field of view (°)",
        validators=[MinValueValidator(1), MaxValueValidator(360)],
        help_text=(
            "Camera only — ignored for every other category. Horizontal "
            "field of view in degrees, used to draw the coverage cone on "
            "the floor plan. Real-world fixed-lens cameras typically run "
            "90-120° for Dome and 70-110° for Bullet; PTZ varies hugely "
            "with zoom (as narrow as ~5° zoomed in, ~55-90° zoomed out) — "
            "60° is a reasonable default representing a moderately zoomed-out "
            "view. Fisheye cameras are commonly 180° (hemispherical) up to "
            "360° (full panoramic) — values of 170° or more render as a full "
            "circle around the marker instead of a triangle, since a cone "
            "shape can't represent that much coverage. Adjust per your "
            "actual hardware's spec sheet if known."
        ),
    )
    description = models.CharField(max_length=200, blank=True)

    channel_capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="channel/slot capacity",
        help_text=(
            "Hub categories only (e.g. NVR, Access Control) — ignored for "
            "every other category. The maximum number of devices this hub "
            "can connect (e.g. a 32-channel NVR accepts up to 32 cameras; "
            "a 4-door Access Control panel accepts up to 4 reader/button "
            "devices). Enter the exact number for your actual hardware — "
            "no preset list to run out of."
        ),
    )
    device_type = models.ForeignKey(
        to="dcim.DeviceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="NetBox Device Type",
        help_text=(
            "Optional: link this to the real NetBox hardware type (manufacturer/model) "
            "this entry represents. One-time setup per Device Type — once set, any "
            "NetBox device using that hardware type automatically suggests this entry "
            "when placing it (icon, category, capacity all apply without re-picking "
            "them by hand). Leave blank if this entry doesn't correspond to one "
            "specific real hardware model, or if several plugin types share the same "
            "generic placeholder hardware type — matching stays ambiguous either way, "
            "so nothing auto-selects until it's set."
        ),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Device Type"
        verbose_name_plural = "Device Types"

    @property
    def is_camera(self):
        return bool(self.category and self.category.is_camera)

    @property
    def is_hub(self):
        return bool(self.category and self.category.is_hub)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_camera_floorplan:cameratype_list")

    def get_icon_url(self):
        """
        Custom uploaded icon takes priority; otherwise fall back to the
        chosen built-in preset; otherwise None (marker falls back to a
        plain color dot).
        """
        if self.icon_image:
            return self.icon_image.url
        if self.preset_icon:
            return static(f"netbox_camera_floorplan/icons/{self.preset_icon}.svg")
        return None


class CameraPlacement(NetBoxModel):
    """
    A single device's pinned position on a FloorPlan (camera, AP, access
    control, switch, UPS...). Deliberately does NOT duplicate uplink
    switch/port or power source as separate text fields — that data
    already lives on the linked Device's real interfaces, cables, and
    power ports in NetBox core, and is looked up live for display so it
    can never drift out of sync with the source of truth.
    """

    POWER_UNKNOWN = ""
    POWER_POE = "poe"
    POWER_ADAPTER = "adapter"
    POWER_CHOICES = [
        (POWER_UNKNOWN, "Unset"),
        (POWER_POE, "PoE (via switch)"),
        (POWER_ADAPTER, "External power adapter"),
    ]

    floorplan = models.ForeignKey(
        to=FloorPlan,
        on_delete=models.CASCADE,
        related_name="cameras",
    )
    device = models.ForeignKey(
        to=Device,
        on_delete=models.CASCADE,
        related_name="floorplan_placements",
        help_text="The existing NetBox device being placed on the floor plan.",
    )
    camera_type = models.ForeignKey(
        to=CameraType,
        on_delete=models.SET_NULL,
        related_name="placements",
        null=True,
        blank=True,
        verbose_name="device type",
        help_text="Placement type, used to pick the marker icon on the floor plan.",
    )
    x_pct = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "Horizontal position as a percentage of image width (0-100). "
            "Left blank for a device added via CSV import — it appears in "
            "the floor plan's \"Unplaced devices\" list until someone "
            "manually clicks it onto the canvas."
        ),
    )
    y_pct = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Vertical position as a percentage of image height (0-100). Left blank until manually placed.",
    )
    direction_degrees = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(359)],
        help_text="Facing direction in degrees (0-359), clockwise from up.",
    )
    # Manual fallback only — if a monitoring plugin (e.g. netbox-ping) is
    # configured to write to a custom field on Device, that field is
    # preferred for display. This stays as a lightweight override/note.
    power_source_override = models.CharField(
        max_length=10,
        choices=POWER_CHOICES,
        blank=True,
        default=POWER_UNKNOWN,
        help_text=(
            "Manual note only. If the device has real PowerPort connections "
            "in NetBox, those are shown instead."
        ),
    )
    notes = models.TextField(blank=True)
    connected_hub = models.ForeignKey(
        to="self",
        on_delete=models.SET_NULL,
        related_name="connected_devices",
        null=True,
        blank=True,
        verbose_name="connected hub",
        help_text=(
            "The hub device (Device Type category with \"is a hub\" enabled "
            "— e.g. NVR, Access Control panel) this device connects into. "
            "Only already-placed hubs can be selected — place the hub "
            "itself first."
        ),
    )
    hub_slot = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="hub slot",
        help_text=(
            "Slot/channel number on the connected hub (e.g. NVR channel, "
            "Access Control door/reader slot) — labeled per that hub's own "
            "Device Type category (e.g. \"D1\", \"Door 1\")."
        ),
    )

    class Meta:
        ordering = ["floorplan__site__name", "floorplan__location__name", "floorplan__name", "device__name"]
        verbose_name = "Device Placement"
        verbose_name_plural = "Device Placements"
        constraints = [
            models.UniqueConstraint(
                fields=["device"],
                name="unique_device_placement",
            ),
            models.UniqueConstraint(
                fields=["connected_hub", "hub_slot"],
                condition=models.Q(connected_hub__isnull=False),
                name="unique_hub_slot_assignment",
            ),
        ]

    def __str__(self):
        return f"{self.device.name} @ {self.floorplan.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_camera_floorplan:floorplan", args=[self.floorplan.pk])

    @property
    def is_placed(self):
        """
        False for a device added via CSV import that hasn't been dragged
        onto the canvas yet — it exists (floor plan, device, hub/slot
        assignment all already set) but has no x/y position.
        """
        return self.x_pct is not None and self.y_pct is not None

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        errors = {}

        if self.connected_hub_id and self.pk and self.connected_hub_id == self.pk:
            errors["connected_hub"] = "A device cannot be connected to itself as its hub."

        if self.connected_hub_id:
            hub_type = getattr(self.connected_hub, "camera_type", None)
            if not hub_type or not hub_type.is_hub:
                errors["connected_hub"] = (
                    "The selected device isn't a hub (its Device Type's category must "
                    "have \"is a hub\" enabled, e.g. NVR or Access Control)."
                )
            if self.hub_slot is None:
                errors.setdefault("hub_slot", "A slot number is required when connecting to a hub.")
            elif hub_type and hub_type.channel_capacity and self.hub_slot > hub_type.channel_capacity:
                errors["hub_slot"] = (
                    f"Slot {self.hub_slot} exceeds this hub's capacity "
                    f"({hub_type.channel_capacity})."
                )
            elif self.hub_slot is not None and self.hub_slot < 1:
                errors["hub_slot"] = "Slot number must be 1 or greater."
        elif self.hub_slot is not None:
            errors["hub_slot"] = "A slot number requires a connected hub to also be set."

        if errors:
            raise ValidationError(errors)

    def get_hub_slot_label(self):
        """
        Returns e.g. "D5" or "Door 5" for hub_slot=5, formatted per the
        CONNECTED HUB's own category's slot_label_format (not this
        placement's own category) — or None if unset.
        """
        if self.hub_slot is None:
            return None
        hub_type = getattr(self.connected_hub, "camera_type", None)
        hub_category = getattr(hub_type, "category", None)
        if hub_category:
            return hub_category.format_slot_label(self.hub_slot)
        return str(self.hub_slot)

    def get_hub_slot_usage(self):
        """
        For a placement whose own Device Type category is a hub (NVR,
        Access Control, ...): how many of its slots are currently claimed
        by devices pointing at it, out of its total capacity. Returns
        None if this placement isn't a hub or has no capacity configured.
        """
        if not self.camera_type or not self.camera_type.is_hub or not self.camera_type.channel_capacity:
            return None
        capacity = self.camera_type.channel_capacity
        used = self.connected_devices.count()
        return {"used": used, "capacity": capacity, "available": max(capacity - used, 0)}

    def get_hub_slot_assignments(self):
        """
        For a placement whose own Device Type category is a hub: which
        slot numbers are currently claimed and by which device — e.g.
        {3: "CAM-ENTRANCE-01", 5: "READER-DOOR-02"}. Used to build a slot
        picker that locks already-taken numbers instead of letting a
        second device silently collide with one (caught by the
        UniqueConstraint on save, but far better to prevent the pick in
        the first place). Returns {} if this placement isn't a hub.
        """
        if not self.camera_type or not self.camera_type.is_hub:
            return {}
        return {
            dev.hub_slot: dev.device.name
            for dev in self.connected_devices.select_related("device").exclude(hub_slot__isnull=True)
        }

    # ---- Live lookups against NetBox's own connection data ----

    def get_uplink_terminations(self):
        """
        Returns a list of (local_interface, remote_device, remote_interface)
        tuples for every cabled network interface on this device. This reads
        straight from NetBox's real cable data, never a stored copy.
        """
        results = []
        for interface in self.device.interfaces.all():
            if not interface.cable:
                continue
            peer = interface.link_peers
            for remote in peer:
                remote_device = getattr(remote, "device", None)
                results.append((interface, remote_device, remote))
        return results

    def get_power_terminations(self):
        """
        Returns a list of (power_port, remote_outlet_or_feed) for any real
        power connections on this device.
        """
        results = []
        for port in self.device.powerports.all():
            if port.cable:
                for remote in port.link_peers:
                    results.append((port, remote))
        return results

    def get_reachability(self):
        """
        Looks up a boolean custom field on the device (name configured via
        plugin settings) if a monitoring plugin like netbox-ping populates
        one. Returns True/False/None (None = not configured / unknown).
        Used by the floor plan canvas's green/red ring — kept as a plain
        3-value result since JS elsewhere checks it directly.
        """
        from django.conf import settings as django_settings

        field_name = django_settings.PLUGINS_CONFIG.get(
            "netbox_camera_floorplan", {}
        ).get("reachability_custom_field")
        if not field_name:
            return None
        return self.device.custom_field_data.get(field_name)

    def get_reachability_status(self):
        """
        A richer status for list-page display than get_reachability()
        alone provides — specifically distinguishes "no IP assigned" (an
        administrative gap: nobody's configured this device for
        monitoring yet) from "no data yet" (has an IP, a monitoring
        plugin just hasn't reported on it) and from a real, confirmed-down
        state. Conflating "no IP" with "unreachable" would create false
        alarms in the troubleshooting view for devices that were never
        actually tested.

        Returns one of: "reachable", "unreachable", "no_ip", "no_data".
        """
        if not self.device.primary_ip4_id:
            return "no_ip"
        result = self.get_reachability()
        if result is True:
            return "reachable"
        if result is False:
            return "unreachable"
        return "no_data"


@receiver(pre_delete, sender=CameraPlacement)
def clear_orphaned_hub_slot(sender, instance, **kwargs):
    """
    connected_hub uses on_delete=SET_NULL, which only clears that FK field
    on affected devices — it leaves hub_slot (a plain integer, not itself
    an FK) holding its old value, producing a confusing half-orphaned
    state: "Connected hub: —" next to "Hub slot: 5".

    A signal — rather than overriding this model's own delete() method —
    is what's needed here: BulkDeleteView and other bulk queryset.delete()
    paths skip custom delete() overrides entirely (a well-known Django
    gotcha), but Django still fires pre_delete/post_delete signals per
    row even during a bulk delete, so this stays correct regardless of
    whether the hub is removed via the single-row action or bulk delete.
    """
    if instance.camera_type_id and instance.camera_type.is_hub:
        instance.connected_devices.update(hub_slot=None)
