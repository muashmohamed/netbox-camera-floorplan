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
        ordering = ["site", "location", "name"]
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


class CameraType(NetBoxModel):
    """
    A manageable camera type (e.g. Dome, PTZ, Bullet, Fisheye, Thermal...)
    with its own icon and marker color. Replaces what used to be a hardcoded
    set of choices on CameraPlacement — new types can be added from the
    NetBox UI with no code changes required.
    """

    PRESET_DOME = "dome"
    PRESET_PTZ = "ptz"
    PRESET_BULLET = "bullet"
    PRESET_GENERIC = "generic"
    PRESET_CHOICES = [
        ("", "None (use color swatch only)"),
        (PRESET_DOME, "Dome (built-in)"),
        (PRESET_PTZ, "PTZ (built-in)"),
        (PRESET_BULLET, "Bullet (built-in)"),
        (PRESET_GENERIC, "Generic camera (built-in)"),
    ]

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
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
        help_text="Hex color used for the marker ring and direction cone (e.g. #f2a65a).",
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

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
    A single camera's pinned position on a FloorPlan. Deliberately does NOT
    duplicate uplink switch/port or power source as separate text fields —
    that data already lives on the linked Device's real interfaces, cables,
    and power ports in NetBox core, and is looked up live for display so it
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
        help_text="The camera, as an existing NetBox device.",
    )
    camera_type = models.ForeignKey(
        to=CameraType,
        on_delete=models.SET_NULL,
        related_name="placements",
        null=True,
        blank=True,
        help_text="Physical camera type, used to pick the marker icon on the floor plan.",
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
        ordering = ["floorplan", "device"]
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
        """
        from django.conf import settings as django_settings

        field_name = django_settings.PLUGINS_CONFIG.get(
            "netbox_camera_floorplan", {}
        ).get("reachability_custom_field")
        if not field_name:
            return None
        return self.device.custom_field_data.get(field_name)
