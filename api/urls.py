from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_camera_floorplan-api"

router = NetBoxRouter()
router.register("camera-types", views.CameraTypeViewSet)
router.register("floorplans", views.FloorPlanViewSet)
router.register("cameras", views.CameraPlacementViewSet)

urlpatterns = router.urls
