# NetBox ⇄ Zabbix Template ID Sync

This repository contains an Ansible playbook that keeps a NetBox **Custom Object Type** (COT) named `zabbix-template-list` in sync with Zabbix template IDs.

> **File:** `nb_co_zabbix_templates_sync.yml`

---

## Quick Start (AWX)

1. **Add the Project**
   - SCM URL: your GitHub repo
   - Branch: `main` (or as used)
   - Ensure the playbook filename has **no leading/trailing spaces** and lives at the repo root (or adjust the path).

2. **Credentials / Environment (in the Job Template)**
   Set these **environment variables** (via AWX credential or Template → Variables → Environment):
   ```text
   NETBOX_API=<https://netbox.example.com>
   NETBOX_TOKEN=<netbox_api_token>
   ZABBIX_API_URL=<https://zabbix.example.com/zabbix>        # or .../api_jsonrpc.php
   ZABBIX_API_TOKEN=<zabbix_api_token>
   ```

3. **Execution Environment**
   - Use your standard EE for now.
   - TLS verification is **disabled in the playbook** by default to unblock first runs. See **Hardening TLS** to enable proper cert validation later.

4. **Job Template**
   - Playbook: `nb_co_zabbix_templates_sync.yml`
   - Inventory: `localhost`
   - **Connection:** handled by the play (`connection: local`), no SSH needed.
   - Optional Extra Vars:
     ```yaml
     zbx_filter_key: name   # or 'host' if NetBox stores Zabbix technical keys
     page_size: 200
     # apply_changes: true   # uncomment if you later add a dry-run switch
     ```

5. **Launch**
   - First run should show `updated > 0` as it fills missing IDs.
   - Subsequent runs should be idempotent (`updated = 0` unless new names appear).

---

## What It Does

**Goal:** Fill `template_id` in NetBox COT `zabbix-template-list` by looking up each `template_name` in Zabbix.

**Flow:**
1. Fetch rows from NetBox API `/api/plugins/custom-objects/zabbix-template-list/`.
2. Collect all `template_name` values.
3. Query Zabbix (`template.get`) for those names (or hosts) using a token.
4. Build a map (`name → templateid` and `host → templateid`), prefer the one that fully covers your NetBox names.
5. PATCH `template_id` **only where it is empty**.
6. Print a summary and write helper files:
   - `zbx_template_ids_from_nb.json` (name→id map)
   - `zbx_template_ids_from_nb.csv`  (name, existing_id, new_id)

**Safety:** Rows with a non-empty `template_id` are **skipped** (no overwrites).

---

## Inputs and URLs

- **NetBox**
  - `NETBOX_API` — base URL, e.g., `https://netbox.example.com`
  - API path (built in play): `{{ NETBOX_API }}/api/plugins/custom-objects/zabbix-template-list/`

- **Zabbix**
  - `ZABBIX_API_URL` — base `https://…/zabbix` *or* the full `…/api_jsonrpc.php`
    - The play normalizes this so the final endpoint is **exactly** `…/api_jsonrpc.php` (no duplicates).
  - `ZABBIX_API_TOKEN` — API token with `template.get` access

- **Fields in COT**
  - `template_name` (string) — the name (or technical key) to match in Zabbix
  - `template_id`   (string/int) — Zabbix `templateid` (filled by the play)

---

## Configuration Options

- `zbx_filter_key`
  - `name` (default): if `template_name` matches Zabbix **display** names
  - `host`: if `template_name` holds Zabbix **technical** keys
- `page_size`: 200 (single-page fetch). See **Pagination** to scale beyond 200.
- `apply_changes`: (optional) add a boolean to support dry-run behavior.

---

## Hardening TLS (recommended)

The tested playbook uses `validate_certs: false` to unblock initial runs. Proper fix: bake your issuing CA(s) into the **Execution Environment** trust store and then set `validate_certs: true`.

