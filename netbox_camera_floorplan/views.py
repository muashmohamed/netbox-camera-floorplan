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

from netbox.views import generic
from netbox.object_actions import BulkDelete, BulkExport, BulkImport

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
                "A device type with that name (or slug) already exists. "
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
    queryset = FloorPlan.objects.prefetch_related("cameras__device")
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
    # NetBox's default (AddObject, BulkImport, BulkExport, BulkEdit,
    # BulkRename, BulkDelete) assumes every one of those views exists.
    # This model deliberately only has List/Import/Export/Delete(bulk and
    # single-row) views — creation is canvas-click or CSV-only, and there's
    # no edit or rename form — so Add/BulkEdit/BulkRename rendered as dead
    # buttons (href="None", the same bug already fixed for Import). Note
    # BulkDelete must stay in this tuple: without at least one multi=True
    # action, NetBox hides the row-selection checkboxes entirely, which is
    # what caused multi-select to disappear the first time this was cut
    # down to (BulkImport, BulkExport) alone.
    actions = (BulkImport, BulkExport, BulkDelete)
    # x_pct IS NULL sorts first in Postgres's default NULLS LAST-for-ASC
    # behavior only if we ask for it explicitly — ordering by "-x_pct"
    # descending puts NULLs (unplaced) first, which is exactly the
    # "needs attention" ordering we want as a passive reminder, without
    # requiring anyone to remember to apply the Placed filter. The
    # needs_nvr annotation does the same for cameras missing an NVR link
    # (whether never assigned, or orphaned by a deleted NVR) — it sorts
    # second, after "not even placed yet", since an unplaced device needs
    # attention regardless of its NVR status.
    queryset = (
        CameraPlacement.objects.select_related("device", "floorplan__site", "floorplan__location", "camera_type")
        .annotate(
            needs_nvr=models.Case(
                models.When(
                    camera_type__category=CameraType.CATEGORY_CAMERA,
                    connected_nvr__isnull=True,
                    then=models.Value(0),
                ),
                default=models.Value(1),
                output_field=models.IntegerField(),
            )
        )
        .order_by("-x_pct", "needs_nvr", "device__name")
    )
    table = tables.CameraPlacementTable
    filterset = filtersets.CameraPlacementFilterSet
    filterset_form = forms.CameraPlacementFilterForm


class CameraPlacementDeleteView(generic.ObjectDeleteView):
    queryset = CameraPlacement.objects.all()

    def get(self, request, *args, **kwargs):
        # Overriding get() directly, rather than relying on
        # get_extra_context(), since that hook's exact invocation on the
        # delete-confirmation page turned out uncertain in practice — this
        # runs unconditionally before the page renders, so the warning
        # can't silently fail to appear regardless of template internals.
        instance = get_object_or_404(self.queryset, pk=kwargs.get("pk"))
        # connected_nvr uses on_delete=SET_NULL — deleting an NVR never
        # deletes or breaks its cameras, it just clears their NVR/channel
        # link (they'll show up flagged "Needs NVR" in the placements list
        # afterward). That's a safe default, but still worth flagging
        # explicitly here so it's never a silent surprise at the moment of
        # deletion, not just something discoverable after the fact.
        if instance.camera_type and instance.camera_type.is_nvr:
            connected = list(instance.connected_cameras.select_related("device")[:10])
            total = instance.connected_cameras.count()
            if total:
                names = ", ".join(c.device.name for c in connected)
                if total > len(connected):
                    names += f", and {total - len(connected)} more"
                messages.warning(
                    request,
                    f"This NVR has {total} connected camera(s): {names}. Deleting it will "
                    f"clear their NVR/channel assignment — the cameras themselves won't be "
                    f"deleted, but they'll need a new NVR assigned afterward.",
                )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # The pre_delete signal (models.py: clear_orphaned_nvr_channel)
        # verified correct in isolation via a direct instance.delete()
        # call, but observed NOT firing when triggered through this exact
        # view's actual delete flow in practice — NetBox's ObjectDeleteView
        # apparently performs the underlying deletion through a path that
        # doesn't reliably trigger Django's standard signal dispatch for
        # every field-clearing side effect. Rather than keep chasing that
        # internal mechanism, this does the cleanup explicitly and
        # unconditionally, ahead of whatever the base view's post() does —
        # guaranteed correct regardless of how NetBox implements deletion
        # underneath. The signal stays in place too, as a harmless second
        # layer for any other path that does use a normal .delete() call.
        instance = get_object_or_404(self.queryset, pk=kwargs.get("pk"))
        if instance.camera_type and instance.camera_type.is_nvr:
            instance.connected_cameras.update(nvr_channel=None)
        return super().post(request, *args, **kwargs)


