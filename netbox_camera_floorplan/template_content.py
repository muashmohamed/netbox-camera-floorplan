import json

from netbox.plugins import PluginTemplateExtension

from .models import FloorPlan

# Shared grouping logic — differs only in whether "Site" is its own column
# (Floor Plans list) or embedded as "Site / Location / Floor Plan" text
# within a "Floorplan" column (Camera Placements list).
#
# Registered via NetBox's own PluginTemplateExtension API (list_buttons
# hook) rather than by extending generic/object_list.html and guessing at
# its internal block names — that approach was tried first and, per
# inspecting the actual rendered page source, never actually worked: the
# script never made it into the page at all. PluginTemplateExtension is
# NetBox's documented, stable mechanism for exactly this kind of
# injection, so it doesn't depend on guessing undocumented internals.

_SCRIPT_TEMPLATE = """
<script>
(function(){{
  function applyGrouping(){{
    // Guard against firing on unrelated NetBox pages — despite this
    // extension declaring a specific model, its list_buttons() output
    // was observed appearing on other pages too (any list with a
    // matching column name), inserting blank group-header rows there
    // and visibly breaking that page's row spacing. Whatever NetBox's
    // actual list_buttons() scoping does internally, checking the real
    // page URL here is a simple, directly-verifiable way to make sure
    // this only ever runs on the one page it's actually meant for.
    if(window.location.pathname.indexOf('{url_guard}') === -1) return;

    var table = document.querySelector('table.object-list');
    if(!table) return;
    var tbody = table.querySelector('tbody');
    if(!tbody) return;

    tbody.querySelectorAll('.cfp-group-header').forEach(function(el){{ el.remove(); }});

    var headerCells = Array.from(table.querySelectorAll('thead th'));
    var colIndex = headerCells.findIndex(function(th){{
      return th.textContent.trim().toLowerCase(){match_expr};
    }});
    if(colIndex === -1) return;

    var dataRows = Array.from(tbody.querySelectorAll('tr'));
    if(!dataRows.length) return;

    // Physically re-sort rows by site name first, rather than assuming
    // same-site rows are already adjacent in whatever order NetBox
    // returned them. NetBox's row order follows each Location's own
    // internal tree/creation order, not site name — so two unrelated
    // Locations belonging to the same site (created separately, under
    // different parent trees) can easily end up with a different site's
    // row sitting in between them. Grouping only contiguous blocks (the
    // original approach) silently split back apart every time that
    // happened again — reparenting Locations fixed one specific instance
    // but did nothing to stop the next one. Actually sorting here makes
    // this permanent regardless of how Locations get created in future.
    var rowsWithSite = dataRows.map(function(row){{
      var cells = row.querySelectorAll('td');
      var siteName = cells[colIndex] ? ({extract_site_expr}) : '';
      return {{ row: row, siteName: siteName || '' }};
    }});
    rowsWithSite.sort(function(a, b){{
      if(a.siteName < b.siteName) return -1;
      if(a.siteName > b.siteName) return 1;
      return 0;  // stable sort (guaranteed since ES2019) keeps each site's own rows in their original relative order
    }});
    rowsWithSite.forEach(function(entry){{ tbody.appendChild(entry.row); }});
    dataRows = rowsWithSite.map(function(entry){{ return entry.row; }});

    var currentSite = null;
    var groupIndex = 0;

    dataRows.forEach(function(row){{
      var cells = row.querySelectorAll('td');
      if(!cells[colIndex]) return;
      var siteName = {extract_site_expr};
      if(!siteName) return;

      if(siteName !== currentSite){{
        currentSite = siteName;
        groupIndex++;
        var headerRow = document.createElement('tr');
        headerRow.className = 'cfp-group-header';
        headerRow.style.cursor = 'pointer';
        headerRow.style.background = 'var(--tblr-bg-surface-secondary, #f2f4f6)';
        var td = document.createElement('td');
        td.colSpan = headerCells.length;
        td.style.fontWeight = '600';
        td.innerHTML = '<span class="cfp-group-arrow">\u25be</span> ' + siteName;
        headerRow.appendChild(td);
        row.parentNode.insertBefore(headerRow, row);
      }}
      row.dataset.cfpGroup = 'g' + groupIndex;
    }});

    tbody.querySelectorAll('.cfp-group-header').forEach(function(headerRow){{
      headerRow.addEventListener('click', function(){{
        var arrow = headerRow.querySelector('.cfp-group-arrow');
        var collapsing = arrow.textContent.trim() === '\u25be';
        arrow.textContent = collapsing ? '\u25b8' : '\u25be';
        var sibling = headerRow.nextElementSibling;
        while(sibling && !sibling.classList.contains('cfp-group-header')){{
          sibling.style.display = collapsing ? 'none' : '';
          sibling = sibling.nextElementSibling;
        }}
      }});
    }});
  }}

  document.addEventListener('DOMContentLoaded', applyGrouping);
  document.body.addEventListener('htmx:afterSwap', applyGrouping);
  document.body.addEventListener('htmx:afterSettle', applyGrouping);
}})();
</script>
"""

