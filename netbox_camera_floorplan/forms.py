from django import forms

from dcim.models import Device, Location, Site
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from .models import CameraPlacement, FloorPlan


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


class CameraPlacementForm(NetBoxModelForm):
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        help_text="Select the existing NetBox device for this camera.",
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
