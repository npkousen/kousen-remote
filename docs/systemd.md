# systemd installation

`kousen-remote` can run as a standalone systemd service on the kiosk.

The installer writes these paths:

```text
/opt/kousen-remote
/etc/default/kousen-remote
/etc/systemd/system/kousen-remote.service
```

It installs these Debian packages if missing:

```text
python3-venv
python3-pip
python3-dbus-next
python3-evdev
bluez
```

## Install

From the repository root on the kiosk:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX
```

Install with the Kousen high-function-key mapping:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX --mapping kousen-control
```

Install but do not start immediately:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX --no-start
```

## Inspect

```bash
systemctl status kousen-remote.service
journalctl -u kousen-remote.service -f
cat /etc/default/kousen-remote
```

## Control

```bash
sudo systemctl restart kousen-remote.service
sudo systemctl stop kousen-remote.service
sudo systemctl disable kousen-remote.service
```

## Uninstall

```bash
sudo /opt/kousen-remote/packaging/systemd/uninstall-systemd.sh
```

This stops/disables the service and removes the systemd unit/environment file. It intentionally leaves `/opt/kousen-remote` in place; remove that directory manually if you no longer need the copied project files.
