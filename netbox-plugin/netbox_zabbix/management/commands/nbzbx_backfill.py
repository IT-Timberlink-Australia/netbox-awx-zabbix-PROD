# /opt/netbox/plugins/netbox-zabbix/netbox_zabbix/management/commands/nbzbx_backfill.py
from dcim.models import Device
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.signals import post_save
from virtualization.models import VirtualMachine

from netbox_zabbix.utils import populate_monitoring_fields


class Command(BaseCommand):
    help = (
        "Populate monitoring CFs for Devices/VMs with mon_req=true (safe, batched, with progress)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max objects to process")
        parser.add_argument("--chunk-size", type=int, default=200, help="DB iterator chunk size")
        parser.add_argument("--devices-only", action="store_true", help="Only process Devices")
        parser.add_argument("--vms-only", action="store_true", help="Only process VMs")

    def handle(self, *args, **opts):
        # Avoid duplicate work caused by post_save signals
        try:
            post_save.disconnect(nbzbx_device_populate, sender=Device)
        except Exception:
            pass
        try:
            post_save.disconnect(nbzbx_vm_populate, sender=VirtualMachine)
        except Exception:
            pass

        chunk = int(opts.get("chunk_size") or 200)
        limit = opts.get("limit")
        only_devices = bool(opts.get("devices_only"))
        only_vms = bool(opts.get("vms_only"))

        total = updated = errors = 0

        def process(qs, label):
            nonlocal total, updated, errors
            qs = qs.select_related("platform", "site", "role").order_by("id")
            for obj in qs.iterator(chunk_size=chunk):
                if limit and total >= limit:
                    break
                total += 1
                try:
                    if populate_monitoring_fields(obj):
                        updated += 1
                except Exception as e:
                    errors += 1
                    self.stderr.write(
                        f"[{label}] id={obj.pk} name={getattr(obj, 'name', None)}: {e}"
                    )
                if total % 50 == 0:
                    self.stdout.write(f"... processed {total} (updated {updated}, errors {errors})")

        # mon_req may be stored as 'mon_req' or legacy 'cf_mon_req' in JSON
        mon_req_q = Q(custom_field_data__mon_req=True) | Q(custom_field_data__cf_mon_req=True)

        if not only_vms:
            d_qs = Device.objects.filter(mon_req_q)
            process(d_qs, "Device")

        if not only_devices:
            v_qs = VirtualMachine.objects.filter(mon_req_q)
            process(v_qs, "VM")

        self.stdout.write(
            self.style.SUCCESS(f"Done. processed={total}, updated={updated}, errors={errors}")
        )
