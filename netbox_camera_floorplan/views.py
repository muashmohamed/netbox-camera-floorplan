import json

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from netbox.views import generic

from . import filtersets, forms, tables
from .models import CameraPlacement, FloorPlan


# ---------------------------------------------------------------------------
# FloorPlan CRUD (standard NetBox generic views)
# ---------------------------------------------------------------------------

class FloorPlanListView(generic.ObjectListView):
    queryset = FloorPlan.objects.all()
    table = tables.FloorPlanTable
    filterset = filtersets.FloorPlanFilterSet


class FloorPlanEditView(generic.ObjectEditView):
    queryset = FloorPlan.objects.all()
    form = forms.FloorPlanForm


class FloorPlanDeleteView(generic.ObjectDeleteView):
    queryset = FloorPlan.objects.all()


# ---------------------------------------------------------------------------
# CameraPlacement CRUD
# ---------------------------------------------------------------------------

class CameraPlacementListView(generic.ObjectListView):
    queryset = CameraPlacement.objects.all()
    table = tables.CameraPlacementTable
    filterset = filtersets.CameraPlacementFilterSet


class CameraPlacementDeleteView(generic.ObjectDeleteView):
    queryset = CameraPlacement.objects.all()


# ---------------------------------------------------------------------------
# The interactive floor plan canvas — the main screen technicians/engineers use
# ---------------------------------------------------------------------------

class FloorPlanCanvasView(PermissionRequiredMixin, View):
    """
    Renders the floor plan image with existing camera markers, and provides
    the click-to-place interaction. Reads are permission-gated on viewing
    the FloorPlan object; writes (add/move camera) are gated separately in
    the AJAX endpoint below.
    """

    permission_required = "netbox_camera_floorplan.view_floorplan"

    def get(self, request, pk):
        floorplan = get_object_or_404(FloorPlan, pk=pk)
        cameras = floorplan.cameras.select_related("device").all()

        camera_data = []
        for cam in cameras:
            uplinks = cam.get_uplink_terminations()
            power = cam.get_power_terminations()
            camera_data.append({
                "id": cam.pk,
                "device_id": cam.device.pk,
                "device_name": cam.device.name,
                "device_url": cam.device.get_absolute_url(),
                "camera_type": cam.camera_type,
                "x_pct": float(cam.x_pct),
                "y_pct": float(cam.y_pct),
                "direction_degrees": cam.direction_degrees,
                "power_source_override": cam.power_source_override,
                "notes": cam.notes,
                "reachability": cam.get_reachability(),
                "uplinks": [
                    {
                        "local_interface": str(local_if),
                        "remote_device": str(remote_dev) if remote_dev else None,
                        "remote_interface": str(remote_if),
                    }
                    for local_if, remote_dev, remote_if in uplinks
                ],
                "power_terminations": [
                    {"port": str(p), "remote": str(r)} for p, r in power
                ],
            })

        can_edit = request.user.has_perm("netbox_camera_floorplan.add_cameraplacement")

        return render(request, "netbox_camera_floorplan/floorplan_canvas.html", {
            "object": floorplan,
            "floorplan": floorplan,
            "cameras_json": json.dumps(camera_data),
            "can_edit": can_edit,
        })


@method_decorator(csrf_protect, name="dispatch")
class CameraPlacementSaveView(PermissionRequiredMixin, View):
    """
    AJAX endpoint used by the canvas JS to create/update a camera's position
    and rotation without a full page reload. Device must already exist in
    NetBox; this view never creates devices, only placements.
    """

    permission_required = "netbox_camera_floorplan.add_cameraplacement"

    def post(self, request, pk):
        floorplan = get_object_or_404(FloorPlan, pk=pk)
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        placement_id = payload.get("id")
        device_id = payload.get("device_id")
        x_pct = payload.get("x_pct")
        y_pct = payload.get("y_pct")
        direction = payload.get("direction_degrees", 0)

        if x_pct is None or y_pct is None or device_id is None:
            return JsonResponse({"error": "device_id, x_pct and y_pct are required."}, status=400)

        from dcim.models import Device
        device = get_object_or_404(Device, pk=device_id)

        if placement_id:
            placement = get_object_or_404(CameraPlacement, pk=placement_id, floorplan=floorplan)
            placement.device = device
            placement.camera_type = payload.get("camera_type", placement.camera_type)
            placement.x_pct = x_pct
            placement.y_pct = y_pct
            placement.direction_degrees = direction
            placement.power_source_override = payload.get("power_source_override", placement.power_source_override)
            placement.notes = payload.get("notes", placement.notes)
            placement.save()
        else:
            placement = CameraPlacement.objects.create(
                floorplan=floorplan,
                device=device,
                camera_type=payload.get("camera_type", CameraPlacement.TYPE_OTHER),
                x_pct=x_pct,
                y_pct=y_pct,
                direction_degrees=direction,
                power_source_override=payload.get("power_source_override", ""),
                notes=payload.get("notes", ""),
            )

        return JsonResponse({"id": placement.pk, "status": "ok"})


@method_decorator(csrf_protect, name="dispatch")
class CameraPlacementQuickDeleteView(PermissionRequiredMixin, View):
    permission_required = "netbox_camera_floorplan.delete_cameraplacement"

    def post(self, request, pk):
        placement = get_object_or_404(CameraPlacement, pk=pk)
        placement.delete()
        return JsonResponse({"status": "deleted"})
