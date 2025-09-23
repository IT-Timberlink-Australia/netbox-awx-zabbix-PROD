# AWX Workflow Setup Guide
## Conditional Zabbix Sync Based on Inventory Host Count

This guide explains how to set up an AWX workflow that:
1. Updates the NetBox inventory source
2. Checks if the "Stage - Add Zabbix" inventory has hosts
3. Conditionally runs the "WF - PROD - Zabbix Sync" workflow if hosts exist

## 📋 Prerequisites

- AWX/Ansible Tower access with admin permissions
- NetBox inventory source already configured
- "WF - PROD - Zabbix Sync" workflow already exists
- "Stage - Add Zabbix" inventory already exists

## 🔧 Step 1: Create Host Count Check Job Template

### 1.1 Navigate to Job Templates
- Go to **Templates** → **Job Templates** in AWX
- Click **+ Add** → **Add Job Template**

### 1.2 Configure Job Template
- **Name**: `Check Stage - Add Zabbix Host Count`
- **Job Type**: `Run`
- **Inventory**: `Stage - Add Zabbix`
- **Project**: Your NetBox-Zabbix project
- **Playbook**: `check_host_count.yml`
- **Credentials**: Any required credentials (if needed)
- **Verbosity**: `1 (Verbose)`

### 1.3 Save the Job Template
- Click **Save**

## 🔧 Step 2: Create the Workflow Template

### 2.1 Navigate to Workflow Templates
- Go to **Templates** → **Workflow Templates** in AWX
- Click **+ Add** → **Add Workflow Template**

### 2.2 Configure Workflow Template
- **Name**: `NetBox Inventory → Conditional Zabbix Sync`
- **Organization**: Your organization
- **Description**: `Updates NetBox inventory and conditionally runs Zabbix sync if hosts exist`

### 2.3 Add Workflow Nodes

#### Node 1: NetBox Inventory Source Update
- **Node Type**: `Job Template`
- **Job Template**: `NetBox Inventory Source` (your existing inventory source)
- **Node Alias**: `Update NetBox Inventory`
- **Run Condition**: `Always`
- **Success Nodes**: `Check Host Count`
- **Failure Nodes**: `Check Host Count` (continue even if inventory update fails)

#### Node 2: Check Host Count
- **Node Type**: `Job Template`
- **Job Template**: `Check Stage - Add Zabbix Host Count`
- **Node Alias**: `Check Host Count`
- **Run Condition**: `Always`
- **Depends On**: `Update NetBox Inventory`
- **Success Nodes**: `Run Zabbix Sync`
- **Failure Nodes**: None (stop on failure)

#### Node 3: Run Zabbix Sync Workflow
- **Node Type**: `Workflow Job Template`
- **Job Template**: `WF - PROD - Zabbix Sync`
- **Node Alias**: `Run Zabbix Sync`
- **Run Condition**: `Custom`
- **Custom Condition**: `{{ stage_add_zabbix_has_hosts }}`
- **Depends On**: `Check Host Count`

### 2.4 Save the Workflow
- Click **Save**

## 🔧 Step 3: Test the Workflow

### 3.1 Manual Test
1. Go to **Templates** → **Workflow Templates**
2. Find `NetBox Inventory → Conditional Zabbix Sync`
3. Click **Launch**
4. Monitor the execution

### 3.2 Expected Behavior
- **Node 1**: Updates NetBox inventory source
- **Node 2**: Checks host count and sets facts
- **Node 3**: Only runs if `stage_add_zabbix_has_hosts` is true

## 📊 Monitoring and Troubleshooting

### 3.3 Check Workflow Results
- **No hosts found**: Node 3 should be skipped (gray)
- **Hosts found**: Node 3 should run (green/blue)

### 3.4 Common Issues
1. **Job Template not found**: Ensure all job templates exist
2. **Inventory not found**: Verify "Stage - Add Zabbix" inventory exists
3. **Workflow not found**: Verify "WF - PROD - Zabbix Sync" exists
4. **Permission issues**: Check AWX permissions for workflow execution

## 🔄 Step 4: Schedule the Workflow (Optional)

### 4.1 Create Schedule
- Go to **Templates** → **Workflow Templates**
- Select `NetBox Inventory → Conditional Zabbix Sync`
- Go to **Schedules** tab
- Click **+ Add Schedule**

### 4.2 Configure Schedule
- **Name**: `Daily NetBox-Zabbix Sync`
- **Schedule**: Set your desired frequency (e.g., every 30 minutes)
- **Enabled**: Yes

## 📝 Variables and Facts

The workflow uses these facts set by the host count check:

- `stage_add_zabbix_host_count`: Number of hosts in inventory
- `stage_add_zabbix_has_hosts`: Boolean indicating if hosts exist
- `inventory_name`: Name of the inventory being checked

## 🎯 Expected Workflow Flow

```
┌─────────────────────────┐
│ 1. Update NetBox        │
│    Inventory Source     │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│ 2. Check Host Count     │
│    in "Stage - Add      │
│    Zabbix" Inventory    │
└─────────┬───────────────┘
          │
          ▼
    ┌─────────┐
    │ Has     │
    │ Hosts?  │
    └────┬────┘
         │
    ┌────▼────┐
    │   YES   │
    └────┬────┘
         │
         ▼
┌─────────────────────────┐
│ 3. Run WF - PROD -      │
│    Zabbix Sync          │
└─────────────────────────┘
```

## ✅ Success Criteria

- ✅ NetBox inventory updates successfully
- ✅ Host count is accurately determined
- ✅ Zabbix sync only runs when hosts exist
- ✅ Workflow completes without errors
- ✅ Logs show clear decision-making process

## 🔧 Advanced Configuration

### Custom Conditions
You can modify the custom condition in Node 3 to add more complex logic:

- `{{ stage_add_zabbix_has_hosts and stage_add_zabbix_host_count > 5 }}` (only if more than 5 hosts)
- `{{ stage_add_zabbix_has_hosts and ansible_date_time.hour >= 9 and ansible_date_time.hour <= 17 }}` (only during business hours)

### Notification Integration
Add notification templates to alert on:
- Workflow completion
- Zabbix sync execution
- Host count changes
