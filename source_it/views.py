from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import (
    GovUser, ResourceType, StateUT, SupplyRecord,
    Alert, AllocationOrder, BroadcastAlert, AIRecommendation
)
from .serializers import (
    GovUserSerializer, ResourceTypeSerializer, StateUTSerializer,
    SupplyRecordSerializer, AlertSerializer, AllocationOrderSerializer,
    BroadcastAlertSerializer, AIRecommendationSerializer,
    NationalSnapshotSerializer
)


# ─── AUTH ───────────────────────────────────────────────────────────────────

class GovLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        employee_id = request.data.get('employee_id', '').strip().upper()
        password    = request.data.get('password', '')

        try:
            user = GovUser.objects.get(employee_id=employee_id)
        except GovUser.DoesNotExist:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_verified:
            return Response({'detail': 'Account pending verification by NDMA IT Cell.'}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id':          user.id,
                'name':        user.get_full_name() or user.username,
                'role':        user.role,
                'state':       user.state,
                'employee_id': user.employee_id,
            }
        })


class GovRegisterView(APIView):
    """
    Self-registration for gov officials. Requires admin verification before access.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GovUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            user.set_password(request.data['password'])
            user.is_verified = False   # must be approved by NDMA admin
            user.save()
            return Response({
                'detail': 'Registration submitted. Your account will be activated after NDMA verification.',
                'employee_id': user.employee_id
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── PUBLIC ENDPOINTS (no auth required) ────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def national_snapshot(request):
    """
    Main dashboard data for public consumers.
    Returns latest supply reading per resource per state, plus active alerts.
    """
    resources = ResourceType.objects.filter(is_active=True)
    states    = StateUT.objects.filter(is_active=True)
    snapshot  = {}

    for state in states:
        snapshot[state.id] = {
            'name':   state.name,
            'region': state.region,
            'pop':    state.population_millions,
            'supply': {}
        }
        for res in resources:
            record = (
                SupplyRecord.objects
                .filter(state=state, resource=res)
                .order_by('-recorded_at')
                .first()
            )
            snapshot[state.id]['supply'][res.slug] = {
                'value':  record.value  if record else None,
                'status': record.status if record else 'unknown',
            }

    active_alerts = Alert.objects.filter(is_active=True, is_resolved=False).select_related('state','resource')[:50]
    return Response({
        'snapshot':       snapshot,
        'alerts':         AlertSerializer(active_alerts, many=True).data,
        'resources':      ResourceTypeSerializer(resources, many=True).data,
        'generated_at':   timezone.now().isoformat(),
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def state_detail(request, state_id):
    """Per-state 7-day trend for all resources."""
    try:
        state = StateUT.objects.get(pk=state_id, is_active=True)
    except StateUT.DoesNotExist:
        return Response({'detail': 'State not found.'}, status=404)

    resources = ResourceType.objects.filter(is_active=True)
    since     = timezone.now() - timezone.timedelta(days=7)
    trend     = {}

    for res in resources:
        records = (
            SupplyRecord.objects
            .filter(state=state, resource=res, recorded_at__gte=since)
            .order_by('recorded_at')
            .values('value', 'status', 'recorded_at', 'source')
        )
        trend[res.slug] = list(records)

    return Response({
        'state':   StateUTSerializer(state).data,
        'trend':   trend,
        'alerts':  AlertSerializer(
            Alert.objects.filter(state=state, is_active=True, is_resolved=False),
            many=True
        ).data,
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def resource_overview(request, resource_slug):
    """Latest value for one resource across all states."""
    try:
        resource = ResourceType.objects.get(slug=resource_slug, is_active=True)
    except ResourceType.DoesNotExist:
        return Response({'detail': 'Resource not found.'}, status=404)

    states = StateUT.objects.filter(is_active=True)
    data   = []
    for state in states:
        record = (
            SupplyRecord.objects
            .filter(state=state, resource=resource)
            .order_by('-recorded_at')
            .first()
        )
        data.append({
            'state':  StateUTSerializer(state).data,
            'value':  record.value  if record else None,
            'status': record.status if record else 'unknown',
            'source': record.source if record else None,
            'ts':     record.recorded_at.isoformat() if record else None,
        })

    data.sort(key=lambda x: (x['value'] or 999))
    return Response({'resource': ResourceTypeSerializer(resource).data, 'states': data})


# ─── GOV-ONLY ENDPOINTS ─────────────────────────────────────────────────────

class IsGovUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and isinstance(request.user, GovUser) and request.user.is_verified)


@api_view(['GET'])
@permission_classes([IsGovUser])
def gov_dashboard(request):
    """Extended crisis management data visible only to authenticated gov officials."""
    critical_states = (
        SupplyRecord.objects
        .filter(status='critical')
        .select_related('state', 'resource')
        .order_by('value')[:20]
    )
    ai_recs = AIRecommendation.objects.filter(was_acted=False).order_by('-generated_at')[:10]
    pending_orders = AllocationOrder.objects.filter(status='pending').select_related(
        'source_state', 'destination_state', 'resource', 'created_by'
    )
    return Response({
        'critical_supply':  SupplyRecordSerializer(critical_states, many=True).data,
        'ai_recommendations': AIRecommendationSerializer(ai_recs, many=True).data,
        'pending_orders':   AllocationOrderSerializer(pending_orders, many=True).data,
        'user':             {'role': request.user.role, 'state': request.user.state},
    })


@api_view(['POST'])
@permission_classes([IsGovUser])
def file_allocation_order(request):
    """Gov official files a supply allocation order."""
    serializer = AllocationOrderSerializer(data=request.data)
    if serializer.is_valid():
        import uuid
        order = serializer.save(
            created_by=request.user,
            reference_no=f"RK/{timezone.now().year}/{uuid.uuid4().hex[:8].upper()}"
        )
        return Response(AllocationOrderSerializer(order).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsGovUser])
def broadcast_alert(request):
    """Gov official broadcasts a citizen-facing alert."""
    serializer = BroadcastAlertSerializer(data=request.data)
    if serializer.is_valid():
        alert = serializer.save(sent_by=request.user)
        # TODO: Hook into SMS/IVR gateway (e.g., CDAC GISFI, Bharat Sanchar Nigam)
        return Response(BroadcastAlertSerializer(alert).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsGovUser])
def resolve_alert(request, alert_id):
    """Mark an alert as resolved."""
    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        return Response({'detail': 'Alert not found.'}, status=404)
    alert.is_resolved  = True
    alert.is_active    = False
    alert.resolved_at  = timezone.now()
    alert.resolved_by  = request.user
    alert.save()
    return Response({'detail': 'Alert resolved.', 'resolved_at': alert.resolved_at})


# ─── ADMIN / DATA INGESTION ──────────────────────────────────────────────────

class IngestSupplyView(APIView):
    """
    Bulk ingestion endpoint called by scheduled scrapers / ETL jobs.
    Accepts a list of supply readings.
    Expected format:
        [
          {"state_id": 1, "resource_slug": "lgp", "value": 58.2, "source": "PPAC API", "recorded_at": "..."},
          ...
        ]
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        records = request.data if isinstance(request.data, list) else [request.data]
        created = []
        errors  = []

        for item in records:
            try:
                state    = StateUT.objects.get(pk=item['state_id'])
                resource = ResourceType.objects.get(slug=item['resource_slug'])
                rec = SupplyRecord.objects.create(
                    state=state,
                    resource=resource,
                    value=float(item['value']),
                    source=item.get('source', ''),
                    recorded_at=item.get('recorded_at', timezone.now()),
                    status=''   # auto-computed in model.save()
                )
                # Auto-raise alert if critical
                if rec.status == 'critical':
                    Alert.objects.get_or_create(
                        state=state,
                        resource=resource,
                        is_resolved=False,
                        defaults={
                            'level':   'critical',
                            'title':   f'Critical supply level in {state.name}',
                            'message': f'{resource.name} supply at {rec.value:.1f}% in {state.name}.',
                            'is_active': True,
                        }
                    )
                created.append(rec.id)
            except Exception as e:
                errors.append({'item': item, 'error': str(e)})

        return Response({'created': len(created), 'errors': errors})