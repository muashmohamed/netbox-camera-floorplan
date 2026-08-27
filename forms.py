from io import BytesIO

from django import forms
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image

from dcim.models import Device, Location, Site, SiteGroup
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from utilities.forms.fields import CSVModelChoiceField, DynamicModelChoiceField, DynamicModelMultipleChoiceField

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeForm(NetBoxModelForm):
    class Meta:
        model = CameraType
        fields = ["name", "slug", "category", "preset_icon", "icon_image", "color", "fov_degrees", "channel_capacity", "description", "tags"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color"}),
        }
        help_texts = {
            "preset_icon": "Quick start: pick one of the built-in icons below.",
        }


class FloorPlanForm(NetBoxModelForm):
    site = DynamicModelChoiceField(queryset=Site.objects.all())
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        query_params={"site_id": "$site"},
    )
    # Overrides the ModelForm's auto-generated forms.ImageField, which
    # would reject a PDF outright (via its own built-in PIL validation)
    # before clean_image() below ever got a chance to intercept it and
    # convert it. A plain FileField lets both image and PDF uploads
    # through to our own validation/conversion logic.
    image = forms.FileField(
        help_text="Upload an image (PNG/JPG) or a PDF — a PDF's first page is automatically converted to an image.",
    )
    pdf_page = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        label="PDF page number",
        help_text=(
            "Only used if you uploaded a PDF. Each floor plan here represents "
            "one specific Site/Location, but a real architectural PDF export "
            "often has multiple pages (ground floor, first floor, electrical "
            "layout, etc.) — set which page is THIS floor plan, so only that "
            "one page gets imported, not the whole document. Defaults to "
            "page 1. Ignored for a plain image upload."
        ),
    )

    class Meta:
        model = FloorPlan
        fields = ["name", "site", "location", "image", "comments", "tags"]

    def clean_image(self):
        uploaded = self.cleaned_data.get("image")
        if not uploaded:
            return uploaded

        uploaded.seek(0)
        header = uploaded.read(5)
        uploaded.seek(0)
        is_pdf = getattr(uploaded, "content_type", "") == "application/pdf" or header == b"%PDF-"

        if not is_pdf:
            # Not a PDF — still verify it's a genuine image (this is the
            # same check forms.ImageField would have done for us before
            # we overrode the field above), since a plain FileField
            # otherwise wouldn't catch a bogus non-image upload here.
            try:
                Image.open(uploaded).verify()
            except Exception:
                raise forms.ValidationError(
                    "Upload a valid image (PNG/JPG) or a PDF — this file doesn't appear to be either."
                )
            uploaded.seek(0)
            return uploaded

        try:
            import pymupdf
        except ImportError:
            raise forms.ValidationError(
                "PDF upload support requires the PyMuPDF package, which isn't installed on "
                "this server yet. Please export the PDF's first page as a PNG/JPG and upload "
                "that instead, or ask your administrator to add PyMuPDF to the plugin's "
                "dependencies and rebuild."
            )

        # Read the page number directly from raw submitted data rather
        # than self.cleaned_data['pdf_page'] — Django doesn't guarantee
        # that field has finished its own cleaning before this method
        # runs, since per-field clean order follows declaration order,
        # and relying on that would be fragile.
        raw_page = self.data.get("pdf_page") or "1"
        try:
            page_num = int(raw_page)
            if page_num < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise forms.ValidationError("PDF page number must be a positive whole number.")

        pdf_bytes = uploaded.read()
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise forms.ValidationError("This PDF has no pages.")
            if page_num > doc.page_count:
                raise forms.ValidationError(
                    f"This PDF only has {doc.page_count} page(s) — page {page_num} doesn't exist."
                )
            page = doc.load_page(page_num - 1)  # PyMuPDF pages are 0-indexed
            # 150 DPI is a reasonable balance of clarity vs file size for
            # a floor plan drawing (72 DPI is a PDF's "native" unit).
            zoom = 150 / 72
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            png_bytes = pix.tobytes("png")
        except forms.ValidationError:
            raise
        except Exception as exc:
            raise forms.ValidationError(f"Could not convert this PDF to an image: {exc}")

        base_name = uploaded.name.rsplit(".", 1)[0] if "." in uploaded.name else uploaded.name
        return InMemoryUploadedFile(
            BytesIO(png_bytes),
            field_name="image",
            name=f"{base_name}.png",
            content_type="image/png",
            size=len(png_bytes),
            charset=None,
        )


class FloorPlanFilterForm(NetBoxModelFilterSetForm):
    """
    Powers the filter panel on the Floor Plans list page, matching
    NetBox's real hierarchy: a Site Group (e.g. "Viligli Powerhouse")
    contains Sites (e.g. its transformers/office), and each Site
    contains Locations (e.g. floors/rooms within that site's building).
    Picking a Site Group narrows Site; picking a Site narrows Location.
    """
    model = FloorPlan

    site_group_id = DynamicModelMultipleChoiceField(
        queryset=SiteGroup.objects.all(),
        required=False,
        label="Site Group",
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label="Site",
        query_params={"group_id": "$site_group_id"},
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label="Location",
        query_params={"site_id": "$site_id"},
    )


