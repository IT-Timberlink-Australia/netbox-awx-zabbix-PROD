.PHONY: collections syntax lint dev-sync dev-remove

collections:
	ansible-galaxy collection install -r requirements.yml

syntax:
	ansible-playbook -i inventory/netbox.yml zabbix_sync.yml --syntax-check
	ansible-playbook -i inventory/netbox_remove.yml zabbix_remove.yml --syntax-check

# Local "does it parse & resolve env" test (no remote hosts).
dev-sync:
	ansible-playbook -i inventory/netbox.yml zabbix_sync.yml --check

dev-remove:
	ansible-playbook -i inventory/netbox_remove.yml zabbix_remove.yml --check
