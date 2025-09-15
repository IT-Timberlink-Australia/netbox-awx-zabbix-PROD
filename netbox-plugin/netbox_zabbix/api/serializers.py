from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import HostGroup, MonitoringConfig, Proxy, Template


class HostGroupSerializer(NetBoxModelSerializer):
    class Meta:
        model = HostGroup
        fields = ("id", "name")


class TemplateSerializer(NetBoxModelSerializer):
    class Meta:
        model = Template
        fields = ("id", "name")


class ProxySerializer(NetBoxModelSerializer):
    class Meta:
        model = Proxy
        fields = ("id", "name")


class MonitoringConfigSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_zabbix-api:monitoringconfig-detail"
    )
    object_type = serializers.CharField(source="content_type.model", read_only=True)
    object_name = serializers.CharField(source="object.name", read_only=True)

    class Meta:
        model = MonitoringConfig
        fields = (
            "id",
            "url",
            "object_type",
            "object_id",
            "object_name",
            "endpoint",
            "enabled",
            "desired_state",
            "zabbix_name",
            "visible_name",
            "interface_policy",
            "agent_port",
            "snmp_enabled",
            "snmp_version",
            "snmp_port",
            "snmp_credential_ref",
            "proxy",
            "hostgroups",
            "templates",
            "tags",
            "macros",
            "last_synced",
            "last_sync_status",
        )
