# NetBox Camera Floor Plan Plugin

Place CCTV cameras on floor plan images inside NetBox, and view each
camera's real uplink switch/port and power connection — pulled live from
NetBox's own cable and power port data, never duplicated or hand-entered.

## v0.2.0 changes (this version)

- **Camera Types are now a real, manageable NetBox model.** Go to
  **Plugins → Camera Types** to add/edit/delete types (name, icon, color,
  description) — no more hardcoded Dome/PTZ/Bullet/Other choices.
- **Built-in icon presets.** When adding a Camera Type, pick one of the
  built-in icons (Dome, PTZ, Bullet, Generic camera) from a dropdown — no
  file to prepare. You can still upload your own custom icon image instead;
  an uploaded image always takes priority over the preset.
- The floor plan canvas now builds its marker icons dynamically from
  whatever Camera Types you've defined.
- **All native browser dialogs are gone.** Placing a camera, choosing its
  type, and deleting a marker now use in-app modals with a real device
  search box, instead of `window.prompt()` / `window.confirm()` / `alert()`.
- The device search in the "Add camera" modal now shows each device's
  Location (not just Site), and sorts devices in the current floor plan's
  own Location/Site to the top.
- `CameraType` is exposed in the REST API at
  `/api/plugins/camera-floorplan/camera-types/`, alongside the existing
  `floorplans/` and `cameras/` endpoints.
- Fixed a `NoReverseMatch` error on the Camera Types (and FloorPlan /
  CameraPlacement) list pages — NetBox's standard object table always
  links each row to a change-history view, which none of these three
  models had registered. All three now have proper changelog views/URLs.
- Fixed clicking the floor plan doing nothing (`ReferenceError: bootstrap
  is not defined` in the browser console). NetBox doesn't expose
  Bootstrap's JS as a global `window.bootstrap`, so the "place a camera"
  modal now drives its own show/hide instead of depending on that.
- Fixed `403 CSRF verification failed` when saving a camera placement.
  The canvas JS was reading a `csrftoken` cookie that NetBox doesn't set
  (it isn't cookie-based here); it now uses Django's `{{ csrf_token }}`
  template value instead, which works regardless of how CSRF is
  configured.
- Fixed a raw `500 Internal Server Error` when placing a device that's
  already on the same floor plan (the "one marker per device per floor
  plan" database rule was correct, but hitting it wasn't handled — it now
  shows a clear inline message instead of crashing).
- **Changed the uniqueness rule**: a device can now only be placed on
  **one floor plan total**, not just once-per-floor-plan — a physical
  camera exists in exactly one location, so placing the same device
  twice (even on two different floor plans) no longer makes sense to
  allow. **Requires a new migration** — see below.
- The "place a camera" device search now shows already-placed devices in
  red with the floor plan they're already on, so you find out *before*
  clicking Place camera instead of after.
- Each camera's primary IPv4 address is now shown both under its label
  on the floor plan and in the details panel, when the device has one
  set in NetBox.
- Added a "Marker label" dropdown above the floor plan to choose Name
  only, IP only, or both — remembered per-browser so it doesn't reset
  every time you open a floor plan.
- Removed the direction-facing cone overlay from markers (kept the
  underlying direction data and the slider in the details panel, just
  not visualized on the map for now).
- Added a proper filter panel to the Floor Plans list page: pick a Site
  first, and the Location dropdown narrows to just that site's
  locations — Site as the parent, Location as the child, matching how
  they relate everywhere else in NetBox. Makes managing many floor plans
  across multiple sites/buildings much easier than a flat list.
- Extended that filter one level higher: Site Group is now the top-level
  filter (e.g. a powerhouse grouping several sites like its
  transformers/office), narrowing Site, which narrows Location. Three
  levels of cascading filters total: Site Group → Site → Location.
- Fixed a raw `500 IntegrityError` when adding a Camera Type or Floor
  Plan with a name that already exists (usually from double-clicking
  Create/Save). Now shows a clear message and returns to the form
  instead of crashing.
- Fixed the "place a camera" save endpoint incorrectly reporting
  "already placed on another floor plan" for *any* validation failure,
  even when nothing was actually conflicting. It now only shows that
  message for genuine uniqueness conflicts, and shows the real
  validation error otherwise.
- **Found and fixed the real bug the above was masking**: clicking to
  place a *new* camera sends raw pixel-derived coordinates with far more
  than 3 decimal places, but the database only stores 3 — every new
  placement was silently failing this validation. The first attempt at
  fixing this (rounding the float) wasn't actually enough — Django
  converts a Python float to `Decimal` by preserving its exact binary
  representation (e.g. `34.568` can become
  `Decimal('34.567999999999998...')` with 40+ digits), which still fails
  the decimal-places check. Coordinates are now converted via a
  formatted string (`f"{value:.3f}"`) instead, which is exact.
- Fixed a `NoReverseMatch` crash opening the Camera Placements list page
  (same root cause as the earlier changelog fix — NetBox's table tried
  to build an "Edit" link that doesn't exist). This list intentionally
  has no Edit or Add entry point: a placement's x/y position can only be
  set meaningfully by clicking on the floor plan canvas, so this page is
  now view + delete only, as intended.
- A Floor Plan's display text (used in the Camera Placements table and
  any dropdown) now includes its Location when set — "Site / Location /
  Floor Plan Name" — instead of skipping straight from Site to name.

### A note on camera devices and racks

This plugin never touches rack position. When you create a camera Device
in NetBox, you don't need to assign it to a rack at all — wall/ceiling/
boundary-mounted cameras are exactly what floor plan placement (`x_pct`/
`y_pct`) is for. Just give the device a Site (and optionally a Location);
skip the rack field entirely.

### Upgrading from an earlier install

`CameraPlacement.camera_type` changed from a fixed-choice text field to a
foreign key pointing at the new `CameraType` model. On your test server:

1. Pull in these updated files.
2. Add at least one `CameraType` row before you place new cameras — either
   via **Plugins → Camera Types → Add Camera Type** in the UI, or via the
   Django shell.
3. Run migrations as usual:
   ```bash
   python manage.py makemigrations netbox_camera_floorplan
   python manage.py migrate
   ```
4. Any cameras placed under the old string-based types will show up with
   **no camera type** afterward (the field is nullable) — open each one on
   the canvas and reassign it from the new dropdown, or re-run your seed
   script against the new model.

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
