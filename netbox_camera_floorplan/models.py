from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse

from dcim.models import Device, Location, Site
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

    class Meta:
        ordering = ["site__name", "location__name", "name"]
        verbose_name = "Device Floor Plan"
        verbose_name_plural = "Device Floor Plans"
        constraints = [
            models.UniqueConstraint(
                fields=["site", "location", "name"],
                name="unique_floorplan_per_site_location_name",
            )
        ]

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


class CameraType(NetBoxModel):
    """
    A manageable device type (e.g. Dome, PTZ, Bullet, Fisheye, AP,
    Switch...) with its own icon, marker color, and category. Displayed
    in the UI as "Device Type" — kept as CameraType internally since
    this plugin started camera-only, and NetBox core already has its own
    unrelated DeviceType model (hardware/rack specs) that this must not
    be confused with.

    The category determines which fields actually apply: direction and
    field-of-view (the coverage cone) only make sense for cameras — an
    access point or a switch doesn't have a "field of view."
    """

    CATEGORY_CAMERA = "camera"
    CATEGORY_AP = "ap"
    CATEGORY_ACCESS_CONTROL = "access_control"
    CATEGORY_SWITCH = "switch"
    CATEGORY_UPS = "ups"
    CATEGORY_SERVER = "server"
    CATEGORY_ROUTER = "router"
    CATEGORY_FIREWALL = "firewall"
    CATEGORY_NVR = "nvr"
    CATEGORY_ONT = "ont"
    CATEGORY_MODEM = "modem"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_CAMERA, "Camera"),
        (CATEGORY_AP, "Access Point"),
        (CATEGORY_ACCESS_CONTROL, "Access Control"),
        (CATEGORY_SWITCH, "Switch"),
        (CATEGORY_UPS, "UPS"),
        (CATEGORY_SERVER, "Server"),
        (CATEGORY_ROUTER, "Router"),
        (CATEGORY_FIREWALL, "Firewall"),
        (CATEGORY_NVR, "NVR"),
        (CATEGORY_ONT, "ONT"),
        (CATEGORY_MODEM, "Modem"),
        (CATEGORY_OTHER, "Other"),
    ]

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

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_CAMERA,
        help_text=(
            "Determines which fields apply — Direction and Field of View "
            "(the coverage cone) are Camera-only and hidden for every "
            "other category, since they don't apply to an AP, switch, "
            "access control panel, or UPS."
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

    class Meta:
        ordering = ["name"]
        verbose_name = "Device Type"
        verbose_name_plural = "Device Types"

    @property
    def is_camera(self):
        return self.category == self.CATEGORY_CAMERA

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
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Horizontal position as a percentage of image width (0-100).",
    )
    y_pct = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Vertical position as a percentage of image height (0-100).",
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

    class Meta:
        ordering = ["floorplan__site__name", "floorplan__location__name", "floorplan__name", "device__name"]
        verbose_name = "Device Placement"
        verbose_name_plural = "Device Placements"
        constraints = [
            models.UniqueConstraint(
                fields=["device"],
                name="unique_device_placement",
            )
        ]

    def __str__(self):
        return f"{self.device.name} @ {self.floorplan.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_camera_floorplan:floorplan", args=[self.floorplan.pk])

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
