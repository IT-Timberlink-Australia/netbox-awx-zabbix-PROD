from django.db import migrations

RENAME_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = '{table}' AND column_name = '_custom_field_data'
  ) THEN
    EXECUTE 'ALTER TABLE {table} RENAME COLUMN _custom_field_data TO custom_field_data';
  END IF;
END$$;
"""

REVERT_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = '{table}' AND column_name = 'custom_field_data'
  ) THEN
    EXECUTE 'ALTER TABLE {table} RENAME COLUMN custom_field_data TO _custom_field_data';
  END IF;
END$$;
"""

TABLES = [
    "netbox_zabbix_zabbixendpoint",
    "netbox_zabbix_hostgroup",
    "netbox_zabbix_template",
    "netbox_zabbix_proxy",
    "netbox_zabbix_monitoringconfig",
]


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_zabbix", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=";\n".join(RENAME_SQL.format(table=t) for t in TABLES),
            reverse_sql=";\n".join(REVERT_SQL.format(table=t) for t in TABLES),
        ),
    ]
