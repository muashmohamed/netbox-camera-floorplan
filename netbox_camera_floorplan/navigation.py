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
    # Separate, read-only, camera-only section — gated on
    # view_cctv_floorplan specifically, not the standard view_floorplan
    # permission the items above use. A user granted only this
    # permission sees just this item, not any of the editable ones above;
    # a user with neither permission sees none of this plugin's nav at all.
    PluginMenuItem(
        link="plugins:netbox_camera_floorplan:cctv_floorplan_list",
        link_text="CCTV Floor Plans",
        permissions=["netbox_camera_floorplan.view_cctv_floorplan"],
    ),
)
