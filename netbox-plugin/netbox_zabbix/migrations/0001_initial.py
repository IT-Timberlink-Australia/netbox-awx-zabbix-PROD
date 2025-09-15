import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="ZabbixEndpoint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.SlugField(unique=True)),
                (
                    "api_url",
                    models.URLField(
                        help_text="Zabbix base URL, e.g. https://svrnmzb01.timberlinkaustralia.com.au"
                    ),
                ),
                (
                    "awx_job_template_id",
                    models.PositiveIntegerField(
                        help_text="Reference to AWX job template ID used for sync"
                    ),
                ),
                (
                    "awx_credential_name",
                    models.CharField(
                        blank=True,
                        help_text="Reference to AWX credential name",
                        max_length=128,
                    ),
                ),
                ("comments", models.TextField(blank=True)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Proxy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=255)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxies",
                        to="netbox_zabbix.zabbixendpoint",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("endpoint", "name")},
            },
        ),
        migrations.CreateModel(
            name="Template",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=255)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="templates",
                        to="netbox_zabbix.zabbixendpoint",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("endpoint", "name")},
            },
        ),
        migrations.CreateModel(
            name="HostGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=255)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hostgroups",
                        to="netbox_zabbix.zabbixendpoint",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("endpoint", "name")},
            },
        ),
        migrations.CreateModel(
            name="MonitoringConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict)),
                ("object_id", models.PositiveIntegerField()),
                ("enabled", models.BooleanField(default=True)),
                (
                    "desired_state",
                    models.CharField(
                        choices=[("present", "present"), ("absent", "absent")],
                        default="present",
                        max_length=8,
                    ),
                ),
                (
                    "zabbix_name",
                    models.CharField(
                        blank=True,
                        help_text="Defaults to Device/VM name if blank",
                        max_length=255,
                    ),
                ),
                ("visible_name", models.CharField(blank=True, max_length=255)),
                (
                    "interface_policy",
                    models.CharField(
                        choices=[
                            ("primary_ip", "Primary IP"),
                            ("mgmt_if", "Management interface"),
                            ("first_up", "First up"),
                        ],
                        default="primary_ip",
                        max_length=32,
                    ),
                ),
                ("agent_port", models.PositiveIntegerField(default=10050)),
                ("snmp_enabled", models.BooleanField(default=False)),
                (
                    "snmp_version",
                    models.CharField(
                        blank=True, choices=[("v2c", "v2c"), ("v3", "v3")], max_length=8
                    ),
                ),
                ("snmp_port", models.PositiveIntegerField(default=161)),
                (
                    "snmp_credential_ref",
                    models.CharField(
                        blank=True, help_text="Reference name/id in AWX", max_length=128
                    ),
                ),
                (
                    "tags",
                    models.JSONField(blank=True, default=list, help_text="List of {tag,value}"),
                ),
                (
                    "macros",
                    models.JSONField(blank=True, default=list, help_text="List of {macro,value}"),
                ),
                ("last_synced", models.DateTimeField(blank=True, null=True)),
                ("last_sync_status", models.CharField(blank=True, max_length=16)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="configs",
                        to="netbox_zabbix.zabbixendpoint",
                    ),
                ),
                (
                    "proxy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="netbox_zabbix.proxy",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="monitoringconfig",
            name="hostgroups",
            field=models.ManyToManyField(blank=True, to="netbox_zabbix.hostgroup"),
        ),
        migrations.AddField(
            model_name="monitoringconfig",
            name="templates",
            field=models.ManyToManyField(blank=True, to="netbox_zabbix.template"),
        ),
    ]
