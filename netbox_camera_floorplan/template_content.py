from netbox.plugins import PluginTemplateExtension

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


template_extensions = [CameraPlacementListGrouping, FloorPlanListGrouping]