# Camera Placements: "Site" is embedded as "Site / Location / Floor Plan"
# text inside the "Floorplan" column.
_PLACEMENT_SCRIPT = _SCRIPT_TEMPLATE.format(
    url_guard="/plugins/camera-floorplan/",
    match_expr=".indexOf('floorplan') !== -1",
    extract_site_expr="cells[colIndex].textContent.trim().split('/')[0].trim()",
)

# Floor Plans: "Site" is its own dedicated column.
_FLOORPLAN_SCRIPT = _SCRIPT_TEMPLATE.format(
    url_guard="/plugins/camera-floorplan/",
    match_expr=" === 'site'",
    extract_site_expr="cells[colIndex].textContent.trim()",
)

# DCIM Locations (core NetBox page): also has "Site" as its own dedicated
# column, same shape as the Floor Plans list — added deliberately this
# time (per explicit request), scoped to exactly this page via its own
# url_guard, unlike the earlier accidental leak onto this same page.
_LOCATION_SCRIPT = _SCRIPT_TEMPLATE.format(
    url_guard="/dcim/locations/",
    match_expr=" === 'site'",
    extract_site_expr="cells[colIndex].textContent.trim()",
)


class CameraPlacementListGrouping(PluginTemplateExtension):
    model = "netbox_camera_floorplan.cameraplacement"

    def list_buttons(self):
        return _PLACEMENT_SCRIPT


class FloorPlanListGrouping(PluginTemplateExtension):
    model = "netbox_camera_floorplan.floorplan"

    def list_buttons(self):
        return _FLOORPLAN_SCRIPT


class LocationListGrouping(PluginTemplateExtension):
    """
    Collapsible site-grouping for the core DCIM Locations list — added
    deliberately here, unlike the earlier version of this feature which
    leaked onto this same page by accident (see _SCRIPT_TEMPLATE's
    url_guard). Genuinely useful on this page too, per explicit request,
    now scoped correctly instead of an unintended side effect.
    """

    model = "dcim.location"

    def list_buttons(self):
        return _LOCATION_SCRIPT


class LocationFloorPlanIndicator(PluginTemplateExtension):
    """
    Adds a small "open floor plan" icon button directly into NetBox's own
    row-actions area (alongside the existing changelog/edit buttons) for
    every Location that has one of our Floor Plans attached — visible
    before deleting a Location, not just discoverable afterward by
    cross-referencing our plugin's own Floor Plans list. Clicking it
    jumps straight to that floor plan's canvas.

    Same list_buttons() + client-side DOM-annotation technique already
    proven working for the grouping headers above (a genuine
    PluginTemplateExtension hook, not guessing at generic/object_list.html
    block names, which was tried first and confirmed not to work).
    """

    model = "dcim.location"

    def list_buttons(self):
        # Map location_id -> that floor plan's own canvas URL. A Location
        # could in principle have more than one FloorPlan; take the first
        # match deterministically (by pk) rather than an arbitrary one.
        location_urls = {}
        for fp in FloorPlan.objects.filter(location__isnull=False).order_by("pk"):
            location_urls.setdefault(fp.location_id, fp.get_absolute_url())
        location_urls_json = json.dumps(location_urls)

        return f"""
<script>
(function(){{
  var FLOORPLAN_URLS_BY_LOCATION = {location_urls_json};

  function applyButtons(){{
    var table = document.querySelector('table.object-list');
    if(!table) return;
    var rows = table.querySelectorAll('tbody tr');
    rows.forEach(function(row){{
      if(row.dataset.cfpFloorplanBtn) return;  // avoid re-adding on repeated htmx refreshes
      // querySelectorAll + last match, not querySelector's first match —
      // nested/indented rows (a child Location under a parent) can have
      // more than one /dcim/locations/ link in the same row (e.g. a
      // parent-breadcrumb or tree-toggle link appearing before the row's
      // own name link), and grabbing the first one silently attached
      // content to the wrong element on those rows.
      var links = row.querySelectorAll('td a[href*="/dcim/locations/"]');
      if(!links.length) return;
      var link = links[links.length - 1];
      var match = link.getAttribute('href').match(/\\/dcim\\/locations\\/(\\d+)\\//);
      if(!match) return;
      var floorplanUrl = FLOORPLAN_URLS_BY_LOCATION[match[1]];
      if(!floorplanUrl) return;

      var cells = row.querySelectorAll('td');
      var actionsCell = cells[cells.length - 1];
      if(!actionsCell) return;

      var btn = document.createElement('a');
      btn.href = floorplanUrl;
      // No margin utility class — NetBox's own adjacent buttons (e.g.
      // "View elevations" next to the edit/dropdown group) aren't
      // margin-classed either; they're separated by a plain whitespace
      // character between elements in the server-rendered HTML. Matching
      // that exact mechanism (see the text node inserted below) gives
      // consistent spacing with NetBox's own buttons instead of
      // approximating it with a Bootstrap margin value.
      btn.className = 'btn btn-cyan btn-sm';
      btn.title = 'Open this location\\'s Camera Floor Plan';
      btn.innerHTML = '<i class="mdi mdi-floor-plan"></i>';
      // Inserted as a standalone element before NetBox's own buttons,
      // without touching or rewrapping their existing markup at all —
      // safer than moving their DOM nodes into a shared container, and
      // keeps this visually and structurally separate as intended.
      actionsCell.insertBefore(btn, actionsCell.firstChild);
      actionsCell.insertBefore(document.createTextNode(' '), btn.nextSibling);
      row.dataset.cfpFloorplanBtn = 'true';
    }});
  }}

  document.addEventListener('DOMContentLoaded', applyButtons);
  document.body.addEventListener('htmx:afterSwap', applyButtons);
  document.body.addEventListener('htmx:afterSettle', applyButtons);
}})();
</script>
"""


