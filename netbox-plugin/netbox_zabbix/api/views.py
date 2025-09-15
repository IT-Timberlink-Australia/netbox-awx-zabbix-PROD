from typing import Any

from dcim.models import Device
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema
from extras.models import CustomField
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from virtualization.models import VirtualMachine

from ..models import MonitoringConfig

# ---------- helpers (mirrors the tab logic) ----------


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y", "enabled", "enable"}


def _get_cf(obj, key: str, default=None):
    if not obj:
        return default
    data = getattr(obj, "custom_field_data", None) or getattr(obj, "_custom_field_data", None) or {}
    alt = key[3:] if key.startswith("cf_") else f"cf_{key}"
    return data.get(key, data.get(alt, data.get(key.strip(), default)))


def _label_and_id(cf: dict, name_key: str, id_key: str) -> tuple[str | None, Any | None]:
    if not cf:
        return (None, None)
    label = cf.get(f"{name_key}_label") or cf.get(f"cf_{name_key}_label")
    idv = cf.get(id_key) or cf.get(f"cf_{id_key}")
    raw = cf.get(name_key) or cf.get(f"cf_{name_key}")
    if raw is not None:
        s = str(raw).strip()
        if s.isdigit():
            idv = idv or int(s)
        elif not label:
            label = s
    return (label, idv)


def _choice_label(value, field_names: tuple[str, ...]) -> str | None:
    """Resolve a label from any CustomField choice-set given the stored value (NetBox 4.4)."""
    if value in (None, ""):
        return None
    cfs = CustomField.objects.filter(name__in=field_names).select_related("choice_set")
    for cf in cfs:
        cs = getattr(cf, "choice_set", None)
        if not cs:
            continue
        # Preferred: concrete choice rows
        choices_mgr = getattr(cs, "choices", None)
        if hasattr(choices_mgr, "filter"):
            ch = choices_mgr.filter(value=str(value)).first()
            if ch:
                return getattr(ch, "label", None)
        # Fallback arrays (defensive)
        base = list(getattr(cs, "base_choices", []) or [])
        extra = list(getattr(cs, "extra_choices", []) or [])
        for pair in base + extra:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                k, lbl = str(pair[0]), pair[1]
                if k == str(value):
                    return lbl
    return None


def _zbx_iface_label(v) -> str:
    try:
        i = int(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else ""
    return {1: "Agent", 2: "SNMP", 3: "IPMI", 4: "JMX"}.get(i, str(v))


def _as_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(x) for x in val]
    # CSV / newline tolerant
    return [s.strip() for s in str(val).replace("\n", ",").split(",") if s.strip()]


def _missing_required(d: dict[str, Any]) -> list[str]:
    return [k for k, v in d.items() if v in (None, "", [], {})]


def _badge_for(zbx_status: str, complete: bool) -> str:
    """Mirror the tab badge: ok=✅, caution=⚠️, fail=❌ (names only here)."""
    if complete and str(zbx_status).strip().lower() == "synced":
        return "ok"
    elif complete:
        return "caution"
    else:
        return "fail"


# ---------- core builder ----------


