# NetBox-AWX-Zabbix Integration

A comprehensive solution for integrating NetBox with Zabbix through AWX automation.

## Architecture Overview
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ NetBox │───▶│ AWX │───▶│ Zabbix │
│ (CMDB) │ │(Automation) │ │(Monitoring) │
└─────────────┘ └─────────────┘ └─────────────┘


## Components

### NetBox Plugin (`netbox-plugin/`)
- Stores Zabbix configuration in custom fields
- Provides REST API endpoints for AWX consumption
- Handles background tasks for data population

### Ansible Playbooks (`ansible-playbooks/`)
- Directory structure prepared for future Ansible automation
- Roles for NetBox and Zabbix synchronization
- Inventory management for dynamic host discovery

### AWX Configuration (`awx-config/`)
- Job templates for automation workflows
- Inventory sources for dynamic host management
- Credential management for secure operations

## Current Status

- ✅ **NetBox Plugin**: Fully functional and ready for use
- 🔄 **AWX Integration**: API endpoints ready, job templates to be configured
- 📋 **Ansible Playbooks**: Directory structure prepared for future development
- 📚 **Documentation**: Comprehensive guides available

## Quick Start

1. **Install NetBox Plugin:**
   ```bash
   cd netbox-plugin
   pip install -e .
   ```

2. **Configure NetBox:**
   ```python
   PLUGINS = ['netbox_zabbix']
   PLUGINS_CONFIG = {
       'netbox_zabbix': {}
   }
   ```

3. **Set Environment Variables:**
   ```bash
   export AWX_API_BASE="https://awx.timberlinkaustralia.com.au"
   export AWX_API_TOKEN="your_token_here"
   ```

## Documentation

- [Installation Guide](docs/installation.md)
- [Configuration Guide](docs/configuration.md)
- [API Reference](docs/api-reference.md)
- [Troubleshooting](docs/troubleshooting.md)

## License

MIT License - see LICENSE file for details.
