#!/usr/bin/env python3
# NetBox → AWX dynamic inventory (filters badge=caution by default)
import os, sys, json, ssl, urllib.request, urllib.parse

def env_bool(name, default=False):
    v = str(os.getenv(name, str(default))).strip().lower()
    return v in ("1", "true", "yes", "y")

def safe(name: str) -> str:
    if name is None:
        return "unknown"
    out = []
    for ch in str(name):
        out.append(ch if ch.isalnum() or ch in ("_", "-") else "_")
    return "".join(out).strip("_") or "unknown"

def main():
    base = os.getenv("NETBOX_URL", "").rstrip("/")
    token = os.getenv("NETBOX_TOKEN", "")
    badge = os.getenv("NETBOX_BADGE", "caution").strip().lower()  # ok|caution|fail
    timeout = float(os.getenv("NETBOX_TIMEOUT", "15"))
    verify = env_bool("NETBOX_VERIFY", True)

    if not base or not token:
        print("{}", end="")
        print("NETBOX_URL and NETBOX_TOKEN are required", file=sys.stderr)
        sys.exit(0)

    url = f"{base}/api/plugins/netbox-zabbix/awx-inventory/"
    params = {}
    if badge in ("ok","caution","fail"):
        params["badge"] = badge
    if params:
        url += "?" + urllib.parse.urlencode(params)

    ctx = None
    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "User-Agent": "nb-zbx-awx-inventory/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("{}", end="")
        print(f"ERROR fetching inventory: {e}", file=sys.stderr)
        sys.exit(0)

    hosts = data.get("hosts", [])

    # Build dynamic inventory
    inv = {"_meta": {"hostvars": {}}, "all": {"hosts": []}}

    groups = {}  # name -> set(hostnames)

    for h in hosts:
        name = h.get("name")  # Zabbix host name (unique)
        if not name:
            # skip nameless
            continue

        # Extract fields
        tags = h.get("tags", {}) or {}
        env = tags.get("environment")
        os_slug = tags.get("os")
        site = tags.get("site")

        iface = h.get("interface", {}) or {}
        primary_tmpl = h.get("primary_template", {}) or {}
        extra_tmps = h.get("extra_templates", []) or []

        hostvars = {
            # core
            "zbx_host_name":            name,
            "zbx_visible_name":         h.get("visible_name"),
            "zbx_status":               h.get("zabbix_status"),    # "Not Synced"/"Synced"
            "badge":                    h.get("badge", ""),        # ok|caution|fail
            "is_device":                (h.get("type") == "device"),

            # templates
            "zbx_primary_template_id":  primary_tmpl.get("id"),
            "zbx_primary_template_name":primary_tmpl.get("name"),
            "zbx_extra_template_ids":   [t.get("id") for t in extra_tmps if t and t.get("id")],
            "zbx_extra_template_names": [t.get("name") for t in extra_tmps if t and t.get("name")],

            # interface
            "zbx_interface_type_id":    iface.get("type_id"),
            "zbx_interface_type_label": iface.get("type_label"),
            "zbx_interface_ip":         iface.get("ip"),

            # placement
            "zbx_proxy_id":             h.get("proxy_id"),
            "zbx_group_id":             h.get("group_id"),

            # tags
            "tag_environment":          env,
            "tag_os":                   os_slug,
            "tag_site":                 site,
            "tag_device":               tags.get("device"),
            "tag_nb_status":            tags.get("nb_status"),

            # convenience
            "enabled":                  True,  # fits AWX "Enabled Variable" if you want to use it
        }

        inv["_meta"]["hostvars"][name] = hostvars
        inv["all"]["hosts"].append(name)

        # Handy groups
        for gname in [
            f"env_{safe(env)}" if env else None,
            f"os_{safe(os_slug)}" if os_slug else None,
            f"site_{safe(site)}" if site else None,
            f"badge_{safe(h.get('badge', ''))}",
        ]:
            if not gname:
                continue
            groups.setdefault(gname, set()).add(name)

    # Convert group sets to lists
    for g, members in groups.items():
        inv[g] = {"hosts": sorted(members)}

    print(json.dumps(inv, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
