from io import BytesIO

from django import forms
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image

from dcim.models import Device, Location, Site, SiteGroup
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeForm(NetBoxModelForm):
    class Meta:
        model = CameraType
        fields = ["name", "slug", "category", "preset_icon", "icon_image", "color", "fov_degrees", "description", "tags"]
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

        pdf_bytes = uploaded.read()
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise forms.ValidationError("This PDF has no pages.")
            page = doc.load_page(0)
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