### Extract CA(s) from your PFX (without private key)
```bash
openssl pkcs12 -in WildCardCert2026.pfx -cacerts -nokeys -out ca-chain.pem
# Optionally split into individual PEMs:
awk 'BEGIN{n=0}/-----BEGIN CERTIFICATE-----/{n++}{print > ("ca-"n".crt")}' ca-chain.pem
```

### Add CA(s) to the EE

**UBI/RHEL-based EE**
```dockerfile
FROM quay.io/ansible/awx-ee:latest
COPY ca/*.crt /etc/pki/ca-trust/source/anchors/
RUN update-ca-trust extract
# Optional, Requests will use system bundle anyway:
ENV REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
```

**Debian/Ubuntu-based EE**
```dockerfile
FROM your/base-ee:tag
COPY ca/*.crt /usr/local/share/ca-certificates/
RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

Build, push to your registry, and select this EE in the AWX Job Template. Then flip all `validate_certs: true` in the play.

---

## Pagination (when you have >200 rows)

Add a count call and loop over `offset`s, then flatten results:

```yaml
# Count
- uri:
    url: "{{ nb_collection_url }}?limit=1"
    method: GET
    headers: { Authorization: "Token {{ netbox_token }}", Accept: "application/json" }
    return_content: true
    validate_certs: false
  register: nb_count

- set_fact:
    _nb_count: "{{ nb_count.json.count | default(nb_count.json.results|length|default(0)) }}"
    _offsets: "{{ range(0, (_nb_count|int), (page_size|int)) | list }}"

# Fetch all pages
- uri:
    url: "{{ nb_collection_url }}?limit={{ page_size }}&offset={{ item }}"
    method: GET
    headers: { Authorization: "Token {{ netbox_token }}", Accept: "application/json" }
    return_content: true
    validate_certs: false
  loop: "{{ _offsets }}"
  register: nb_pages

- set_fact:
    _nb_rows: "{{ nb_pages.results | map(attribute='json') | map(attribute='results', default=[]) | list | flatten }}"
```

---

## Troubleshooting

- **Playbook not found (AWX UI)**  
  The file wasn’t in the synced tree or had a funky filename (e.g., leading space). Fix the path/name and resync.

- **NetBox returned HTML / login page**  
  You hit the UI path. Use the **API**: `/api/plugins/custom-objects/...` and ensure you pass the token.

- **Double `/api_jsonrpc.php/api_jsonrpc.php`**  
  Caused by an already-suffixed `ZABBIX_API_URL`. The play de-dupes, but keep your env clean (base URL *or* full endpoint, not both).

- **TLS `CERTIFICATE_VERIFY_FAILED`**  
  Install your org CA(s) into the EE and enable `validate_certs: true` (see **Hardening TLS**).

- **Ansible is trying SSH to 127.0.0.1**  
  The play sets `connection: local`. Keep it that way; no SSH needed.

- **Undefined vars during `set_fact`**  
  Facts must be set in **separate tasks** before use. The final play splits them correctly.

- **Missing templates in Zabbix**  
  The summary prints `missing_in_zabbix`. Fix the source `template_name` or add the template in Zabbix.

---

## Output Artifacts

- `zbx_template_ids_from_nb.json` — name → templateid map
- `zbx_template_ids_from_nb.csv` — row-by-row view (`name, existing_id, new_id`)
- AWX job summary prints: `total_rows`, `updated`, `skipped_non_empty`, `missing_in_zabbix`

---

## Idempotency

- Rows that already have a non-empty `template_id` are **skipped**.
- Re-running will only affect newly added names or previously empty rows.

---

## Operational Tips

- If NetBox stores Zabbix **technical keys**, set `zbx_filter_key: host`.
- Keep names consistent; trim accidental whitespace and case drift.
- Schedule this in AWX (daily) so new rows get filled automatically.
- Once TLS trust is fixed in your EE, **enable cert verification** and keep it that way.

---

**Contact / Maintenance**  
Keep the playbook thin and deterministic. If you extend it (e.g., pagination, dry-run switch), update this README accordingly.
