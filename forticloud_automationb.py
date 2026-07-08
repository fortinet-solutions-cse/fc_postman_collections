#!/usr/bin/env python3
"""
FortiCloud Unified SASE – Provisioning Automation
═══════════════════════════════════════════════════════════════════════════════
Ported from the Postman collection "FortiCloud for Unified SASE" (final version).

Steps:
  01  FortiCloud Org Login       → token         (client_id: organization)
  02a List OU                    → root_org_id   (auto-detected)
  02b Create OU                  → target_org_id
  03  Login IAM                  → tokeniam      (client_id: iam)
  04a Get Common Data            → country_id, phone_prefix, size_id
  04b Create FortiCare Account   → customer_account_id
  05  FortiFlex Login            → tokenflex     (client_id: flexvm)
  06a Create Flex Config         → flexconfigid  (productTypeId: 205 = FortiSASE)
  06b Create Flex Entitlement    → serial(s)

Usage:
  pip install requests pyyaml
  python fortisase_provision.py --config config.yaml

═══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import re
import sys

import requests
import yaml

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BASE_AUTH    = "https://customerapiauth.fortinet.com/api/v1/oauth/token/"
BASE_SUPPORT = "https://support.fortinet.com/ES/api"
HDRS_JSON    = {"Content-Type": "application/json"}

FLEX_PRODUCT_TYPE_ID = 205  # FortiSASE

# Valid service package values for parameter id 49:
#   "FSASESTD" = Standard
#   "FSASEADV" = Advanced
#   "FSASECOM" = Comprehensive
FLEX_PARAMS_REQUIRED = [
    {"id": 48, "key": "flexnumberofusers"},   # Number of users
    {"id": 49, "key": "flexservicepackage"},  # Service package
]
FLEX_PARAMS_OPTIONAL = [
    {"id": 51,  "key": "flexdedicatedip"},
    {"id": 100, "key": "flexdatatransfer"},
    {"id": 101, "key": "flexonrampcloud"},
    {"id": 102, "key": "flexonrampftn"},
    {"id": 104, "key": "flexaddcomputecloud"},
    {"id": 105, "key": "flexaddcomputeftn"},
]

# ─────────────────────────────────────────────────────────────────────────────
# LOAD AND VALIDATE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Runtime state (tokens, computed IDs) — initialized empty
    runtime_keys = [
        "token", "tokeniam", "tokenflex",
        "root_org_id", "target_org_id", "customer_account_id",
        "current_country_id", "current_phone_prefix", "current_size_id",
        "flexconfigid", "_clean_phone",
    ]
    for k in runtime_keys:
        cfg.setdefault(k, "")
    return cfg

def validate_config(cfg: dict):
    required = [
        "apiID", "apipassword",
        "customer_OU_name",
        "firstname", "lastname", "companyname", "companyaddress",
        "companycity", "companypostalcode", "companystate",
        "selected_country_name", "companyPhone", "companysize",
        "flexprogramserialnumber", "flexconfigname",
        "flexnumberofusers", "flexservicepackage",
    ]
    missing = [k for k in required if not str(cfg.get(k, "")).strip()]
    if missing:
        print(f"❌  Missing values in config file: {missing}")
        sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _check(resp: requests.Response, step: str) -> dict:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        print(f"\n❌  [{step}] HTTP {resp.status_code}")
        try:
            print(f"    Detail: {resp.json()}")
        except Exception:
            print(f"    Detail: {resp.text[:600]}")
        sys.exit(1)
    return resp.json()

def _bearer(cfg: dict, token_key: str) -> dict:
    return {"Authorization": f"Bearer {cfg[token_key]}"}

def _is_valid(val) -> bool:
    """Equivalent of isValidValue() from the Postman pre-request script."""
    if val is None:
        return False
    return str(val).strip() not in ("", "0")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 01 – FortiCloud Org Login
# ─────────────────────────────────────────────────────────────────────────────
def step01_org_login(cfg: dict):
    print("\n── Step 01: FortiCloud Org Login ───────────────────────────────────")
    r = requests.post(BASE_AUTH, json={
        "username":   cfg["apiID"],
        "password":   cfg["apipassword"],
        "client_id":  "organization",
        "grant_type": "password",
    }, headers=HDRS_JSON)
    data = _check(r, "Step01")
    cfg["token"] = data["access_token"]
    print("✅  Org token obtained.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 02 – Customer OU Creation
# ─────────────────────────────────────────────────────────────────────────────
def step02a_list_ou(cfg: dict):
    print("\n── Step 02a: List OU (retrieve root) ───────────────────────────────")
    r = requests.post(
        f"{BASE_SUPPORT}/organization/v1/units/list",
        headers={**HDRS_JSON, **_bearer(cfg, "token")},
        json={},
    )
    data = _check(r, "Step02a")

    # --- Recursively extract a list of units from nested dicts ---
    def _extract_list(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ["units", "data", "organizationUnits", "results"]:
                if key in obj:
                    result = _extract_list(obj[key])
                    if result:
                        return result
            return list(obj.values())  # Fallback: flatten dict values
        return []

    units = _extract_list(data)

    if not units:
        print(f"❌  Step02a: empty unit list. Raw: {str(data)[:400]}")
        sys.exit(1)

    # --- Handle list of integers (API returns just IDs) ---
    if units and isinstance(units[0], int):
        units = [{"id": uid} for uid in units]  # Convert to list of dicts

    print(f"    {len(units)} unit(s) returned:")
    for u in units[:5]:
        uid   = u.get("id") or u.get("orgID") or u.get("unitID") or "?"
        name  = u.get("name", "")
        pid   = u.get("parentID", "n/a")
        depth = u.get("depth", "n/a")
        print(f"      id={uid}  parentID={pid}  depth={depth}  name={name}")

    # The root OU is the FIRST item returned
    root    = units[0]
    root_id = root.get("id") or root.get("orgID") or root.get("unitID")

    if not root_id:
        print(f"❌  Step02a: could not extract an ID from the first unit: {root}")
        sys.exit(1)

    cfg["root_org_id"] = int(root_id)
    print(f"✅  root_org_id = {cfg['root_org_id']}  ({root.get('name', '')})")

def step02b_create_ou(cfg: dict):
    print("\n── Step 02b: Create OU ─────────────────────────────────────────────")
    r = requests.post(
        f"{BASE_SUPPORT}/organization/v1/units/create",
        headers={**HDRS_JSON, **_bearer(cfg, "token")},
        json={
            "parentID": cfg["root_org_id"],
            "name":     cfg["customer_OU_name"],
            "desc":     f"OU for {cfg['customer_OU_name']}",
        },
    )
    data = _check(r, "Step02b")

    # --- Recursively extract unit_id from nested dicts/lists ---
    def _find_unit_id(obj):
        if isinstance(obj, dict):
            for key in ["id", "orgID", "unitID", "org_id", "unit_id"]:
                if key in obj:
                    return obj[key]
            for value in obj.values():
                result = _find_unit_id(value)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _find_unit_id(item)
                if result is not None:
                    return result
        return None

    unit_id = _find_unit_id(data)
    if not unit_id:
        print(f"❌  Step02b: Could not extract unit_id. Response: {data}")
        sys.exit(1)

    cfg["target_org_id"] = int(unit_id)
    print(f"✅  target_org_id = {cfg['target_org_id']}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 03 – IAM Login
# ─────────────────────────────────────────────────────────────────────────────
def step03_iam_login(cfg: dict):
    print("\n── Step 03: IAM Login ──────────────────────────────────────────────")
    r = requests.post(BASE_AUTH, json={
        "username":   cfg["apiID"],
        "password":   cfg["apipassword"],
        "client_id":  "iam",          # Postman collection: client_id = "iam"
        "grant_type": "password",
    }, headers=HDRS_JSON)
    data = _check(r, "Step03")
    cfg["tokeniam"] = data["access_token"]
    print("✅  IAM token obtained.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 04 – FortiCare Account Creation
# ─────────────────────────────────────────────────────────────────────────────
def step04a_get_common_data(cfg: dict):
    print("\n── Step 04a: Get Data for Account Creation ─────────────────────────")
    r = requests.post(
        f"{BASE_SUPPORT}/iam/v1/accounts/getcommondata",
        headers={**HDRS_JSON, **_bearer(cfg, "tokeniam")},
        json={},
    )
    data = _check(r, "Step04a")

    countries = data.get("organizationUnits", {}).get("countries", [])
    sizes     = data.get("organizationUnits", {}).get("sizes", [])

    # ── Country resolution ───────────────────────────────────────────────────
    user_code = cfg["selected_country_name"].strip().upper()
    matched_country = next(
        (c for c in countries if (c.get("code") or "").upper() == user_code), None
    )
    if matched_country is None:
        print(f"⚠️  Country code '{user_code}' not found, using first in list.")
        matched_country = countries[0] if countries else {}

    cfg["current_country_id"] = matched_country.get("id", "")
    phone_codes = matched_country.get("phone_codes") or []
    cfg["current_phone_prefix"] = phone_codes[0] if phone_codes else ""
    print(
        f"✅  Country: {matched_country.get('code')} → "
        f"id={cfg['current_country_id']}, prefix={cfg['current_phone_prefix']}"
    )

    # ── Company size resolution ──────────────────────────────────────────────
    user_size       = str(cfg["companysize"]).strip()
    user_size_clean = re.sub(r"\s+", "", user_size)

    matched_size = next(
        (s for s in sizes if re.sub(r"\s+", "", s.get("name", "")) == user_size_clean),
        None,
    )

    if matched_size is None:
        # Fallback: "1-24" (Postman default) then first in list
        default_size = "1-24"
        fallback = next(
            (s for s in sizes if re.sub(r"\s+", "", s.get("name", "")) == default_size),
            sizes[0] if sizes else {},
        )
        print(f"⚠️  Size '{user_size}' not found. Available: {[s.get('name') for s in sizes[:8]]} …")
        print(f"    Fallback → '{fallback.get('name')}'")
        matched_size = fallback

    cfg["current_size_id"] = matched_size.get("id", "")
    print(f"✅  Size: '{matched_size.get('name')}' → id={cfg['current_size_id']}")

    # ── Phone number sanitization ────────────────────────────────────────────
    clean = re.sub(r"^\+", "", cfg["companyPhone"].strip())
    cfg["_clean_phone"] = re.sub(r"\s+", "", clean)

def step04b_create_account(cfg: dict):
    print("\n── Step 04b: Create FortiCare Account ──────────────────────────────")
    prefix = cfg.get("current_phone_prefix", "")
    phone  = f"{prefix} {cfg['_clean_phone']}".strip()
    r = requests.post(
        f"{BASE_SUPPORT}/iam/v1/accounts/create",
        headers={**HDRS_JSON, **_bearer(cfg, "tokeniam")},
        json={
            "parentId":   cfg["target_org_id"],  # <-- FIXED: Use target_org_id
            "firstName":  cfg["firstname"],
            "lastName":   cfg["lastname"],
            "company":    cfg["companyname"],
            "address":    cfg["companyaddress"],
            "city":       cfg["companycity"],
            "postalCode": cfg["companypostalcode"],
            "state":      cfg["companystate"],
            "countryId":  cfg["current_country_id"],
            "phone":      phone,
            "industryId": 58,
            "sizeId":     cfg["current_size_id"],
        },
    )
    data = _check(r, "Step04b")

    # --- Recursively extract account_id from nested dicts/lists ---
    def _find_id(obj):
        if isinstance(obj, dict):
            for key in ["id", "accountId", "account_id", "accountID"]:
                if key in obj:
                    return obj[key]
            for value in obj.values():
                result = _find_id(value)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _find_id(item)
                if result is not None:
                    return result
        return None

    account_id = _find_id(data)
    if not account_id:
        print(f"❌  Step04b: Could not extract account_id. Response: {data}")
        sys.exit(1)

    cfg["customer_account_id"] = str(account_id)
    print(f"✅  customer_account_id = {cfg['customer_account_id']}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 05 – FortiFlex Login
# ─────────────────────────────────────────────────────────────────────────────
def step05_flex_login(cfg: dict):
    print("\n── Step 05: FortiFlex Login ────────────────────────────────────────")
    r = requests.post(BASE_AUTH, json={
        "username":   cfg["apiID"],
        "password":   cfg["apipassword"],
        "client_id":  "flexvm",
        "grant_type": "password",
    }, headers=HDRS_JSON)
    data = _check(r, "Step05")
    cfg["tokenflex"] = data["access_token"]
    print("✅  Flex token obtained.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 06a – Create Flex Config (dynamic payload)
# ─────────────────────────────────────────────────────────────────────────────
def step06a_create_flex_config(cfg: dict):
    print("\n── Step 06a: Create Flex Config ────────────────────────────────────")

    # Required parameters
    parameters = [
        {"id": p["id"], "value": str(cfg[p["key"]]).strip()}
        for p in FLEX_PARAMS_REQUIRED
    ]
    # Optional parameters (skipped if empty or "0")
    for p in FLEX_PARAMS_OPTIONAL:
        val = cfg.get(p["key"], "")
        if _is_valid(val):
            parameters.append({"id": p["id"], "value": str(val).strip()})

    payload = {
        "programSerialNumber": cfg["flexprogramserialnumber"],
        "accountId":           int(cfg["customer_account_id"]),
        "name":                cfg["flexconfigname"],
        "productTypeId":       FLEX_PRODUCT_TYPE_ID,
        "parameters":          parameters,
    }
    print(f"    Flex parameters: {parameters}")

    r = requests.post(
        f"{BASE_SUPPORT}/fortiflex/v2/configs/create",
        headers={**HDRS_JSON, **_bearer(cfg, "tokenflex")},
        json=payload,
    )
    data = _check(r, "Step06a")

    # Extract configId: data.configs[0].id or data.configs.id (from Postman test script)
    configs = data.get("configs")
    config_id = None
    if isinstance(configs, list) and configs:
        config_id = configs[0].get("id")
    elif isinstance(configs, dict):
        config_id = configs.get("id")
    if not config_id:
        config_id = data.get("id") or data.get("configId") or ""

    cfg["flexconfigid"] = str(config_id)
    print(f"✅  flexconfigid = {cfg['flexconfigid']}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 06b – Create Flex Entitlement
# ─────────────────────────────────────────────────────────────────────────────
def step06b_create_entitlement(cfg: dict):
    print("\n── Step 06b: Create Flex Entitlement ───────────────────────────────")
    r = requests.post(
        f"{BASE_SUPPORT}/fortiflex/v2/entitlements/cloud/create",
        headers={**HDRS_JSON, **_bearer(cfg, "tokenflex")},
        json={
            "programSerialNumber": cfg["flexprogramserialnumber"],
            "accountId":           cfg["customer_account_id"],
            "configId":            cfg["flexconfigid"],
            "count":               1,
            "description":         "Fortisase Configuration",
        },
    )
    data = _check(r, "Step06b")

    serials = []
    if isinstance(data.get("entitlements"), list):
        serials = [e.get("serialNumber", "") for e in data["entitlements"]]
    elif data.get("serialNumber"):
        serials = [data["serialNumber"]]

    print(f"✅  Entitlement created. Serial(s): {serials or '(see raw response)'}")
    return data

# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(cfg: dict):
    print("\n" + "═" * 65)
    print("  ✅  All steps completed successfully.")
    print("═" * 65)
    print(f"""
  root_org_id         = {cfg['root_org_id']}
  target_org_id       = {cfg['target_org_id']}
  customer_account_id = {cfg['customer_account_id']}
  country_id          = {cfg['current_country_id']}
  size_id             = {cfg['current_size_id']}
  flexconfigid        = {cfg['flexconfigid']}
""")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="FortiCloud Unified SASE – Provisioning Automation"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)"
    )
    args = parser.parse_args()

    print("═" * 65)
    print("  FortiCloud Unified SASE – Provisioning Automation")
    print(f"  Config: {args.config}")
    print("═" * 65)

    cfg = load_config(args.config)
    validate_config(cfg)

    step01_org_login(cfg)
    step02a_list_ou(cfg)
    step02b_create_ou(cfg)
    step03_iam_login(cfg)
    step04a_get_common_data(cfg)
    step04b_create_account(cfg)
    step05_flex_login(cfg)
    step06a_create_flex_config(cfg)
    step06b_create_entitlement(cfg)

    print_summary(cfg)

if __name__ == "__main__":
    main()