class CameraPlacementForm(NetBoxModelForm):
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        help_text="Select the existing NetBox device being placed.",
    )
    camera_type = DynamicModelChoiceField(
        queryset=CameraType.objects.all(),
        required=False,
        label="Device type",
        help_text="Placement type — manage these under Plugins → Device Types.",
    )

    class Meta:
        model = CameraPlacement
        fields = [
            "floorplan",
            "device",
            "camera_type",
            "x_pct",
            "y_pct",
            "direction_degrees",
            "power_source_override",
            "notes",
            "tags",
        ]
        widgets = {
            "x_pct": forms.HiddenInput(),
            "y_pct": forms.HiddenInput(),
        }


class CameraPlacementFilterForm(NetBoxModelFilterSetForm):
    """
    Powers the filter panel on the Camera Placements list page.
    CameraPlacement doesn't have Site/Location fields of its own — these
    reach through to whichever floor plan each placement belongs to, same
    Site Group -> Site -> Location cascade as the Floor Plans list.
    """
    model = CameraPlacement

    site_group_id = DynamicModelMultipleChoiceField(
        queryset=SiteGroup.objects.all(),
        required=False,
        label="Site Group",
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label="Site",
        query_params={"group_id": "$site_group_id"},
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label="Location",
        query_params={"site_id": "$site_id"},
    )
    floorplan_id = DynamicModelMultipleChoiceField(
        queryset=FloorPlan.objects.all(),
        required=False,
        label="Floor Plan",
        query_params={"site_id": "$site_id", "location_id": "$location_id"},
    )


class CameraPlacementImportForm(NetBoxModelImportForm):
    """
    Bulk CSV import for devices (cameras, NVRs, APs, etc.) — deliberately
    does NOT accept x_pct/y_pct: canvas placement stays a manual,
    click-to-place step. A row imported here shows up in that floor
    plan's "Unplaced devices" list until someone drags/clicks it onto
    the actual image.

    Both `device` and `connected_nvr` are resolved against real NetBox
    devices by name — never free text — consistent with how every other
    device lookup in this plugin works. `connected_nvr` is a two-hop
    lookup: the CSV cell holds the NVR's own device name, which is
    resolved here to the CameraPlacement wrapping that device (the
    actual target of the connected_nvr FK).

    Column order matters for combined imports: if an NVR and the cameras
    that reference it are in the same CSV, the NVR's row must come
    before its cameras' rows, since connected_nvr can only resolve to an
    NVR that already has a placement (either from an earlier row in
    this same file, or one placed earlier through the canvas).
    """

    device = CSVModelChoiceField(
        queryset=Device.objects.all(),
        to_field_name="name",
        help_text="Name of the existing NetBox device (must be unique — disambiguate by renaming if two sites share a device name).",
    )
    camera_type = CSVModelChoiceField(
        queryset=CameraType.objects.all(),
        to_field_name="name",
        required=False,
        label="Device type",
        help_text="Name of an existing Device Type (Plugins → Device Types).",
    )
    floorplan = forms.CharField(
        help_text='Which floor plan this device belongs to, formatted exactly as it appears in the UI: "Site / Name" or "Site / Location / Name".',
    )
    connected_nvr = forms.CharField(
        required=False,
        label="Connected NVR",
        help_text="Device name of an already-placed NVR (leave blank if this row isn't a camera, or has no NVR yet).",
    )

    class Meta:
        model = CameraPlacement
        fields = [
            "device", "camera_type", "floorplan", "connected_nvr", "nvr_channel",
            "power_source_override", "notes", "tags",
        ]

    def clean_floorplan(self):
        raw = self.cleaned_data["floorplan"].strip()
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) == 2:
            site_name, name = parts
            location_name = None
        elif len(parts) == 3:
            site_name, location_name, name = parts
        else:
            raise forms.ValidationError(
                'Expected "Site / Name" or "Site / Location / Name" — got: ' + raw
            )

        qs = FloorPlan.objects.filter(site__name=site_name, name=name)
        qs = qs.filter(location__name=location_name) if location_name else qs.filter(location__isnull=True)
        floorplan = qs.first()
        if not floorplan:
            raise forms.ValidationError(f'No floor plan matches "{raw}".')
        return floorplan

    def clean_connected_nvr(self):
        raw = self.cleaned_data.get("connected_nvr", "").strip()
        if not raw:
            return None
        placement = (
            CameraPlacement.objects.filter(device__name=raw, camera_type__category=CameraType.CATEGORY_NVR)
            .select_related("camera_type")
            .first()
        )
        if not placement:
            raise forms.ValidationError(
                f'"{raw}" isn\'t an already-placed NVR. Place the NVR itself first '
                f"(or, in this same CSV, put its row before any camera that references it)."
            )
        return placement
