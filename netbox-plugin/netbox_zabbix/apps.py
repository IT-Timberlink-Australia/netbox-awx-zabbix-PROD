# /opt/netbox/plugins/netbox-zabbix/netbox_zabbix/apps.py
from netbox.plugins import PluginConfig


class NetBoxZabbixConfig(PluginConfig):
    name = "netbox_zabbix"
    verbose_name = "NetBox Zabbix"
    description = "Zabbix integration for NetBox"
    version = "0.1.0"
    base_url = "zabbix"
    min_version = "4.4.0"
    max_version = "4.9.99"

    def ready(self):
        # Import views so @register_model_view decorators run AFTER apps are loaded
        from . import views  # noqa: F401


# v4 requires module-level config symbol
config = NetBoxZabbixConfig
