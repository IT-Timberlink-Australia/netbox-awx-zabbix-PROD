from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from netbox.models import NetBoxModel


class ZabbixEndpoint(NetBoxModel):
    name = models.SlugField(unique=True)
    api_url = models.URLField(
        help_text="Zabbix base URL, e.g. https://svrnmzb01.timberlinkaustralia.com.au"
    )
    awx_job_template_id = models.PositiveIntegerField(
        help_text="Reference to AWX job template ID used for sync"
    )
    awx_credential_name = models.CharField(
        max_length=128, blank=True, help_text="Reference to AWX credential name"
    )
    comments = models.TextField(blank=True)

    def __str__(self):
        return self.name


class HostGroup(NetBoxModel):
    endpoint = models.ForeignKey(
        ZabbixEndpoint, on_delete=models.CASCADE, related_name="hostgroups"
    )
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("endpoint", "name")
        ordering = ("endpoint__name", "name")

    def __str__(self):
        return f"{self.endpoint}:{self.name}"


class Template(NetBoxModel):
    endpoint = models.ForeignKey(ZabbixEndpoint, on_delete=models.CASCADE, related_name="templates")
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("endpoint", "name")
        ordering = ("endpoint__name", "name")

    def __str__(self):
        return f"{self.endpoint}:{self.name}"


class Proxy(NetBoxModel):
    endpoint = models.ForeignKey(ZabbixEndpoint, on_delete=models.CASCADE, related_name="proxies")
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("endpoint", "name")
        ordering = ("endpoint__name", "name")

    def __str__(self):
        return f"{self.endpoint}:{self.name}"


class MonitoringConfig(NetBoxModel):
    # Link to either Device or VirtualMachine
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    object = GenericForeignKey("content_type", "object_id")

    endpoint = models.ForeignKey(ZabbixEndpoint, on_delete=models.PROTECT, related_name="configs")
    enabled = models.BooleanField(default=True)
    desired_state = models.CharField(
        max_length=8,
        choices=(("present", "present"), ("absent", "absent")),
        default="present",
    )

    zabbix_name = models.CharField(
        max_length=255, blank=True, help_text="Defaults to Device/VM name if blank"
    )
    visible_name = models.CharField(max_length=255, blank=True)

    interface_policy = models.CharField(
        max_length=32,
        choices=(
            ("primary_ip", "Primary IP"),
            ("mgmt_if", "Management interface"),
            ("first_up", "First up"),
        ),
        default="primary_ip",
    )
    agent_port = models.PositiveIntegerField(default=10050)

    snmp_enabled = models.BooleanField(default=False)
    snmp_version = models.CharField(
        max_length=8, choices=(("v2c", "v2c"), ("v3", "v3")), blank=True
    )
    snmp_port = models.PositiveIntegerField(default=161)
    snmp_credential_ref = models.CharField(
        max_length=128, blank=True, help_text="Reference name/id in AWX"
    )

    proxy = models.ForeignKey(Proxy, blank=True, null=True, on_delete=models.SET_NULL)
    hostgroups = models.ManyToManyField(HostGroup, blank=True)
    templates = models.ManyToManyField(Template, blank=True)

    tags = models.JSONField(default=list, blank=True, help_text="List of {tag,value}")
    macros = models.JSONField(default=list, blank=True, help_text="List of {macro,value}")

    last_synced = models.DateTimeField(blank=True, null=True)
    last_sync_status = models.CharField(max_length=16, blank=True)

    class Meta:
        ordering = ("endpoint__name",)

    def __str__(self):
        return f"{self.object} → {self.endpoint}"
