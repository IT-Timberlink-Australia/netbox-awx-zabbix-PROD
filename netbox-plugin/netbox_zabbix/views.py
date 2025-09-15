# /opt/netbox/plugins/netbox-zabbix/netbox_zabbix/views.py updated
from __future__ import annotations

from typing import Any, Iterable

from dcim.models import Device
from django.shortcuts import get_object_or_404, render
from extras.models import CustomField, CustomFieldChoiceSet
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

IFACE_LABELS = {"1": "Agent", "2": "SNMP", "3": "IPMI", "4": "JMX"}

def _cf_map(obj) -> dict[str, Any]:
    # NetBox v4 exposes .cf; fall back for older/edge cases
    data = getattr(obj, "cf", None)
    if isinstance(data, dict):
        return data
    return getattr(obj, "custom_field_data", {}) or {}

def get_cf(obj, key: str, default=None):
    return _cf_map(obj).get(key, default)

def _is_empty(v: Any) -> bool:
    return (
        v is None
        or (isinstance(v, str) and v.strip() == "")
        or (isinstance(v, (list, tuple, set)) and len(v) == 0)
    )

def _choice_label_from_set(val: Any, set_name: str | None) -> str | None:
    """Resolve a choice-set label by value (supports CF integer/string IDs)."""
    if not set_name:
        return None
    cs = CustomFieldChoiceSet.objects.filter(name=set_name).first()
    if not cs:
        return None
    for pair in (getattr(cs, "base_choices", []) or []) + (getattr(cs, "extra_choices", []) or []):
        if isinstance(pair, (list, tuple)) and len(pair) >= 2 and str(pair[0]) == str(val):
            return str(pair[1])
    return None

def _collect_items_and_status(obj):
    """
    Build rows for the template and compute completeness/status badge.
    RETURNS: (items, missing, badge)
    """
    items: list[dict[str, Any]] = []
    missing: list[str] = []

    name = getattr(obj, "name", None)
    descr = getattr(obj, "description", None) or ""
    vname = get_cf(obj, "cf_zb_vname") or (f"{name} - {descr}" if (name and descr) else None)

    platform = getattr(obj, "platform", None)
    pcf = getattr(platform, "custom_field_data", {}) if platform else {}
    pri_tmpl_id = pcf.get("zb_pri_template_id")
    pri_tmpl_name = pcf.get("zb_pri_template_name") or _choice_label_from_set(
        pri_tmpl_id, "zb_primary_template_list"
    )

    tmpl_int_id = pcf.get("zb_pri_template_int_id")
    tmpl_int_name = IFACE_LABELS.get(str(tmpl_int_id)) if tmpl_int_id is not None else None

    ip = get_cf(obj, "cf_zb_int_ip")
    if _is_empty(ip):
        ip4 = getattr(obj, "primary_ip4", None)
        if ip4 and getattr(ip4, "address", None):
            ip = str(ip4.address.ip)

    extra = get_cf(obj, "zb_extra_templates")
    if isinstance(extra, (list, tuple)):
        extra = ", ".join(str(x) for x in extra if x is not None) or None
    elif isinstance(extra, str):
        extra = ", ".join(s.strip() for s in extra.replace("\n", ",").split(",") if s.strip()) or None

    env = get_cf(obj, "zb_mon_env")
    os_text = get_cf(obj, "zbp_platform")
    site_text = get_cf(obj, "zbp_site")
    proxy_id = get_cf(obj, "zbp_proxy_id")
    group_id = get_cf(obj, "zbp_group_id")
    sla_code = get_cf(obj, "zbp_sla_code")

    items.extend(
        [
            {"label": "Host Name", "display": name},
            {"label": "Visible Name", "display": vname},
            {"label": "Primary Template ID", "display": pri_tmpl_id},
            {"label": "Primary Template", "display": pri_tmpl_name or pri_tmpl_id},
            {"label": "Template Interface ID", "display": tmpl_int_id},
            {"label": "Template Interface", "display": tmpl_int_name},
            {"label": "Host IP", "display": ip},
            {"label": "Extra Templates", "display": extra},
            {"label": "Environment", "display": env},
            {"label": "OS/Platform", "display": os_text},
            {"label": "Site", "display": site_text},
            {"label": "Zabbix Proxy ID", "display": proxy_id},
            {"label": "Zabbix Hostgroup ID", "display": group_id},
            {"label": "SLA Code", "display": sla_code},
        ]
    )

    for row in items:
        if _is_empty(row["display"]):
            missing.append(row["label"])

    badge = "ok" if not missing else ("caution" if ip and pri_tmpl_id else "fail")
    return items, missing, badge

@register_model_view(Device, name="monitoring", path="monitoring")
class DeviceMonitoringView(generic.ObjectView):
    queryset = Device.objects.all()
    tab = ViewTab(label="Monitoring")
    template_name = "netbox_zabbix/monitoring_tab.html"

    def get(self, request, pk):
        device = get_object_or_404(Device.objects.all(), pk=pk)
        items, missing, badge = _collect_items_and_status(device)
        return render(
            request,
            self.template_name,
            {"tab": self.tab, "object": device, "items": items, "missing": missing, "badge": badge},
        )

@register_model_view(VirtualMachine, name="monitoring", path="monitoring")
class VMMonitoringView(generic.ObjectView):
    queryset = VirtualMachine.objects.all()
    tab = ViewTab(label="Monitoring")
    template_name = "netbox_zabbix/monitoring_tab.html"

    def get(self, request, pk):
        vm = get_object_or_404(VirtualMachine.objects.all(), pk=pk)
        items, missing, badge = _collect_items_and_status(vm)
        return render(
            request,
            self.template_name,
            {"tab": self.tab, "object": vm, "items": items, "missing": missing, "badge": badge},
        )
