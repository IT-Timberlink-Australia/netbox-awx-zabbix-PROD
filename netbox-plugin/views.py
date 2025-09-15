from dcim.models import Device
from django.shortcuts import render
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine


# Helper: read custom fields robustly
def get_cf(obj, key, default=None):
    data = getattr(obj, "custom_field_data", None) or getattr(obj, "_custom_field_data", None) or {}
    # Some CF names in the sheet have stray spaces; normalize
    return data.get(key, data.get(key.strip(), default))


def truthy(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


class ConditionalTab(ViewTab):
    """A ViewTab that renders only if a condition(instance) returns True."""

    def __init__(self, *args, condition=None, **kwargs):
        self._condition = condition
        super().__init__(*args, **kwargs)

    def render(self, instance):
        if self._condition and not self._condition(instance):
            return None
        return super().render(instance)


def _collect_items(obj, is_device):
    # Common lookups
    name = getattr(obj, "name", None)
    description = getattr(obj, "description", "") or getattr(obj, "comments", "") or ""
    platform = getattr(obj, "platform", None)
    site = getattr(obj, "site", None)
    role = getattr(obj, "role", None)

    # Visible Name: CF override then fallback concat "name - description"
    cf_vname = get_cf(obj, "cf_zb_vname")
    vname = cf_vname or (f"{name} - {description}".strip(" -"))

    # Status: CF override then derived from model status
    cf_status = get_cf(obj, "cf_zb_status")
    if cf_status:
        status_text = str(cf_status)
    else:
        status = getattr(obj, "status", None)
        status_value = getattr(status, "value", None) if status else None
        status_text = "Enabled" if status_value == "active" else "Not Enable"

    # Primary Template & template interface from Platform custom fields
    plat_cf = getattr(platform, "custom_field_data", {}) if platform else {}
    pri_tmpl = plat_cf.get("zb_pri_template_name") or plat_cf.get("zb_pri_template_name".strip())
    tmpl_int_id = plat_cf.get("zb_pri_template_int_id") or plat_cf.get(
        "zb_pri_template_int_id".strip()
    )

    # Host IP Address: CF override then primary IPv4 (host-only)
    cf_int_ip = get_cf(obj, "cf_zb_int_ip")
    ip = None
    if cf_int_ip:
        ip = str(cf_int_ip)
    else:
        ip4 = getattr(obj, "primary_ip4", None)
        if ip4 and getattr(ip4, "address", None):
            ip = str(ip4.address.ip)

    # Extra templates (CF may be comma/space/line separated)
    extra_raw = get_cf(obj, "cf_zb_extra_templates") or get_cf(obj, "cf_zb_extra_templates ")
    extra_list = []
    if extra_raw:
        for part in str(extra_raw).replace("\n", ",").split(","):
            cleaned = part.strip()
            if cleaned:
                extra_list.append(cleaned)
    extra_templates = ", ".join(extra_list) if extra_list else None

    # Environment (CF on object)
    env = get_cf(obj, "cf_zb_mon_env")

    # OS from platform.slug
    os_slug = getattr(platform, "slug", None)

    # Site slug & site CFs for Zabbix proxy/group IDs
    site_slug = getattr(site, "slug", None)
    site_cf = getattr(site, "custom_field_data", {}) if site else {}
    zbx_proxy_id = site_cf.get("cf_zb_proxy_id")
    zbx_group_id = site_cf.get("cf_zb_group_id")

    # SLA code: try attribute then site/role CFs
    sla_code = None
    if role:
        sla_code = getattr(role, "sla_report_code", None)
        if not sla_code:
            role_cf = getattr(role, "custom_field_data", {})
            sla_code = role_cf.get("sla_report_code")

    items = [
        ("Host Name", name),
        ("Visible Name", vname),
        ("Status", status_text),
        ("Primary Template", pri_tmpl),
        ("Template Interface ID", tmpl_int_id),
        ("Host IP Address", ip),
        ("Extra Templates", extra_templates),
        ("Environment", env),
        ("OS", os_slug),
        ("Site", site_slug),
        ("Zabbix Proxy ID", zbx_proxy_id),
        ("Zabbix Group ID", zbx_group_id),
        ("SLA Code", sla_code),
    ]
    return items


def _cf_mon_req(obj):
    return truthy(get_cf(obj, "cf_mon_req"))


@register_model_view(Device, name="monitoring", path="monitoring")
class DeviceMonitoringView(generic.ObjectView):
    queryset = Device.objects.all()
    tab = ConditionalTab(label="Monitoring", weight=800, condition=_cf_mon_req)

    def get(self, request, pk):
        device = self.get_object(pk=pk)
        items = _collect_items(device, is_device=True)
        return render(
            request,
            "netbox_zabbix/monitoring_tab.html",
            context={"tab": self.tab, "object": device, "items": items},
        )


@register_model_view(VirtualMachine, name="monitoring", path="monitoring")
class VMMonitoringView(generic.ObjectView):
    queryset = VirtualMachine.objects.all()
    tab = ConditionalTab(label="Monitoring", weight=800, condition=_cf_mon_req)

    def get(self, request, pk):
        vm = self.get_object(pk=pk)
        items = _collect_items(vm, is_device=False)
        return render(
            request,
            "netbox_zabbix/monitoring_tab.html",
            context={"tab": self.tab, "object": vm, "items": items},
        )
