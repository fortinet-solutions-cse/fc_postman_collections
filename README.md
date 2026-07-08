
# FortiCloud Unified SASE Automation

This repository provides tools to automate the provisioning process for FortiCloud Unified SASE environments. It includes both a Postman collection for manual testing/debugging and a Python script for automated, non-interactive deployment.

## Features

The automation covers the following workflow:
1.  **Authentication**: OAuth token generation for Organization, IAM, and Flex services.
2.  **OU Management**: Automatically listing root OUs and creating new Organizational Units (OU) for customers.
3.  **Account Provisioning**: Retrieving necessary registration data (country codes, company size IDs) and creating new FortiCare accounts.
4.  **FortiFlex License Configuration**: Automating the creation of FortiSASE (`productTypeId: 205`) configurations and entitlements via the FortiFlex API.

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

---

## 2. Python Automation Script

For scalable or programmatic deployment, use `forticloud_automationb.py`.

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

### Configuration (`config.yaml`)
Ensure all mandatory fields (API credentials, customer names, address, and SASE license parameters) are populated. Optional FortiSASE parameters (like dedicated IP, data transfer, etc.) can be set to "0" or left empty to skip them.

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

---
*Note: Ensure your FortiCloud org API user has the necessary permissions to perform these administrative actions across the Organization and FortiFlex programs.*