class CameraPlacementBulkDeleteView(generic.BulkDeleteView):
    queryset = CameraPlacement.objects.all()
    filterset = filtersets.CameraPlacementFilterSet
    table = tables.CameraPlacementTable

    def post(self, request, *args, **kwargs):
        # Same explicit-cleanup guarantee as the single-row delete view
        # above, and for the same reason — don't rely on the pre_delete
        # signal alone for this.
        pks = request.POST.getlist("pk")
        if pks:
            nvr_ids = list(
                self.queryset.filter(pk__in=pks, camera_type__category=CameraType.CATEGORY_NVR)
                .values_list("pk", flat=True)
            )
            if nvr_ids:
                CameraPlacement.objects.filter(connected_nvr_id__in=nvr_ids).update(nvr_channel=None)
        return super().post(request, *args, **kwargs)


class CameraPlacementChangeLogView(generic.ObjectChangeLogView):
    queryset = CameraPlacement.objects.all()


class CameraPlacementBulkImportView(generic.BulkImportView):
    """
    CSV bulk import for devices — cameras, NVRs, APs, etc. Deliberately
    excludes x_pct/y_pct: canvas placement (dragging/clicking a marker
    onto the floor plan image) stays a manual step, so an imported row
    shows up as "unplaced" until someone does that. NVR/channel
    assignment, on the other hand, is fully set from the CSV, since
    that's exactly the repetitive step this feature exists to avoid.
    """

    queryset = CameraPlacement.objects.all()
    model_form = forms.CameraPlacementImportForm
    table = tables.CameraPlacementTable


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
        cameras = floorplan.cameras.select_related(
            "device", "device__primary_ip4", "camera_type", "connected_nvr__device"
        ).all()

        camera_data = []
        unplaced_data = []
        for cam in cameras:
            uplinks = cam.get_uplink_terminations()
            power = cam.get_power_terminations()
            primary_ip = cam.device.primary_ip4
            entry = {
                "id": cam.pk,
                "device_id": cam.device.pk,
                "device_name": cam.device.name,
                "device_url": cam.device.get_absolute_url(),
                "ip_address": str(primary_ip.address.ip) if primary_ip else None,
                "camera_type_id": cam.camera_type_id,
                "x_pct": float(cam.x_pct) if cam.is_placed else None,
                "y_pct": float(cam.y_pct) if cam.is_placed else None,
                "direction_degrees": cam.direction_degrees,
                "power_source_override": cam.power_source_override,
                "notes": cam.notes,
                "reachability": cam.get_reachability(),
                "connected_nvr_id": cam.connected_nvr_id,
                "nvr_channel": cam.nvr_channel,
                "channel_label": cam.get_channel_label(),
                "nvr_channel_usage": cam.get_nvr_channel_usage(),
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
            }
            if cam.is_placed:
                camera_data.append(entry)
            else:
                unplaced_data.append(entry)

        camera_types = [
            {
                "id": ct.pk,
                "name": ct.name,
                "color": ct.color,
                "icon_url": ct.get_icon_url(),
                "fov_degrees": ct.fov_degrees,
                "category": ct.category,
                "is_camera": ct.is_camera,
                "is_nvr": ct.is_nvr,
                "channel_capacity": ct.channel_capacity,
            }
            for ct in CameraType.objects.all()
        ]

        # Every placed NVR across ALL floor plans, not just this one — an
        # NVR is often in a different room/rack than the cameras feeding
        # into it, so a camera here needs to be able to point at an NVR
        # placed elsewhere.
        nvr_placements = (
            CameraPlacement.objects.filter(camera_type__category=CameraType.CATEGORY_NVR)
            .select_related("device", "camera_type", "floorplan")
        )
        nvr_data = [
            {
                "id": nvr.pk,
                "device_name": nvr.device.name,
                "floorplan_id": nvr.floorplan_id,
                "floorplan_name": str(nvr.floorplan),
                "capacity": nvr.camera_type.channel_capacity if nvr.camera_type else None,
                "usage": nvr.get_nvr_channel_usage(),
                # JSON object keys are always strings, so channel numbers
                # come through JS-side as string keys ("3", not 3) — the
                # picker code below accounts for that.
                "used_channels": nvr.get_nvr_channel_assignments(),
            }
            for nvr in nvr_placements
        ]

        can_edit = request.user.has_perm("netbox_camera_floorplan.add_cameraplacement")

        return render(request, "netbox_camera_floorplan/floorplan_canvas.html", {
            "object": floorplan,
            "floorplan": floorplan,
            "cameras_json": json.dumps(camera_data),
            "unplaced_json": json.dumps(unplaced_data),
            "camera_types_json": json.dumps(camera_types),
            "nvrs_json": json.dumps(nvr_data),
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

        if device_id is None:
            return JsonResponse({"error": "device_id is required."}, status=400)

        # x_pct/y_pct are omitted when placing a marker for the first time
        # via the "Unplaced devices" list click flow below (the device
        # already exists as a CameraPlacement from a CSV import; only its
        # position is being set now) — both must be provided together, or
        # both left out entirely.
        if (x_pct is None) != (y_pct is None):
            return JsonResponse({"error": "x_pct and y_pct must be provided together."}, status=400)

        if x_pct is not None:
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

        connected_nvr_id = payload.get("connected_nvr_id")
        connected_nvr = None
        if connected_nvr_id:
            connected_nvr = get_object_or_404(CameraPlacement, pk=connected_nvr_id)
        nvr_channel = payload.get("nvr_channel") or None

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
                              f"A device can only be pinned to one location — "
                              f"delete that marker first if you want to move it here."},
                    status=409,
                )

            detail = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({"error": f"Could not save this device: {detail}"}, status=400)

        if placement_id:
            placement = get_object_or_404(CameraPlacement, pk=placement_id, floorplan=floorplan)
            placement.device = device
            if "camera_type_id" in payload:
                placement.camera_type = camera_type
            # Only touch position if this call actually provided it — this
            # is what lets clicking an "unplaced" device onto the canvas
            # set its position via this same endpoint, without every other
            # detail-panel save (type change, notes, NVR assignment, etc.)
            # having to resend x/y for an already-placed marker.
            if x_pct is not None:
                placement.x_pct = x_pct
                placement.y_pct = y_pct
            placement.direction_degrees = direction
            placement.power_source_override = payload.get("power_source_override", placement.power_source_override)
            placement.notes = payload.get("notes", placement.notes)
            if "connected_nvr_id" in payload:
                placement.connected_nvr = connected_nvr
            if "nvr_channel" in payload:
                placement.nvr_channel = nvr_channel
            try:
                placement.full_clean()
                placement.save()
            except (IntegrityError, ValidationError) as e:
                return build_error_response(e)
        else:
            if x_pct is None:
                return JsonResponse({"error": "x_pct and y_pct are required when placing a new marker."}, status=400)
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
                    connected_nvr=connected_nvr,
                    nvr_channel=nvr_channel,
                )
                placement.full_clean()
                placement.save()
            except (IntegrityError, ValidationError) as e:
                return build_error_response(e)

        return JsonResponse({"id": placement.pk, "status": "ok"})


