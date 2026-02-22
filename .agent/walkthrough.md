# LibreNMS -> NetBox Sync Fix Walkthrough

## 1. Issue Description
New devices added to LibreNMS were not appearing in NetBox despite the Webhook being triggered.
- **Cause**: The `webhook_receiver.py` passed a `--device` argument, but `sync_librenms_to_netbox.py` did not parse it. Additionally, the default `AUTO_CREATE_NEW=False` setting prevented new devices from being created during these partial syncs.

## 2. Changes Made
### `scripts/sync_librenms_to_netbox.py`
- **Feature**: Added `argparse` to handle `--device <hostname>` and `--dry-run`.
- **Logic**: 
    - When `--device` is specified, `auto_create` is forcibly set to `True`.
    - The device list is filtered to match only the target hostname (partial match on `sysName` or `hostname`).
- **Safety**: Dry-run mode (`--dry-run`) is supported via CLI argument.

### `scripts/webhook_receiver.py`
- No changes required (it was already sending the correct argument).

## 3. Deployment & Verification
Deploy the updated script to the NetBox server.

```bash
# 0. Initial Setup (If directory does not exist)
if [ ! -d "/opt/netbox/scripts/it_nexus" ]; then
    sudo git clone https://github.com/huckly/IT_Nexus.git /opt/netbox/scripts/it_nexus
    sudo chown -R netbox:netbox /opt/netbox/scripts/it_nexus
fi

# 1. Pull changes
cd /opt/netbox/scripts/it_nexus
git pull

# 2. Check permissions
chmod +x scripts/sync_librenms_to_netbox.py

# 3. Test manually (Optional)
/opt/netbox/scripts/venv/bin/python3 scripts/sync_librenms_to_netbox.py --device <NEW_DEVICE_NAME> --dry-run
```

## 4. Verification Check
Check `webhook_receiver.log` after adding a new device to LibreNMS:
```bash
tail -f /var/log/it_nexus/webhook_receiver.log
```
You should see:
> `🚀 Triggering sync for <device>...`
> `✅ Sync successful for <device>`

And in `it_nexus/sync_librenms.log`:
> `🎯 指定同步設備: <device> (強制 Auto-Create)`
