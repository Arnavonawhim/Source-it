from rest_framework import serializers
from .models import (
    GovUser, ResourceType, StateUT, SupplyRecord,
    Alert, AllocationOrder, BroadcastAlert, AIRecommendation
)

class GovUserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = GovUser
        fields = ['id','username','first_name','last_name','email',
                  'role','state','ministry','employee_id']

class ResourceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ResourceType
        fields = ['id','slug','name','unit','critical_threshold',
                  'warning_threshold','description']

class StateUTSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StateUT
        fields = ['id','name','region','population_millions']

class SupplyRecordSerializer(serializers.ModelSerializer):
    state_name    = serializers.CharField(source='state.name',    read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)
    resource_slug = serializers.CharField(source='resource.slug', read_only=True)
    class Meta:
        model  = SupplyRecord
        fields = ['id','state','state_name','resource','resource_name',
                  'resource_slug','value','status','source','recorded_at']

class AlertSerializer(serializers.ModelSerializer):
    state_name    = serializers.CharField(source='state.name',    read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)
    class Meta:
        model  = Alert
        fields = ['id','state','state_name','resource','resource_name',
                  'level','title','message','is_active','is_resolved','created_at']

class AllocationOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AllocationOrder
        fields = ['id','reference_no','resource','source_state','destination_state',
                  'allocation_pct','status','notes','estimated_eta_hrs','created_at']
        read_only_fields = ['reference_no','status']

class BroadcastAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BroadcastAlert
        fields = ['id','states','level','message','channel','sent_at','reach_est']
        read_only_fields = ['sent_at']

class AIRecommendationSerializer(serializers.ModelSerializer):
    state_name    = serializers.CharField(source='state.name',    read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)
    class Meta:
        model  = AIRecommendation
        fields = ['id','state','state_name','resource','resource_name',
                  'priority','action_text','confidence','was_acted','generated_at']

class NationalSnapshotSerializer(serializers.Serializer):
    pass