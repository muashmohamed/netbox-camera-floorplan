from netbox.plugins import PluginConfig


class CameraFloorplanConfig(PluginConfig):
    name = "netbox_camera_floorplan"
    verbose_name = "Device Floor Plans"
    description = "Place cameras, APs, access control, switches, and UPS units on floor plan images and view their live NetBox connections."
    version = "0.3.0"
    author = "Stelco IT"
    base_url = "camera-floorplan"
    min_version = "4.0.0"
    default_settings = {
        # Optional: name of a boolean custom field on dcim.Device that netbox-ping
        # (or any other monitoring plugin) writes to, so this plugin can show a
        # live reachability dot without owning ping logic itself.
        "reachability_custom_field": "",
    }


config = CameraFloorplanConfig
