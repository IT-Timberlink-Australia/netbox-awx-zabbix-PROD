import logging

from dcim.models import Device, Platform, Site
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from virtualization.models import VirtualMachine

from .tasks import (
    _awx_cfg,
    schedule_awx_inventory_refresh,
    update_related_for_platform,
    update_related_for_site,
)
from .utils import populate_monitoring_fields, truthy

logger = logging.getLogger("netbox.plugins.netbox_zabbix")


def _old_status_for(obj):
    model = obj.__class__
    if obj.pk:
        old = (
            model.objects.filter(pk=obj.pk).values_list("custom_field_data", flat=True).first()
            or {}
        )
        return (old or {}).get("zbp_status") or (old or {}).get("cf_zbp_status")
    return None


def _new_status_for(obj):
    cfd = getattr(obj, "custom_field_data", {}) or {}
    return cfd.get("zbp_status") or cfd.get("cf_zbp_status")


@receiver(pre_save, sender=Device)
def nbzbx_device_presave(sender, instance: Device, **kwargs):
    try:
        instance._nbzbx_old_status = _old_status_for(instance)
        # Compute/populate *in memory*; NetBox will persist on save
        populate_monitoring_fields(instance, validate=False, save=False, overwrite_source=True)
        instance._nbzbx_new_status = _new_status_for(instance)
    except Exception:
        logger.exception(
            "pre_save populate failed for Device id=%s name=%s",
            getattr(instance, "pk", None),
            getattr(instance, "name", None),
        )


@receiver(pre_save, sender=VirtualMachine)
def nbzbx_vm_presave(sender, instance: VirtualMachine, **kwargs):
    try:
        instance._nbzbx_old_status = _old_status_for(instance)
        populate_monitoring_fields(instance, validate=False, save=False, overwrite_source=True)
        instance._nbzbx_new_status = _new_status_for(instance)
    except Exception:
        logger.exception(
            "pre_save populate failed for VM id=%s name=%s",
            getattr(instance, "pk", None),
            getattr(instance, "name", None),
        )


def _queue_after_commit(fn, *args, **kwargs):
    """
    Ensure AWX calls only fire after the DB commit finishes,
    so NetBox filters see the *new* zbp_status.
    """

    def _call():
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Deferred call failed: %s", fn)

    transaction.on_commit(_call)


def _route_refresh(instance):
    """
    Decide which AWX source to refresh and do it *after commit* to avoid races.
    """
    cfd = getattr(instance, "custom_field_data", {}) or {}
    mon = cfd.get("mon_req") or cfd.get("cf_mon_req")
    old_status = getattr(instance, "_nbzbx_old_status", None)
    new_status = getattr(instance, "_nbzbx_new_status", _new_status_for(instance))
    cfg = _awx_cfg()

    logger.info(
        "NBZBX transition %s id=%s mon_req=%s old=%s new=%s src=%s rm_src=%s",
        type(instance).__name__,
        instance.pk,
        mon,
        old_status,
        new_status,
        cfg.get("source_id"),
        cfg.get("remove_source_id"),
    )

    # No actual change → nothing to do
    if old_status == new_status:
        return

    # Removal path: mon_req off OR status changed to Remove Pending
    if not truthy(mon) or new_status == "Remove Pending":
        rm_sid = cfg.get("remove_source_id")
        if rm_sid:
            logger.info(
                "Scheduling removal-source refresh after commit for id=%s source_id=%s",
                instance.pk,
                rm_sid,
            )
            _queue_after_commit(schedule_awx_inventory_refresh, source_id=rm_sid)
        else:
            logger.warning(
                "AWX_REMOVE_SOURCE_ID not set; cannot refresh removal inventory for id=%s",
                instance.pk,
            )
        return

    # Normal path: only refresh primary on Not Synced / Missing Data / Synced
    if new_status in ("Not Synced", "Missing Data", "Synced"):
        logger.info(
            "Scheduling primary-source refresh after commit for id=%s source_id=%s",
            instance.pk,
            cfg.get("source_id"),
        )
        _queue_after_commit(schedule_awx_inventory_refresh)
    else:
        logger.info(
            "AWX refresh skipped for id=%s old=%s new=%s mon_req=%s",
            instance.pk,
            old_status,
            new_status,
            mon,
        )


@receiver(post_save, sender=Device)
def nbzbx_device_postsave(sender, instance: Device, **kwargs):
    try:
        _route_refresh(instance)
    except Exception:
        logger.exception("post_save decision failed for Device id=%s", instance.pk)


@receiver(post_save, sender=VirtualMachine)
def nbzbx_vm_postsave(sender, instance: VirtualMachine, **kwargs):
    try:
        _route_refresh(instance)
    except Exception:
        logger.exception("post_save decision failed for VM id=%s", instance.pk)


# -------- Cascades when Platform/Site change --------


@receiver(post_save, sender=Platform)
def nbzbx_platform_changed(sender, instance: Platform, **kwargs):
    try:
        update_related_for_platform.delay(instance.pk)
        logger.info(
            "Queued platform cascade for Platform id=%s slug=%s",
            instance.pk,
            instance.slug,
        )
    except Exception:
        logger.exception("Failed to enqueue platform cascade for Platform id=%s", instance.pk)


@receiver(post_save, sender=Site)
def nbzbx_site_changed(sender, instance: Site, **kwargs):
    try:
        update_related_for_site.delay(instance.pk)
        logger.info("Queued site cascade for Site id=%s slug=%s", instance.pk, instance.slug)
    except Exception:
        logger.exception("Failed to enqueue site cascade for Site id=%s", instance.pk)
