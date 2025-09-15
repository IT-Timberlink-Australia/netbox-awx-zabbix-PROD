"""
Background jobs for cascading updates when Platform/Site (source-of-truth) changes.
Runs on the netbox-rq worker.
"""

import logging
import os

import requests
from dcim.models import Device, Platform, Site
from django.db.models import Q
from django_rq import get_connection, job
from virtualization.models import VirtualMachine

from .utils import populate_monitoring_fields


BATCH = 200  # iterator chunk size


def _awx_cfg():
    return {
        "base": os.getenv("AWX_API_BASE", "").rstrip("/"),
        "token": os.getenv("AWX_API_TOKEN"),
        "verify": str(os.getenv("AWX_VERIFY", "true")).lower() in ("1", "true", "yes"),
        "source_id": int(os.getenv("AWX_INVENTORY_SOURCE_ID", "0") or 0),
        "remove_source_id": int(os.getenv("AWX_REMOVE_SOURCE_ID", "0") or 0),
        "debounce": int(os.getenv("AWX_DEBOUNCE_SECONDS", "60") or 60),
    }


@job("default", timeout=60)
def awx_refresh_inventory(source_id: int, base: str = "", token: str = "", verify: bool = True):
    base = base.rstrip("/")
    url = f"{base}/inventory_sources/{source_id}/update/"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={}, verify=verify, timeout=30)
        r.raise_for_status()
        logger.info(
            "AWX inventory refresh triggered for source_id=%s status=%s",
            source_id,
            r.status_code,
        )
    except Exception as e:
        logger.exception("AWX inventory refresh failed for source_id=%s: %s", source_id, e)
        raise


def schedule_awx_inventory_refresh(source_id: int | None = None):
    """
    Debounce using Redis: only one refresh per source within AWX_DEBOUNCE_SECONDS.
    """
    cfg = _awx_cfg()
    source_id = int(source_id or cfg["source_id"] or 0)
    if not (cfg["base"] and cfg["token"] and source_id):
        logger.warning("AWX refresh skipped: missing base/token/source_id")
        return

    conn = get_connection("default")
    key = f"nbzbx:awx:invsrc:{source_id}:debounce"
    # set if not exists; expire for debounce window
    if conn.setnx(key, "1"):
        conn.expire(key, max(5, int(cfg["debounce"])))
        # queue the actual refresh
        awx_refresh_inventory.delay(
            source_id, base=cfg["base"], token=cfg["token"], verify=cfg["verify"]
        )
    else:
        logger.info("AWX refresh debounced for source_id=%s", source_id)


def _mon_req_q() -> Q:
    # Accept both keys in JSON CF blob, depending on how it was created
    return Q(custom_field_data__mon_req=True) | Q(custom_field_data__cf_mon_req=True)


def _process(qs):
    updated = errors = 0
    qs = qs.select_related("platform", "site", "role").order_by("id")
    for obj in qs.iterator(chunk_size=BATCH):
        try:
            if populate_monitoring_fields(obj, validate=False, save=True, overwrite_source=True):
                updated += 1
        except Exception:
            errors += 1
            continue
    return updated, errors


@job("default", timeout=600)
def update_related_for_platform(platform_id: int):
    """
    Refresh all mon_req=true Devices/VMs for a given Platform.
    """
    platform = Platform.objects.filter(pk=platform_id).first()
    if not platform:
        return {"updated": 0, "errors": 0}

    d_qs = Device.objects.filter(_mon_req_q(), platform=platform)
    v_qs = VirtualMachine.objects.filter(_mon_req_q(), platform=platform)

    du, de = _process(d_qs)
    vu, ve = _process(v_qs)
    return {"updated": du + vu, "errors": de + ve}

    res = {"updated": du + vu, "errors": de + ve}
    logger.info("Cascade %s result=%s", "platform", res)
    return res


@job("default", timeout=600)
def update_related_for_site(site_id: int):
    """
    Refresh all mon_req=true Devices/VMs for a given Site.
    """
    site = Site.objects.filter(pk=site_id).first()
    if not site:
        return {"updated": 0, "errors": 0}

    d_qs = Device.objects.filter(_mon_req_q(), site=site)
    v_qs = VirtualMachine.objects.filter(_mon_req_q(), site=site)

    du, de = _process(d_qs)
    vu, ve = _process(v_qs)
    return {"updated": du + vu, "errors": de + ve}

    res = {"updated": du + vu, "errors": de + ve}
    logger.info("Cascade %s result=%s", "platform", res)
    return res
