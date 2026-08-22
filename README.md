# NetBox Camera Floor Plan Plugin

Place CCTV cameras on floor plan images inside NetBox, and view each
camera's real uplink switch/port and power connection — pulled live from
NetBox's own cable and power port data, never duplicated or hand-entered.

## What this does

- Upload a floor plan image (e.g. exported from AutoCAD as PNG/JPG) per
  Site, optionally narrowed to a Location.
- Click on the image to drop a camera marker, linking it to an **existing**
  NetBox device (this plugin never creates devices — only positions them).
- Set each camera's facing direction (0-359°) as a rotating cone overlay.
- The uplink switch/port and power source shown for each camera are looked
  up live from the device's actual Interface/Cable and PowerPort records
  in NetBox — if those change in NetBox, the plugin reflects it automatically.
- Optional: if a monitoring plugin (e.g. `netbox-ping`) writes a boolean
  "reachable" custom field onto Device, this plugin can show that as a
  green/red ring around each camera marker (configure the field name in
  `PLUGINS_CONFIG`, see below).

## Requirements

- NetBox 4.0 or later
- Server (SSH/admin) access to install a Python package and restart NetBox

## Installation

1. Activate the NetBox virtual environment:
   ```bash
   source /opt/netbox/venv/bin/activate
   ```

2. Install this package. If you were given a `.tar.gz` or wheel file:
   ```bash
   pip install /path/to/netbox_camera_floorplan-0.1.0.tar.gz
   ```
   Or, if hosted in a Git repo:
   ```bash
   pip install git+https://your-git-host/netbox_camera_floorplan.git
   ```

3. Add it to NetBox's plugin list. Edit
   `/opt/netbox/netbox/netbox/configuration.py`:
   ```python
   PLUGINS = [
       "netbox_camera_floorplan",
   ]

   PLUGINS_CONFIG = {
       "netbox_camera_floorplan": {
           # Optional: name of a boolean custom field on Device that a
           # monitoring plugin writes reachability to. Leave blank to skip.
           "reachability_custom_field": "",
       },
   }
   ```

4. Add the package to `local_requirements.txt` so it survives future
   NetBox upgrades:
   ```bash
   echo netbox-camera-floorplan | sudo tee -a /opt/netbox/local_requirements.txt
   ```

5. Run migrations and collect static files:
   ```bash
   cd /opt/netbox/netbox
   python manage.py makemigrations netbox_camera_floorplan
   python manage.py migrate
   python manage.py collectstatic --no-input
   ```

6. Restart NetBox:
   ```bash
   sudo systemctl restart netbox netbox-rq
   ```

7. Confirm it worked: log into NetBox, look for **Camera Floor Plans**
   under the Plugins section of the left navigation.

## Usage

1. Go to **Plugins → Camera Floor Plans → Add Floor Plan**. Choose the
   Site (and optionally Location), give it a name (e.g. "Ground Floor"),
   and upload the floor plan image.
2. Open the floor plan. Click anywhere on the image to place a camera —
   you'll be asked for the NetBox device ID of an existing camera device
   (visible in that device's page URL), and its camera type (dome, ptz,
   or bullet — leave blank for a generic icon). Each type renders with
   its own distinct marker icon so different camera styles are easy to
   tell apart at a glance. The type can be changed later from the side
   panel after placement.
3. Drag the direction slider in the side panel to set which way the
   camera faces, add notes, and save.
4. Uplink and power information appear automatically if the device has
   real cable/power connections recorded in NetBox — nothing to enter
   manually for those.

## Permissions

Standard NetBox object permissions apply:
- `netbox_camera_floorplan.view_floorplan` / `view_cameraplacement` — to view
- `netbox_camera_floorplan.add_cameraplacement` — required to place/move/edit
  cameras on the canvas (view-only users can look but not click-to-place)
- `netbox_camera_floorplan.delete_cameraplacement` — to remove a placement

## Notes on scope

This plugin manages **positions and directions only**. It does not create,
edit, or delete Devices, Interfaces, Cables, or Power Ports — those remain
fully owned by NetBox core (or your existing MCP/automation tooling). This
keeps floor plan data and network topology data from ever drifting apart.
