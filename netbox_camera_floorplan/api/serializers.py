from netbox.api.serializers import NetBoxModelSerializer
from rest_framework.serializers import HyperlinkedIdentityField

from ..models import CameraPlacement, FloorPlan


class FloorPlanSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="plugins-api:netbox_camera_floorplan-api:floorplan-detail"
    )

    class Meta:
        model = FloorPlan
        fields = [
            "id", "url", "display", "name", "site", "location", "image",
            "comments", "tags", "custom_fields", "created", "last_updated",
        ]
        brief_fields = ["id", "url", "display", "name"]


class CameraPlacementSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="plugins-api:netbox_camera_floorplan-api:cameraplacement-detail"
    )

    class Meta:
        model = CameraPlacement
        fields = [
            "id", "url", "display", "floorplan", "device", "camera_type",
            "x_pct", "y_pct", "direction_degrees", "power_source_override",
            "notes", "tags", "custom_fields", "created", "last_updated",
        ]
        brief_fields = ["id", "url", "display", "device"]
