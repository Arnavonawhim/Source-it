from django.db import models
from django.contrib.auth.models import AbstractUser


class GovUser(AbstractUser):
    """
    Extended user model for government officials.
    """
    ROLE_CHOICES = [
        ('state_admin', 'State Administrator'),
        ('district_admin', 'District Administrator'),
        ('ndma', 'NDMA Official'),
        ('central', 'Central Ministry'),
        ('viewer', 'Read-Only Viewer'),
    ]
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='viewer')
    state = models.CharField(max_length=60, blank=True)
    ministry = models.CharField(max_length=100, blank=True)
    employee_id = models.CharField(max_length=40, unique=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.role})"


class ResourceType(models.Model):
    """
    Pluggable resource definition — add new resources without code changes.
    """
    slug = models.SlugField(unique=True)          # e.g. "lpg", "water", "food_grains"
    name = models.CharField(max_length=80)        # Display name
    unit = models.CharField(max_length=30)        # e.g. "%" for index, "MT" for metric tons
    critical_threshold = models.FloatField(default=45.0)
    warning_threshold  = models.FloatField(default=63.0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class StateUT(models.Model):
    """
    All 36 Indian states and union territories.
    """
    REGION_CHOICES = [
        ('North', 'North'), ('South', 'South'), ('East', 'East'),
        ('West', 'West'), ('Central', 'Central'), ('Northeast', 'Northeast'),
        ('UT', 'Union Territory'),
    ]
    name = models.CharField(max_length=80, unique=True)
    region = models.CharField(max_length=20, choices=REGION_CHOICES)
    population_millions = models.FloatField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SupplyRecord(models.Model):
    """
    One supply reading per resource per state per timestamp.
    Ingest from government APIs, scrapers, or manual uploads.
    """
    STATUS_CHOICES = [
        ('critical', 'Critical'),
        ('warning',  'Warning'),
        ('stable',   'Stable'),
    ]
    state         = models.ForeignKey(StateUT, on_delete=models.CASCADE, related_name='supply_records')
    resource      = models.ForeignKey(ResourceType, on_delete=models.CASCADE, related_name='supply_records')
    value         = models.FloatField(help_text="Supply level — percentage index or physical unit")
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES)
    source        = models.CharField(max_length=120, blank=True, help_text="Data source (e.g. FCI API, CWC, manual)")
    recorded_at   = models.DateTimeField()
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes  = [
            models.Index(fields=['state', 'resource', '-recorded_at']),
        ]

    def save(self, *args, **kwargs):
        if self.status == '':
            r = self.resource
            if self.value < r.critical_threshold:
                self.status = 'critical'
            elif self.value < r.warning_threshold:
                self.status = 'warning'
            else:
                self.status = 'stable'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.state} / {self.resource} = {self.value} @ {self.recorded_at}"


class Alert(models.Model):
    """
    System-generated or manually raised alert.
    """
    LEVEL_CHOICES = [('critical','Critical'), ('warning','Warning'), ('info','Information')]
    state    = models.ForeignKey(StateUT, on_delete=models.CASCADE, related_name='alerts')
    resource = models.ForeignKey(ResourceType, on_delete=models.CASCADE, related_name='alerts')
    level    = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    title    = models.CharField(max_length=200)
    message  = models.TextField()
    is_active     = models.BooleanField(default=True)
    is_resolved   = models.BooleanField(default=False)
    resolved_at   = models.DateTimeField(null=True, blank=True)
    resolved_by   = models.ForeignKey(GovUser, null=True, blank=True, on_delete=models.SET_NULL)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level}] {self.state} — {self.resource}: {self.title}"


class AllocationOrder(models.Model):
    """
    Gov-panel supply allocation orders filed by officials.
    """
    STATUS_CHOICES = [
        ('pending',   'Pending Approval'),
        ('approved',  'Approved'),
        ('dispatched','Dispatched'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    reference_no      = models.CharField(max_length=40, unique=True)
    created_by        = models.ForeignKey(GovUser, on_delete=models.CASCADE, related_name='orders')
    resource          = models.ForeignKey(ResourceType, on_delete=models.CASCADE)
    source_state      = models.ForeignKey(StateUT, on_delete=models.CASCADE, related_name='outgoing_orders')
    destination_state = models.ForeignKey(StateUT, on_delete=models.CASCADE, related_name='incoming_orders')
    allocation_pct    = models.FloatField(help_text="Percentage of surplus stock to transfer")
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes             = models.TextField(blank=True)
    estimated_eta_hrs = models.IntegerField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.reference_no}: {self.source_state} → {self.destination_state} ({self.resource})"


class BroadcastAlert(models.Model):
    """
    Citizen-facing alerts broadcast by gov officials.
    """
    LEVEL_CHOICES  = [('critical','Critical'), ('warning','Warning'), ('info','Information')]
    CHANNEL_CHOICES = [('sms','SMS'), ('ivr','IVR'), ('app','App Notification'), ('all','All Channels')]
    sent_by    = models.ForeignKey(GovUser, on_delete=models.CASCADE, related_name='broadcasts')
    states     = models.ManyToManyField(StateUT, blank=True, help_text="Leave empty to broadcast nationally")
    level      = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    message    = models.TextField()
    channel    = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='all')
    sent_at    = models.DateTimeField(auto_now_add=True)
    reach_est  = models.IntegerField(null=True, blank=True, help_text="Estimated citizen reach")

    def __str__(self):
        return f"[{self.level}] Broadcast by {self.sent_by} at {self.sent_at}"


class AIRecommendation(models.Model):
    """
    AI-generated crisis management recommendations (stored for audit).
    """
    state       = models.ForeignKey(StateUT, on_delete=models.CASCADE, related_name='ai_recs')
    resource    = models.ForeignKey(ResourceType, on_delete=models.CASCADE)
    priority    = models.CharField(max_length=20)
    action_text = models.TextField()
    confidence  = models.FloatField(help_text="0–100 confidence score")
    was_acted   = models.BooleanField(default=False)
    acted_by    = models.ForeignKey(GovUser, null=True, blank=True, on_delete=models.SET_NULL)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AI Rec [{self.priority}] {self.state} — {self.resource} ({self.confidence}%)"