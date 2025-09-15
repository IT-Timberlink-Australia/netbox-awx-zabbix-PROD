import logging
from functools import lru_cache
from typing import Any

from django.core.exceptions import ValidationError
from extras.models import CustomField

logger = logging.getLogger("netbox.plugins.netbox_zabbix")

# Human labels for the Zabbix template interface type
IFACE_LABELS = {1: "Agent", 2: "SNMP", 3: "IPMI", 4: "JMX"}


# ------------------------ tiny helpers ------------------------


def truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y", "enabled", "enable"}


def _get_cfdata(obj) -> dict[str, Any]:
    return (getattr(obj, "custom_field_data", None) or {}).copy()


def _set_cf(obj, data: dict[str, Any]):
    setattr(obj, "custom_field_data", data)


def _get_cf(obj, key: str, default=None):
    data = getattr(obj, "custom_field_data", None) or {}
    return data.get(key, data.get(f"cf_{key}", default))


# ------------------------ CF metadata & caching ------------------------


@lru_cache(maxsize=128)
def _cf_meta(name: str) -> tuple[str | None, str | None]:
    cf = CustomField.objects.filter(name=name).first()
    if not cf:
        return (None, None)
    t = getattr(cf, "type", None)
    if hasattr(t, "value"):
        t = t.value
    dt = getattr(cf, "data_type", None)
    return (t, dt)


@lru_cache(maxsize=128)
def _cf_exists(name: str) -> bool:
    return CustomField.objects.filter(name=name).exists()


def _expects_list(name: str) -> bool:
    t, dt = _cf_meta(name)
    return t in {"multi-select"} or dt in {"array", "list"}


@lru_cache(maxsize=64)
def _choice_value_map(cf_name: str) -> dict[str, str]:
    cf = CustomField.objects.filter(name=cf_name).select_related("choice_set").first()
    if not cf or not getattr(cf, "choice_set", None):
        return {}
    m: dict[str, str] = {}

    mgr = getattr(cf.choice_set, "choices", None)
    if hasattr(mgr, "all"):
        for row in mgr.all():
            v = str(getattr(row, "value", "")).strip()
            lbl = str(getattr(row, "label", "")).strip()
            if v:
                m[v] = v
            if lbl:
                m[lbl] = v

    # Defensive fallback for legacy arrays
    for pair in (getattr(cf.choice_set, "base_choices", []) or []) + (
        getattr(cf.choice_set, "extra_choices", []) or []
    ):
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            v = str(pair[0]).strip()
            lbl = str(pair[1]).strip()
            if v:
                m[v] = v
            if lbl:
                m[lbl] = v
    return m


def _normalize_choice_field_value(cf_name: str, raw: Any, expects_list: bool) -> Any:
    mapping = _choice_value_map(cf_name)
    if not mapping:
        return raw

    def to_vals(seq) -> list[str]:
        out: list[str] = []
        for x in seq:
            s = str(x).strip()
            if not s:
                continue
            v = mapping.get(s)
            if v is None:
                lower = next((mapping[k] for k in mapping if k.lower() == s.lower()), None)
                if lower:
                    v = lower
            if v:
                out.append(v)
        seen = set()
        keep: list[str] = []
        for v in out:
            if v not in seen:
                seen.add(v)
                keep.append(v)
        return keep

    if expects_list:
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            return to_vals(raw)
        return to_vals(str(raw).replace("\n", ",").split(","))

    if raw is None:
        return None
    if isinstance(raw, (list, tuple, set)):
        vals = to_vals(raw)
        return vals[0] if vals else None
    s = str(raw).strip()
    if not s:
        return None
    return mapping.get(s) or next((mapping[k] for k in mapping if k.lower() == s.lower()), None)


# ------------------------ coercion helpers ------------------------


def _to_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _to_choice_str(v: Any) -> str | None:
    return _to_str(v)


def _to_iface_id_str(v: Any) -> str | None:
    return _to_str(v)


