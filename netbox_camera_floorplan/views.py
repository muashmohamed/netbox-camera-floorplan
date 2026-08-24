import json

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from django.contrib.auth.mixins import LoginRequiredMixin

from netbox.views import generic

from . import filtersets, forms, tables
from .models import CameraPlacement, CameraType, FloorPlan
from dcim.models import Device


# ---------------------------------------------------------------------------
# CameraType CRUD — manage the set of camera types and their icons/colors
# ---------------------------------------------------------------------------

class CameraTypeListView(generic.ObjectListView):
    queryset = CameraType.objects.all()
    table = tables.CameraTypeTable
    filterset = filtersets.CameraTypeFilterSet


class CameraTypeEditView(generic.ObjectEditView):
    queryset = CameraType.objects.all()
    form = forms.CameraTypeForm


class CameraTypeDeleteView(generic.ObjectDeleteView):
    queryset = CameraType.objects.all()


class CameraTypeChangeLogView(generic.ObjectChangeLogView):
    queryset = CameraType.objects.all()


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


class FloorPlanChangeLogView(generic.ObjectChangeLogView):
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


class CameraPlacementChangeLogView(generic.ObjectChangeLogView):
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
        cameras = floorplan.cameras.select_related("device", "camera_type").all()

        camera_data = []
        for cam in cameras:
            uplinks = cam.get_uplink_terminations()
            power = cam.get_power_terminations()
            camera_data.append({
                "id": cam.pk,
                "device_id": cam.device.pk,
                "device_name": cam.device.name,
                "device_url": cam.device.get_absolute_url(),
                "camera_type_id": cam.camera_type_id,
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

        camera_types = [
            {
                "id": ct.pk,
                "name": ct.name,
                "color": ct.color,
                "icon_url": ct.get_icon_url(),
            }
            for ct in CameraType.objects.all()
        ]

        can_edit = request.user.has_perm("netbox_camera_floorplan.add_cameraplacement")

        return render(request, "netbox_camera_floorplan/floorplan_canvas.html", {
            "object": floorplan,
            "floorplan": floorplan,
            "cameras_json": json.dumps(camera_data),
            "camera_types_json": json.dumps(camera_types),
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

        device = get_object_or_404(Device, pk=device_id)

        camera_type_id = payload.get("camera_type_id")
        camera_type = None
        if camera_type_id:
            camera_type = get_object_or_404(CameraType, pk=camera_type_id)

        if placement_id:
            placement = get_object_or_404(CameraPlacement, pk=placement_id, floorplan=floorplan)
            placement.device = device
            if "camera_type_id" in payload:
                placement.camera_type = camera_type
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
                camera_type=camera_type,
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


class DeviceSearchView(LoginRequiredMixin, View):
    """
    Small JSON search endpoint used by the "Add camera" modal's device
    lookup field, so the canvas never needs a raw NetBox REST API token in
    the browser — it reuses the logged-in session instead. Read-only.

    Optionally scoped to a FloorPlan's site/location via ?floorplan_id=,
    so devices belonging to that site/location are shown first.
    """

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"results": []})

        devices = Device.objects.filter(name__icontains=query).select_related("site", "location")

        floorplan_id = request.GET.get("floorplan_id")
        if floorplan_id:
            floorplan = FloorPlan.objects.filter(pk=floorplan_id).first()
            if floorplan:
                if floorplan.location_id:
                    devices = devices.order_by(
                        models.Case(
                            models.When(location_id=floorplan.location_id, then=0),
                            models.When(site_id=floorplan.site_id, then=1),
                            default=2,
                        )
                    )
                else:
                    devices = devices.order_by(
                        models.Case(
                            models.When(site_id=floorplan.site_id, then=0),
                            default=1,
                        )
                    )

        devices = devices[:15]
        return JsonResponse({
            "results": [
                {
                    "id": d.pk,
                    "name": d.name,
                    "site": str(d.site) if d.site else "",
                    "location": str(d.location) if d.location else "",
                }
                for d in devices
            ]
        })
