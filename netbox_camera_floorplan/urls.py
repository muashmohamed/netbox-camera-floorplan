from django.urls import path

from . import views

app_name = "netbox_camera_floorplan"

urlpatterns = [
    # FloorPlan CRUD
    path("floorplans/", views.FloorPlanListView.as_view(), name="floorplan_list"),
    path("floorplans/add/", views.FloorPlanEditView.as_view(), name="floorplan_add"),
    path("floorplans/<int:pk>/edit/", views.FloorPlanEditView.as_view(), name="floorplan_edit"),
    path("floorplans/<int:pk>/delete/", views.FloorPlanDeleteView.as_view(), name="floorplan_delete"),

    # The interactive canvas — this is the main screen
    path("floorplans/<int:pk>/", views.FloorPlanCanvasView.as_view(), name="floorplan"),
    path("floorplans/<int:pk>/save-camera/", views.CameraPlacementSaveView.as_view(), name="camera_save"),

    # CameraPlacement CRUD (mostly used from the canvas, but list view is useful too)
    path("cameras/", views.CameraPlacementListView.as_view(), name="cameraplacement_list"),
    path("cameras/<int:pk>/delete/", views.CameraPlacementDeleteView.as_view(), name="cameraplacement_delete"),
    path("cameras/<int:pk>/quick-delete/", views.CameraPlacementQuickDeleteView.as_view(), name="camera_quick_delete"),
]
