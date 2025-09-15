# netbox-zabbix

A minimal NetBox 4.x plugin that stores Zabbix-related configuration for any Device or Virtual Machine.
AWX/Ansible can then consume a clean REST feed to sync hosts to Zabbix.

## Features (v0.1.0)
- Models: `ZabbixEndpoint`, `HostGroup`, `Template`, `Proxy`, and `MonitoringConfig` (attached to Devices/VMs).
- REST API with a `/sync/` endpoint returning pre-resolved host data for AWX.
- Uses `NetBoxModel` for change logging, tags, journaling, and webhooks.

adding test change

## Install (svrnmnb01)
1. Copy this repo onto your NetBox host (e.g., `/opt/netbox/plugins/netbox-zabbix`).
2. Install into NetBox's venv:
   ```bash
   sudo -i
   source /opt/netbox/venv/bin/activate
   pip install -e /opt/netbox/plugins/netbox-zabbix
   ```
3. Enable in `/opt/netbox/netbox/netbox/configuration.py`:
   ```python
   PLUGINS = ["netbox_zabbix"]
   PLUGINS_CONFIG = {
       "netbox_zabbix": {
           # Defaults can live here later
       }
   }
   ```
4. Migrate & collect static:
   ```bash
   cd /opt/netbox/netbox
   python3 manage.py migrate
   python3 manage.py collectstatic --no-input
   systemctl restart netbox netbox-rq
   ```

## API quick test
- Browse: `https://<netbox>/api/plugins/netbox-zabbix/monitoring-configs/`
- Sync feed: `https://<netbox>/api/plugins/netbox-zabbix/monitoring-configs/sync/`

## Notes
- This first cut ships API-only (no custom UI views). You can manage models via Django admin (`/admin/`) or the API.
- Secrets (Zabbix creds, SNMP creds) are **not** stored here—use references to AWX credentials instead.

MIT Licensed.
