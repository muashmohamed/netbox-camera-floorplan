import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
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

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError:
            messages.error(
                request,
                "A camera type with that name (or slug) already exists. "
                "This usually happens from double-clicking Create/Save — "
                "please check the list before adding it again.",
            )
            return redirect(request.path)


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
    filterset_form = forms.FloorPlanFilterForm


class FloorPlanEditView(generic.ObjectEditView):
    queryset = FloorPlan.objects.all()
    form = forms.FloorPlanForm

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError:
            messages.error(
                request,
                "A floor plan with that name already exists for this site/location. "
                "This usually happens from double-clicking Create/Save — "
                "please check the list before adding it again.",
            )
            return redirect(request.path)


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
    filterset_form = forms.CameraPlacementFilterForm


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
        cameras = floorplan.cameras.select_related("device", "device__primary_ip4", "camera_type").all()

        camera_data = []
        for cam in cameras:
            uplinks = cam.get_uplink_terminations()
            power = cam.get_power_terminations()
            primary_ip = cam.device.primary_ip4
            camera_data.append({
                "id": cam.pk,
                "device_id": cam.device.pk,
                "device_name": cam.device.name,
                "device_url": cam.device.get_absolute_url(),
                "ip_address": str(primary_ip.address.ip) if primary_ip else None,
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
                "fov_degrees": ct.fov_degrees,
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

        # Raw click coordinates from the browser (pixel math) commonly have
        # far more precision than the model's DecimalField(decimal_places=3)
        # allows. Rounding a float and handing it straight to the model
        # isn't enough — Django converts floats to Decimal by preserving
        # their exact binary representation (e.g. 34.568 becomes something
        # like Decimal('34.5680000000000003944...')), which still fails the
        # decimal_places check. Building the Decimal from a formatted
        # string instead avoids that entirely.
        try:
            x_pct = Decimal(f"{float(x_pct):.3f}")
            y_pct = Decimal(f"{float(y_pct):.3f}")
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({"error": "x_pct and y_pct must be numbers."}, status=400)

        device = get_object_or_404(Device, pk=device_id)

        camera_type_id = payload.get("camera_type_id")
        camera_type = None
        if camera_type_id:
            camera_type = get_object_or_404(CameraType, pk=camera_type_id)

        def build_error_response(exc):
            """
            Only report "already placed" when the failure is genuinely a
            uniqueness conflict — otherwise show the real validation error.
            The previous version assumed every ValidationError/IntegrityError
            here meant a duplicate placement, which masked unrelated
            failures behind a misleading message.
            """
            is_uniqueness_conflict = isinstance(exc, IntegrityError)
            if isinstance(exc, ValidationError):
                message_dict = getattr(exc, "message_dict", None)
                text = (
                    " ".join(msg for msgs in message_dict.values() for msg in msgs)
                    if message_dict else " ".join(exc.messages)
                )
                if "already exists" in text.lower() or "unique" in text.lower():
                    is_uniqueness_conflict = True

            if is_uniqueness_conflict:
                existing = CameraPlacement.objects.filter(device=device).select_related("floorplan").first()
                if existing and existing.floorplan_id == floorplan.pk:
                    where = "this floor plan"
                elif existing:
                    where = f'the floor plan "{existing.floorplan.name}"'
                else:
                    where = "another floor plan (its marker may have just been removed — please try again)"
                return JsonResponse(
                    {"error": f"{device.name} is already placed on {where}. "
                              f"A camera can only be pinned to one location — "
                              f"delete that marker first if you want to move it here."},
                    status=409,
                )

            detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({"error": f"Could not save this camera: {detail}"}, status=400)

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
            try:
                placement.full_clean()
                placement.save()
            except (IntegrityError, ValidationError) as e:
                return build_error_response(e)
        else:
            try:
                placement = CameraPlacement(
                    floorplan=floorplan,
                    device=device,
                    camera_type=camera_type,
                    x_pct=x_pct,
                    y_pct=y_pct,
                    direction_degrees=direction,
                    power_source_override=payload.get("power_source_override", ""),
                    notes=payload.get("notes", ""),
                )
                placement.full_clean()
                placement.save()
            except (IntegrityError, ValidationError) as e:
                return build_error_response(e)

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

        devices = list(devices[:15])

        # Look up existing placements for just these matched devices in one
        # query, so the modal can flag "already placed" before the user
        # picks a device that's going to fail anyway.
        existing_placements = {
            p.device_id: p.floorplan
            for p in CameraPlacement.objects.filter(device__in=devices).select_related("floorplan")
        }

        return JsonResponse({
            "results": [
                {
                    "id": d.pk,
                    "name": d.name,
                    "site": str(d.site) if d.site else "",
                    "location": str(d.location) if d.location else "",
                    "placed_on_floorplan": (
                        existing_placements[d.pk].name if d.pk in existing_placements else None
                    ),
                }
                for d in devices
            ]
        })
