from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets
from ..models import CameraPlacement, CameraType, FloorPlan
from .serializers import CameraPlacementSerializer, CameraTypeSerializer, FloorPlanSerializer


class CameraTypeViewSet(NetBoxModelViewSet):
    queryset = CameraType.objects.all()
    serializer_class = CameraTypeSerializer
    filterset_class = filtersets.CameraTypeFilterSet


class FloorPlanViewSet(NetBoxModelViewSet):
    queryset = FloorPlan.objects.all()
    serializer_class = FloorPlanSerializer
    filterset_class = filtersets.FloorPlanFilterSet


class CameraPlacementViewSet(NetBoxModelViewSet):
    queryset = CameraPlacement.objects.all()
    serializer_class = CameraPlacementSerializer
    filterset_class = filtersets.CameraPlacementFilterSet
