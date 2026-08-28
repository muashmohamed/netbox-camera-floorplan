from django.urls import path

from . import views

app_name = "netbox_camera_floorplan"

urlpatterns = [
    # CameraType CRUD — manage camera types and their icons/colors
    path("camera-types/", views.CameraTypeListView.as_view(), name="cameratype_list"),
    path("camera-types/add/", views.CameraTypeEditView.as_view(), name="cameratype_add"),
    path("camera-types/<int:pk>/edit/", views.CameraTypeEditView.as_view(), name="cameratype_edit"),
    path("camera-types/<int:pk>/delete/", views.CameraTypeDeleteView.as_view(), name="cameratype_delete"),
    path("camera-types/<int:pk>/changelog/", views.CameraTypeChangeLogView.as_view(), name="cameratype_changelog"),

    # Device search (used by the "add camera" modal, replaces window.prompt())
    path("device-search/", views.DeviceSearchView.as_view(), name="device_search"),

    # FloorPlan CRUD
    path("floorplans/", views.FloorPlanListView.as_view(), name="floorplan_list"),
    path("floorplans/add/", views.FloorPlanEditView.as_view(), name="floorplan_add"),
    path("floorplans/<int:pk>/edit/", views.FloorPlanEditView.as_view(), name="floorplan_edit"),
    path("floorplans/<int:pk>/delete/", views.FloorPlanDeleteView.as_view(), name="floorplan_delete"),
    path("floorplans/<int:pk>/changelog/", views.FloorPlanChangeLogView.as_view(), name="floorplan_changelog"),

    # The interactive canvas — this is the main screen
    path("floorplans/<int:pk>/", views.FloorPlanCanvasView.as_view(), name="floorplan"),
    path("floorplans/<int:pk>/save-camera/", views.CameraPlacementSaveView.as_view(), name="camera_save"),

    # Restricted, read-only, camera-only section — for security team
    # access, gated on its own dedicated permission (view_cctv_floorplan)
    # without unlocking the full editable Device Floor Plans section.
    path("cctv-floorplans/", views.CCTVFloorPlanListView.as_view(), name="cctv_floorplan_list"),
    path("cctv-floorplans/<int:pk>/", views.CCTVFloorPlanCanvasView.as_view(), name="cctv_floorplan"),

    # CameraPlacement CRUD (mostly used from the canvas, but list view is useful too)
    path("cameras/", views.CameraPlacementListView.as_view(), name="cameraplacement_list"),
    path("cameras/import/", views.CameraPlacementBulkImportView.as_view(), name="cameraplacement_bulk_import"),
    path("cameras/delete/", views.CameraPlacementBulkDeleteView.as_view(), name="cameraplacement_bulk_delete"),
    path("cameras/<int:pk>/delete/", views.CameraPlacementDeleteView.as_view(), name="cameraplacement_delete"),
    path("cameras/<int:pk>/changelog/", views.CameraPlacementChangeLogView.as_view(), name="cameraplacement_changelog"),
    path("cameras/<int:pk>/unplace/", views.CameraPlacementUnplaceView.as_view(), name="camera_unplace"),
]
