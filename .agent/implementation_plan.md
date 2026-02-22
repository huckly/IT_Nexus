# Implementation Plan - Fix LibreNMS Sync for New Devices

## Problem
New devices added to LibreNMS are not appearing in NetBox.
1. `webhook_receiver.py` triggers `sync_librenms_to_netbox.py` with the `--device` argument.
2. `sync_librenms_to_netbox.py` currently ignores all command-line arguments and fetches all devices.
3. `sync_librenms_to_netbox.py` defaults to `AUTO_CREATE_NEW=False`, skipping creation of new devices unless configured otherwise.

## Proposed Changes

### `scripts/sync_librenms_to_netbox.py`

- Import `argparse`.
- Add argument parser for `--device` (and optional `--debug`).
- Update `main()` to filter the `librenms_devices` list if a specific device is requested.
- **Critical Logic Change**: If a specific device is requested via `--device`, force `auto_create = True` for that run, ensuring the new device is created in NetBox.

## Verification Plan

### Manual Verification
1.  **Simulate Webhook Trigger**: Run the sync script manually with the `--device` flag against a known (or mock) new device.
    ```bash
    python3 scripts/sync_librenms_to_netbox.py --device <NEW_DEVICE_HOSTNAME> --dry-run
    ```
    *Note: Since I cannot access the live NetBox/LibreNMS environment directly, I will rely on the script's output (dry-run mode).*
2.  **Verify Logic**: Check logs to see if the script:
    - Filters for the specific device.
    - Sets `auto_create` to True.
    - Attempts to create the device (in dry-run).

### Automated Tests
- None existing for this specific integration. Will rely on manual invocation and log review.