def _to_list_str(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return [s for s in (str(x).strip() for x in v) if s]
    return [s for s in (str(v).replace("\n", ",").split(",")) if s.strip()]


# ------------------------ main engine ------------------------


def populate_monitoring_fields(
    obj, *, validate: bool = False, save: bool = True, overwrite_source: bool = False
) -> bool:
    """
    Populate/normalize monitoring CFs on Device/VM.

    If mon_req=false, we still manage zbp_status (set to 'Remove Pending') but
    we do not attempt to populate other fields.
    """

    changed = False
    cf = _get_cfdata(obj)

    platform = getattr(obj, "platform", None)
    pcf = getattr(platform, "custom_field_data", {}) if platform else {}
    site = getattr(obj, "site", None)
    scf = getattr(site, "custom_field_data", {}) if site else {}
    role = getattr(obj, "role", None)
    rcf = getattr(role, "custom_field_data", {}) if role else {}

    mon_enabled = truthy(_get_cf(obj, "mon_req")) or truthy(_get_cf(obj, "cf_mon_req"))

    def put_if_empty(key: str, raw_value: Any, transform=_to_str):
        nonlocal changed
        if not _cf_exists(key):
            return
        if key not in cf or cf.get(key) in (None, "", [], {}):
            val = transform(raw_value)
            if val not in (None, "", [], {}):
                cf[key] = val
                changed = True

    def put_from_source(key: str, raw_value: Any, transform=_to_str):
        nonlocal changed
        if not _cf_exists(key):
            return
        cur = cf.get(key, None)
        if cur not in (None, "", [], {}) and not overwrite_source:
            return
        val = transform(raw_value)
        if val not in (None, "", [], {}):
            if cur != val:
                cf[key] = val
                changed = True

    # ------------------ If monitoring is disabled: mark Remove Pending ------------------
    if not mon_enabled:
        if _cf_exists("zbp_status"):
            if cf.get("zbp_status") != "Remove Pending":
                cf["zbp_status"] = "Remove Pending"
                changed = True
        if changed:
            _set_cf(obj, cf)
            if save:
                if validate:
                    try:
                        obj.full_clean()
                    except ValidationError as ve:
                        logger.error(
                            "ValidationError saving %s id=%s name=%s errors=%r custom_field_data=%r",
                            type(obj).__name__,
                            obj.pk,
                            getattr(obj, "name", None),
                            ve.message_dict,
                            cf,
                        )
                        raise
                obj.save(update_fields=["custom_field_data"])
        return changed

    # ------------------ Monitoring enabled: populate fields ------------------

    # Visible Name
    if _cf_exists("zbp_vname") and not cf.get("zbp_vname"):
        desc = getattr(obj, "description", None)
        if desc:
            cf["zbp_vname"] = f"{getattr(obj, 'name', '')} - {desc}"
            changed = True

    # Host IP
    put_if_empty("zbp_int_ip", _get_cf(obj, "zbp_int_ip"), _to_str)
    if _cf_exists("zbp_int_ip") and not cf.get("zbp_int_ip"):
        ip4 = getattr(obj, "primary_ip4", None)
        if ip4 and getattr(ip4, "address", None):
            cf["zbp_int_ip"] = str(ip4.address.ip)
            changed = True

    # Primary Template from Platform CF 'zb_pri_template_name'
    plat_tmpl_val = pcf.get("zb_pri_template_name")
    put_from_source("zbp_pri_template_name_id", plat_tmpl_val, _to_choice_str)

    if _cf_exists("zbp_pri_template_name"):
        stored_value = _normalize_choice_field_value(
            "zb_pri_template_name", plat_tmpl_val, expects_list=False
        )
        label = None
        if stored_value:
            rev = {v: k for k, v in _choice_value_map("zb_pri_template_name").items()}
            label = rev.get(stored_value)
        if overwrite_source or not cf.get("zbp_pri_template_name"):
            if label and cf.get("zbp_pri_template_name") != label:
                cf["zbp_pri_template_name"] = label
                changed = True

    # Template Interface ID/Name
    plat_int_id = (
        pcf.get("zb_pri_template_int_id")
        or pcf.get("zbp_pri_template_int_id")
        or pcf.get("zb_template_interface_id")
    )

    if not plat_int_id:
        tmpl_label = (
            cf.get("zbp_pri_template_name") if _cf_exists("zbp_pri_template_name") else None
        )
        if not tmpl_label and plat_tmpl_val:
            stored_value = _normalize_choice_field_value(
                "zb_pri_template_name", plat_tmpl_val, expects_list=False
            )
            if stored_value:
                rev = {v: k for k, v in _choice_value_map("zb_pri_template_name").items()}
                tmpl_label = rev.get(stored_value)

        if tmpl_label:
            low = str(tmpl_label).lower()
            if "snmp" in low:
                plat_int_id = "2"
            elif "ipmi" in low:
                plat_int_id = "3"
            elif "jmx" in low:
                plat_int_id = "4"
            else:
                plat_int_id = "1"

    put_from_source("zbp_pri_template_int_id", plat_int_id, _to_iface_id_str)

    if _cf_exists("zbp_pri_template_int_name"):
        lbl = None
        try:
            i = int(str(plat_int_id)) if plat_int_id is not None else None
            lbl = IFACE_LABELS.get(i)
        except Exception:
            lbl = None
        if overwrite_source or not cf.get("zbp_pri_template_int_name"):
            if lbl and cf.get("zbp_pri_template_int_name") != lbl:
                cf["zbp_pri_template_int_name"] = lbl
                changed = True

    # Platform / Site slugs
    if platform:
        put_from_source("zbp_platform", getattr(platform, "slug", None), _to_str)
    if site:
        put_from_source("zbp_site", getattr(site, "slug", None), _to_str)

    # Proxy / Group / SLA
    put_from_source("zbp_proxy_id", scf.get("zb_proxy_id"), _to_str)
    put_from_source("zbp_group_id", scf.get("zb_group_id"), _to_str)
    put_from_source(
        "zbp_sla_code",
        getattr(role, "sla_report_code", None) or rcf.get("sla_report_code"),
        _to_str,
    )

    # Extra templates normalization (legacy field lives on object)
    if "zb_extra_templates" in cf:
        expects_list = _expects_list("zb_extra_templates")
        cf["zb_extra_templates"] = _normalize_choice_field_value(
            "zb_extra_templates",
            cf.get("zb_extra_templates"),
            expects_list,
        )
        changed = True

    # ---- Zabbix Status state machine (Missing Data / Not Synced / Synced) ----
    def _nonempty(x):
        return x not in (None, "", [], {})

    def _val(key):
        return cf.get(key)

    required_keys = [
        "zbp_vname",
        "zbp_int_ip",
        "zbp_pri_template_name_id",
        "zbp_pri_template_int_id",
        "zbp_proxy_id",
        "zbp_group_id",
        "zbp_sla_code",
    ]
    for opt in ("zbp_platform", "zbp_site"):
        if _cf_exists(opt):
            required_keys.append(opt)

    existing_reqs = [k for k in required_keys if _cf_exists(k)]
    env_ok = _nonempty(_get_cf(obj, "zb_mon_env"))
    complete = env_ok and all(_nonempty(_val(k)) for k in existing_reqs)

    if _cf_exists("zbp_status"):
        current = cf.get("zbp_status")
        if complete:
            desired = "Synced" if current == "Synced" else "Not Synced"
        else:
            desired = "Missing Data"
        if current != desired:
            cf["zbp_status"] = desired
            changed = True

    # ---- save if changed ----
    if changed:
        _set_cf(obj, cf)
        if save:
            if validate:
                try:
                    obj.full_clean()
                except ValidationError as ve:
                    logger.error(
                        "ValidationError saving %s id=%s name=%s errors=%r custom_field_data=%r",
                        type(obj).__name__,
                        obj.pk,
                        getattr(obj, "name", None),
                        ve.message_dict,
                        cf,
                    )
                    raise
            obj.save(update_fields=["custom_field_data"])

    return changed