@method_decorator(csrf_protect, name="dispatch")
class CameraPlacementUnplaceView(PermissionRequiredMixin, View):
    """
    "Remove from canvas" — clears x/y so the marker disappears from the
    floor plan image, but keeps the CameraPlacement row itself intact
    (device, camera type, connected NVR, channel, notes all preserved).
    It reappears in that floor plan's "Unplaced devices" list, same as a
    CSV-imported row that's never been placed yet.

    This is deliberately NOT a delete: permission required is 'change',
    not 'delete', since nothing is actually being removed from the
    database — only its position. Full removal of the record is only
    available via the row-delete action on the Device Placements list
    (CameraPlacementDeleteView) or bulk delete, which use the standard
    'delete' permission and NetBox's own confirmation page.
    """
    permission_required = "netbox_camera_floorplan.change_cameraplacement"

    def post(self, request, pk):
        placement = get_object_or_404(CameraPlacement, pk=pk)
        placement.x_pct = None
        placement.y_pct = None
        placement.full_clean()
        placement.save()
        return JsonResponse({
            "status": "unplaced",
            "id": placement.pk,
            "device_id": placement.device_id,
            "device_name": placement.device.name,
            "device_url": placement.device.get_absolute_url(),
            "camera_type_id": placement.camera_type_id,
        })


class DeviceSearchView(PermissionRequiredMixin, View):
    """
    Small JSON search endpoint used by the "Add camera" modal's device
    lookup field, so the canvas never needs a raw NetBox REST API token in
    the browser — it reuses the logged-in session instead. Read-only.

    Requires the same permission as actually placing a device, not just
    being logged in — otherwise a user with zero access to this plugin
    could still discover device names/sites/locations through this
    endpoint, which matters given this plugin's data (camera coverage,
    physical security layouts) is meant to be restricted.

    Optionally scoped to a FloorPlan's site/location via ?floorplan_id=,
    so devices belonging to that site/location are shown first.
    """

    permission_required = "netbox_camera_floorplan.add_cameraplacement"

    def get(self, request):
        query = request.GET.get("q", "").strip()
        # No minimum length here on purpose — an empty query still runs
        # (name__icontains="" matches everything), so focusing the device
        # search box shows a full/default list sorted by relevance to
        # this floor plan, before the user types anything to narrow it.
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
