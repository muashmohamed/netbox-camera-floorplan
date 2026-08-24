from django import forms

from dcim.models import Device, Location, Site
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField

from .models import CameraPlacement, CameraType, FloorPlan


class CameraTypeForm(NetBoxModelForm):
    class Meta:
        model = CameraType
        fields = ["name", "slug", "preset_icon", "icon_image", "color", "description", "tags"]
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

    class Meta:
        model = FloorPlan
        fields = ["name", "site", "location", "image", "comments", "tags"]


class FloorPlanFilterForm(NetBoxModelFilterSetForm):
    """
    Powers the filter panel on the Floor Plans list page. Site is treated
    as the parent — picking one narrows the Location dropdown to just
    that site's locations, mirroring how Sites and Locations relate to
    each other everywhere else in NetBox.
    """
    model = FloorPlan

    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label="Site",
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
        help_text="Select the existing NetBox device for this camera.",
    )
    camera_type = DynamicModelChoiceField(
        queryset=CameraType.objects.all(),
        required=False,
        help_text="Physical camera type — manage these under Plugins → Camera Types.",
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
