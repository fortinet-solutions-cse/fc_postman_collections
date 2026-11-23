# FortiCloud Unified SASE Automation

This repository provides tools to automate the provisioning process for FortiCloud Unified SASE environments. It includes both a Postman collection for manual testing/debugging and a Python script for automated, non-interactive deployment.

## Features

The automation covers the following workflow:
1.  **Authentication**: OAuth token generation for Organization, IAM, and Flex services.
2.  **OU Management**: Automatically listing root OUs and creating new Organizational Units (OU) for customers.
3.  **Account Provisioning**: Retrieving necessary registration data (country codes, company size IDs) and creating new FortiCare accounts.
4.  **FortiFlex License Configuration**: Automating the creation of FortiSASE (`productTypeId: 205`) configurations and entitlements via the FortiFlex API.
5.  **IAM Profile & User (optional, new in `forticloud_automationC.py`)**: Creating a read-only FortiSASE IAM permission profile and an IAM user attached to the customer OU, for co-management access.

---

## 1. Postman Collection

The `FortiCloud for Unifed SASE.postman_collection.json` file contains the complete API sequence.

### Prerequisites
* Import both the collection (`.json`) and the environment (`.postman_environment.json`) into Postman.
* Update the variables in the Postman environment with your specific API credentials (`apiID`, `apipassword`) and customer details.

### Workflow
* **Step 01**: Org Login
* **Step 02**: OU Creation
* **Step 03**: IAM Login
* **Step 04**: FortiCare Account Creation
* **Step 05**: FortiFlex Login
* **Step 06**: FortiSASE License/Entitlement Creation
* **Step 07** *(optional, Python script only)*: IAM profile and user creation. It is ported from the Postman collection "test permission" and is not part of the collection above.

---

## 2. Python Automation Script

For scalable or programmatic deployment, use `forticloud_automationb.py`.

> **New:** `forticloud_automationC.py` is version B plus the optional IAM step (step 07). Steps 01-06 are unchanged. Use version C if you also want the IAM profile and user created automatically (see [IAM Profile & User](#iam-profile--user-step-07-optional) below).

### Prerequisites
* Python 3.x
* Required libraries: `requests`, `pyyaml`
    ```bash
    pip install requests pyyaml
    ```

### Usage
1.  **Configure**: Edit the `config.yaml` file with your credentials and customer-specific provisioning details.
2.  **Run**: Execute the script from the command line:
    ```bash
    python forticloud_automationb.py --config config.yaml
    ```
    With the IAM step (version C):
    ```bash
    python forticloud_automationC.py --config config.yaml
    ```

### Configuration (`config.yaml`)
Ensure all mandatory fields (API credentials, customer names, address, and SASE license parameters) are populated. Optional FortiSASE parameters (like dedicated IP, data transfer, etc.) can be set to "0" or left empty to skip them.

#### IAM settings (version C, optional)
The following keys control step 07. They are all optional as a group: if any required one is empty, step 07 is skipped and steps 01-06 run as usual.

| Key | Required for step 07 | Description |
| :--- | :--- | :--- |
| `permission_profile_name` | Yes | Name of the IAM profile to create, e.g. `Comanagement-RO-SASE-Customer88`. |
| `permission_profile_description` | No | Profile description. Defaults to `Comanagement read-only SASE profile`. |
| `iam_user_name` | Yes | IAM user name, e.g. `customer88-ro`. |
| `iam_email` | Yes | Email address of the IAM user. |
| `iam_fullname` | Yes | Full name of the IAM user. |
| `iam_phone` | Yes | Phone number of the IAM user. Keep the quotes, e.g. `"+33 6 12 34 56 78"`. |
| `org_base_url` | No | Base URL of the IAM API used for `accounts/list`. Leave empty to use `https://support.fortinet.com/ES/api/iam/v1`. |

`root_org_id` and `target_org_id` do not need to be set: the script finds or creates them in steps 02a / 02b.

### IAM Profile & User (step 07, optional)

Step 07 is ported from the Postman collection "test permission" and reuses the IAM token (step 03), the root OU ID (step 02a) and the new customer OU ID (step 02b).

| Sub-step | Action | Description |
| :--- | :--- | :--- |
| **07a** | Get root account | Calls `accounts/list` with the root OU as parent and picks the root `accountId`. |
| **07b** | Create IAM profile | Creates a read-only profile (`type: Organization`) on the FortiSASE portal (`portalId: 15`). |
| **07c** | Create IAM user | Creates the IAM user with that profile, attached to the customer OU (`nodeId = target_org_id`). |

**Permissions granted** (all read-only, `action: 0`): `dashboards`, `endpoint_mgmt`, `infrastructure`, `logging`, `monitoring`, `network`, `policy`, `security`, `system`, `user_auth`.

**Behaviour**
* **Skipped** if the IAM settings are incomplete. Steps 01-06 still run and the summary shows `iam_status = skipped`.
* **Non-fatal**: if an IAM call fails, the error is printed and the script finishes. The main provisioning (steps 01-06) is already done at that point.
* **Exit code**: the script exits with code `2` when step 07 failed, so a pipeline can detect it. The summary shows `iam_status = failed`.
* On success the summary shows `iam_status = created` and the `iam_root_account_id` used.

---

## Workflow Logic

The scripts perform the following steps sequentially:
| Step | Action | Description |
| :--- | :--- | :--- |
| **01** | Org Login | Authenticates to FortiCloud Organization API. |
| **02** | OU Setup | Detects root OU and creates a customer-specific unit. |
| **03** | IAM Login | Authenticates to the IAM API for account management. |
| **04** | Account Creation | Maps country/size input to API IDs and registers the account. |
| **05** | Flex Login | Authenticates to the FortiFlex service. |
| **06** | Flex Provisioning | Creates the SASE config and assigns the entitlement. |
| **07** | IAM Profile & User *(optional, version C)* | Creates a read-only SASE IAM profile and an IAM user on the customer OU. Skipped if the IAM config is incomplete. |

---

## Keeping credentials out of git

`config.yaml` contains your FortiCloud API credentials. Commit only a placeholder `config.example.yaml` and keep the real `config.yaml` out of the repository with the provided `.gitignore` (it also ignores Postman exports, logs and saved API responses, which can contain credentials, tokens or account IDs). If a real `config.yaml` was ever committed, run `git rm --cached config.yaml` and rotate the API password.

---
*Note: Ensure your FortiCloud org API user has the necessary permissions to perform these administrative actions across the Organization and FortiFlex programs. Step 07 additionally needs permission to create IAM profiles and users.*
