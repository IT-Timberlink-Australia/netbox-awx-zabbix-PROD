# NetBox ⇄ Zabbix Operations (Timberlink)

## What lives here
- `zabbix_sync.yml` — Sync/Upsert NetBox Devices/VMs into Zabbix and write status back into NetBox.
- `zabbix_remove.yml` — Disable/Delete hosts in Zabbix and mark them `Removed` in NetBox.
- `inventory/netbox.yml` — Targets items with `zbp_status: "Not Synced"`.
- `inventory/netbox_remove.yml` — Targets items with `zbp_status: "Remove Pending"`.

## Required environment variables
NETBOX_API, NETBOX_TOKEN, NETBOX_VERIFY
ZABBIX_API_URL, ZABBIX_API_TOKEN, ZABBIX_VERIFY
ZBX_REMOVE_MODE (disable|delete, for removal job)

See `.env.example` for names. Set these in AWX Credential (Environment) or locally before running.

## Basic usage (local dev)
export $(grep -v '^#' .env | xargs)   # if you’ve created a local .env
ansible-playbook -i inventory/netbox.yml zabbix_sync.yml --syntax-check

## Notes
- TLS: start with ZABBIX_VERIFY=false, flip to true once the CA is in the EE.
- Statuses used in NetBox: Not Synced → Synced → Remove Pending → Removed.