template_extensions = [CameraPlacementListGrouping, FloorPlanListGrouping, LocationListGrouping, LocationFloorPlanIndicator]

# ---------------------------------------------------------------------------
# Security Zone badges — reads a NetBox-native Custom Field, doesn't define
# or own the classification data itself. Set up once in Admin > Customization
# > Custom Fields: a Selection-type field named exactly "security_zone",
# assigned to the Location model, with choices matching the keys below
# (Public / Controlled / Restricted / High Security). This plugin code only
# renders whatever that field already holds — it's a display layer on top of
# NetBox's own general-purpose classification mechanism, not a replacement
# for it (per the ISO 27001 physical-security-zoning discussion: the
# classification itself belongs in Custom Fields, since it's a general
# NetBox concept, not something specific to camera floor plans).
# ---------------------------------------------------------------------------

_SECURITY_ZONE_STYLES = {
    "Public": {"color": "green", "description": "Publicly accessible area. No special access controls required."},
    "Controlled": {
        "color": "cyan",
        "description": "Access limited to employees and authorized visitors. Sign-in or escort may be required.",
    },
    "Restricted": {
        "color": "orange",
        "description": "Access limited to authorized personnel only. Escort required for visitors. Entry is logged.",
    },
    "High Security": {
        "color": "red",
        "description": (
            "Highest security zone (e.g. server/comms rooms). Access strictly limited to designated "
            "authorized personnel. All entry/exit logged and monitored."
        ),
    },
}


class LocationSecurityZoneIndicator(PluginTemplateExtension):
    """
    Renders the "security_zone" custom field (if set) as a colored badge
    next to each Location's name in the core DCIM Locations list, with a
    hover tooltip describing what that zone level means/requires.

    Deliberately reads custom_field_data directly rather than assuming
    which choices exist — if the custom field is renamed, given different
    choice values, or not created at all yet, this silently does nothing
    rather than erroring, since the field's existence and choices are
    admin-configured data this code doesn't own or control.
    """

    model = "dcim.location"

    def list_buttons(self):
        from dcim.models import Location

        zone_by_location = {}
        for loc in Location.objects.only("pk", "custom_field_data"):
            zone = (loc.custom_field_data or {}).get("security_zone")
            if zone:
                zone_by_location[loc.pk] = zone
        zone_by_location_json = json.dumps(zone_by_location)
        styles_json = json.dumps(_SECURITY_ZONE_STYLES)

        return f"""
<script>
(function(){{
  var ZONE_BY_LOCATION = {zone_by_location_json};
  var ZONE_STYLES = {styles_json};

  function applyZoneBadges(){{
    var table = document.querySelector('table.object-list');
    if(!table) return;
    var rows = table.querySelectorAll('tbody tr');
    rows.forEach(function(row){{
      if(row.dataset.cfpZoneBadge) return;  // avoid re-adding on repeated htmx refreshes
      var cells = row.querySelectorAll('td');
      // Name is always the second cell (index 1) — index 0 is the
      // row-select checkbox. Scoping the link search to specifically
      // THIS cell, and appending back into this SAME cell variable,
      // means the result can't depend on wherever the browser's
      // nested-anchor auto-correction actually relocated the anchors to
      // (which is what broke the previous closest('td') attempt — that
      // resolved to the actions cell at the far right instead of Name).
      var nameCell = cells[1];
      if(!nameCell) return;
      var link = nameCell.querySelector('a[href*="/dcim/locations/"]');
      if(!link) return;
      var match = link.getAttribute('href').match(/\\/dcim\\/locations\\/(\\d+)\\//);
      if(!match) return;
      var zone = ZONE_BY_LOCATION[match[1]];
      if(!zone) return;
      var style = ZONE_STYLES[zone];
      if(!style) return;  // an unrecognized/custom choice value — skip rather than guess a color

      var badge = document.createElement('span');
      badge.className = 'badge text-bg-' + style.color + ' mx-2';
      badge.title = style.description;
      badge.textContent = zone;
      nameCell.appendChild(badge);
      row.dataset.cfpZoneBadge = 'true';
    }});
  }}

  document.addEventListener('DOMContentLoaded', applyZoneBadges);
  document.body.addEventListener('htmx:afterSwap', applyZoneBadges);
  document.body.addEventListener('htmx:afterSettle', applyZoneBadges);
}})();
</script>
"""


template_extensions.append(LocationSecurityZoneIndicator)