def _build_host(obj, is_device: bool) -> dict[str, Any]:
    # Names
    name = getattr(obj, "name", None)
    description = getattr(obj, "description", None)
    vname_cf = _get_cf(obj, "cf_zb_vname")
    visible_name = vname_cf if vname_cf else (f"{name} - {description}" if description else None)

    # Platform-derived fields
    platform = getattr(obj, "platform", None)
    plat_cf = getattr(platform, "custom_field_data", {}) if platform else {}
    pri_tmpl_label, pri_tmpl_id = _label_and_id(
        plat_cf, "zb_pri_template_name", "zb_pri_template_id"
    )
    tmpl_int_label, tmpl_int_id = _label_and_id(
        plat_cf, "zb_pri_template_int_name", "zb_pri_template_int_id"
    )

    # If no template label, resolve via CF choice-set (supports your zb_primary_template_list)
    if not pri_tmpl_label and pri_tmpl_id is not None:
        pri_tmpl_label = _choice_label(
            pri_tmpl_id,
            ("zb_pri_template_id", "zb_primary_template_list", "zb_pri_template_name"),
        )

    # Host IP
    ip = _get_cf(obj, "cf_zb_int_ip")
    if not ip:
        ip4 = getattr(obj, "primary_ip4", None)
        if ip4 and getattr(ip4, "address", None):
            ip = str(ip4.address.ip)

    # Extra templates (IDs) + optional labels
    extra_ids = _as_list(
        _get_cf(obj, "cf_zb_extra_templates") or _get_cf(obj, "zb_extra_templates")
    )
    extra_labels = []
    for tid in extra_ids:
        lbl = _choice_label(tid, ("zb_extra_template_list", "zb_primary_template_list"))
        extra_labels.append(lbl or None)

    # Misc/tags
    env = _get_cf(obj, "cf_zb_mon_env") or _get_cf(obj, "zb_mon_env")
    os_slug = getattr(platform, "slug", None)
    site = getattr(obj, "site", None)
    site_slug = getattr(site, "slug", None)

    # Proxy/Group IDs (prefer Site CFs, fallback to object CFs)
    zbx_proxy_id = (
        _get_cf(site, "cf_zb_proxy_id")
        or _get_cf(site, "zb_proxy_id")
        or _get_cf(obj, "cf_zb_proxy_id")
        or _get_cf(obj, "zb_proxy_id")
    )
    zbx_group_id = (
        _get_cf(site, "cf_zb_group_id")
        or _get_cf(site, "zb_group_id")
        or _get_cf(obj, "cf_zb_group_id")
        or _get_cf(obj, "zb_group_id")
    )

    # SLA code (role attr/CF)
    role = getattr(obj, "role", None)
    sla_code = None
    if role:
        sla_code = getattr(role, "sla_report_code", None)
        if not sla_code:
            rcf = getattr(role, "custom_field_data", {}) or {}
            sla_code = rcf.get("sla_report_code")

    # NetBox status (for tag nb_status)
    try:
        nb_status = getattr(obj.status, "value", None)  # StatusField
    except Exception:
        nb_status = getattr(obj, "status", None)

    # Zabbix Status from MonitoringConfig
    ct = ContentType.objects.get_for_model(obj)
    cfg = (
        MonitoringConfig.objects.filter(content_type=ct, object_id=obj.pk)
        .order_by("-last_synced")
        .first()
    )
    zbx_status = cfg.last_sync_status if cfg and cfg.last_sync_status else "Not Synced"

    # Required-field completeness (everything except extra templates)
    required = {
        "host_name": name,
        "visible_name": visible_name,
        "primary_template_id": pri_tmpl_id,
        "template_interface_id": tmpl_int_id,
        "interface_ip": ip,
        "environment": env,
        "os": os_slug,
        "site": site_slug,
        "proxy_id": zbx_proxy_id,
        "group_id": zbx_group_id,
        "sla_code": sla_code,
    }
    missing = _missing_required(required)
    complete = len(missing) == 0
    badge = _badge_for(zbx_status, complete)

    # Final mapped object for AWX
    return {
        "type": "device" if is_device else "vm",
        "id": obj.pk,
        "name": name,  # Zabbix host name
        "visible_name": visible_name,  # Zabbix visible name
        # Templates
        "primary_template": {
            "id": pri_tmpl_id,
            "name": pri_tmpl_label,
        },
        "extra_templates": [
            {"id": tid, "name": (lbl if lbl else None)} for tid, lbl in zip(extra_ids, extra_labels)
        ],
        # Interface
        "interface": {
            "type_id": tmpl_int_id,
            "type_label": _zbx_iface_label(tmpl_int_id),
            "ip": ip,
        },
        # Zabbix placement
        "proxy_id": zbx_proxy_id,  # “Monitored by”
        "group_id": zbx_group_id,  # Host group
        # Tags for Zabbix
        "tags": {
            "environment": env,
            "os": os_slug,
            "site": site_slug,
            "device": sla_code,  # SLA Code → tag 'device'
            "nb_status": nb_status,  # dcim.devices.status → tag 'nb_status'
        },
        # Completeness signals (and tab badge mirror)
        "zabbix_status": zbx_status,  # "Synced" / "Not Synced"
        "complete": complete,
        "missing": missing,
        "badge": badge,  # "ok" | "caution" | "fail"
    }


# ---------- API view ----------


class AwxInventoryView(APIView):
    permission_classes = [IsAuthenticated]

    schema = None

    @extend_schema(exclude=True)
    def get(self, request, format=None):
        hosts: list[dict[str, Any]] = []

        # Devices
        for d in Device.objects.select_related("platform", "site", "role"):
            if not _truthy(_get_cf(d, "cf_mon_req")):
                continue
            hosts.append(_build_host(d, is_device=True))

        # VMs
        for vm in VirtualMachine.objects.select_related("platform", "site", "role", "cluster"):
            if not _truthy(_get_cf(vm, "cf_mon_req")):
                continue
            hosts.append(_build_host(vm, is_device=False))

        # Optional filtering by badge state (ok | caution | fail)
        want_badge = (request.query_params.get("badge") or "").strip().lower()
        if want_badge in {"ok", "caution", "fail"}:
            hosts = [h for h in hosts if h.get("badge") == want_badge]

        # Summary
        summary = {
            "count": len(hosts),
            "ok": sum(1 for h in hosts if h["badge"] == "ok"),
            "caution": sum(1 for h in hosts if h["badge"] == "caution"),
            "fail": sum(1 for h in hosts if h["badge"] == "fail"),
        }
        return Response({"netbox": summary, "hosts": hosts})
