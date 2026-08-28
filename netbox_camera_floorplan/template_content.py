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
    match_expr=".indexOf('floorplan') !== -1",
    extract_site_expr="cells[colIndex].textContent.trim().split('/')[0].trim()",
)

# Floor Plans: "Site" is its own dedicated column.
_FLOORPLAN_SCRIPT = _SCRIPT_TEMPLATE.format(
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
      var link = row.querySelector('td a[href*="/dcim/locations/"]');
      if(!link) return;
      var match = link.getAttribute('href').match(/\\/dcim\\/locations\\/(\\d+)\\//);
      if(!match) return;
      var floorplanUrl = FLOORPLAN_URLS_BY_LOCATION[match[1]];
      if(!floorplanUrl) return;

      var cells = row.querySelectorAll('td');
      var actionsCell = cells[cells.length - 1];
      if(!actionsCell) return;
      // NetBox renders row actions inside a .btn-group when present —
      // append alongside those existing buttons rather than replacing
      // them. Falls back to the bare cell if that wrapper isn't found,
      // so this still works even if NetBox's exact markup differs.
      var container = actionsCell.querySelector('.btn-group') || actionsCell;

      var btn = document.createElement('a');
      btn.href = floorplanUrl;
      btn.className = 'btn btn-cyan btn-sm';
      btn.title = 'Open this location\\'s Camera Floor Plan';
      btn.innerHTML = '<i class="mdi mdi-floor-plan"></i>';
      container.appendChild(btn);
      row.dataset.cfpFloorplanBtn = 'true';
    }});
  }}

  document.addEventListener('DOMContentLoaded', applyButtons);
  document.body.addEventListener('htmx:afterSwap', applyButtons);
  document.body.addEventListener('htmx:afterSettle', applyButtons);
}})();
</script>
"""


template_extensions = [CameraPlacementListGrouping, FloorPlanListGrouping, LocationFloorPlanIndicator]
