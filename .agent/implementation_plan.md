# IT Nexus - NetBox Installation Plan

## Goal Description
Deploy **NetBox** (Source of Truth) on a freshly provisioned Ubuntu 24.04 Server.
We will use **NetBox Docker** Community Edition for ease of maintenance and upgrades.

## User Review Required
> [!IMPORTANT]
> **New Host Info**: Please provide the IP address and SSH credentials for the new Ubuntu 24.04 VM once it is provisioned.
> **Existing Systems**:
> - LibreNMS: `198.51.100.1` (Assumed from history)
> - GLPI: (Need IP/URL)

## Proposed Changes

### 1. Host Preparation (New VM)
User will provision a standard Ubuntu 24.04 LTS server.
We will provide a bootstrap script to:
- Update OS.
- Install Docker & Docker Compose.
- Install Git & Utilities.

#### [NEW] [install_netbox_docker.sh](file:///c:/Users/huckly.chiu/Documents/AntiGravity/IT_Nexus/scripts/install_netbox_docker.sh)
- Automated installation script.
- Clones `netbox-docker`.
- Configures `docker-compose.override.yml` for custom ports (if needed) or accepted defaults.
- Bringing up the stack.

### 2. Integration Config (Post-Install)
Once NetBox is up:
- Create Superuser.
- Generate API Token.
- Configure LibreNMS (on `198.51.100.1`) to push data to this new NetBox instance.

## Verification Plan

### Manual Verification
1. **Access UI**: Open `http://<NEW_VM_IP>:8000`.
2. **Login**: Log in with created superuser.
3. **API Test**: `curl` the API endpoint.
