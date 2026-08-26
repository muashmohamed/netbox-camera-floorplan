from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_camera_floorplan:cameratype_list",
        link_text="Device Types",
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_camera_floorplan:cameratype_add",
                title="Add Device Type",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:netbox_camera_floorplan:floorplan_list",
        link_text="Device Floor Plans",
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_camera_floorplan:floorplan_add",
                title="Add Floor Plan",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:netbox_camera_floorplan:cameraplacement_list",
        link_text="Device Placements",
    ),
)
