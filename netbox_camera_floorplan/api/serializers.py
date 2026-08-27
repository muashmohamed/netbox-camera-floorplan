from netbox.api.serializers import NetBoxModelSerializer
from rest_framework.serializers import HyperlinkedIdentityField

from ..models import CameraPlacement, CameraType, FloorPlan


class CameraTypeSerializer(NetBoxModelSerializer):
    url = HyperlinkedIdentityField(
        view_name="plugins-api:netbox_camera_floorplan-api:cameratype-detail"
    )

    class Meta:
        model = CameraType
        fields = [
            "id", "url", "display", "name", "slug", "category", "preset_icon",
            "icon_image", "color", "fov_degrees", "channel_capacity", "description", "tags",
            "custom_fields", "created", "last_updated",
        ]
        brief_fields = ["id", "url", "display", "name"]


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
            "connected_nvr", "nvr_channel", "notes", "tags", "custom_fields",
            "created", "last_updated",
        ]
        brief_fields = ["id", "url", "display", "device"]
