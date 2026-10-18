# BazziteLGTV

Automatically power your LG TV on/off when using it as a PC monitor on **Bazzite** (or any SELinux-enforcing Fedora Atomic distro). Handles boot, shutdown, and suspend/resume.

Existing solutions like [LG_Buddy](https://github.com/jesseposner/LG_Buddy) and [lgpowercontrol](https://github.com/nicholasgasior/lgpowercontrol) don't work on Bazzite because systemd runs in the `init_t` SELinux domain and cannot execute scripts installed to `~/.local/` (`user_home_t`). This project fixes that correctly — no custom SELinux policy modules, no hacks.

**Zero external dependencies.** Everything is implemented in Python's standard library (`asyncio`, `ssl`, `socket`). No pip packages required.

---

## Requirements

### System

- Bazzite / Fedora Atomic (or any SELinux-enforcing distro)
- LG WebOS TV connected via **wired LAN** or **WiFi** on your local network e.g. (192.168.1.x)
- `python3` (already present on all Fedora-based systems)
- `policycoreutils-python-utils` — for `semanage` (only needed if SELinux is Enforcing)

If `semanage` is missing:
```bash
sudo rpm-ostree install policycoreutils-python-utils
# reboot after
```

### TV Settings

These must be configured on the TV before install:

- **Quick Start must be disabled** — Quick Start prevents Wake-on-LAN magic packets from working
- **Settings → General → External Devices → TV On with Mobile** must be **enabled** — this keeps the network chip powered in standby so the TV can receive WoL packets

---

## Install

```bash
git clone https://github.com/yourusername/BazziteLGTV
cd BazziteLGTV
./install.sh
```

The installer will:

1. Check for `python3` and (if SELinux is Enforcing) `semanage`
2. Ask for your TV's IP address
3. Ask which HDMI input to switch to after power-on (default `HDMI3`, or `none`)
4. Copy scripts to `/etc/lgtvcontrol/`
5. Apply `bin_t` SELinux contexts so systemd can execute them
6. Pair with the TV — a prompt appears on screen, press OK with your remote
7. Detect and save the TV's MAC address for Wake-on-LAN or Wifi
8. Install and enable the systemd services
9. Offer to run a screen test (off 10s → on)

You can also pass the HDMI input on the command line to skip the prompt:

```bash
./install.sh --input HDMI2        # use HDMI2 instead of the default HDMI3
./install.sh --input none         # install without any input switching
```

---

## Test

Run at any time after install:

```bash
./install.sh --test
```

Turns the screen off for 10 seconds then back on.

---

## How it works

### The SELinux problem

systemd launches services in the `init_t` SELinux domain. Files in your home directory have `user_home_t` context. SELinux blocks `init_t` from executing `user_home_t` files — this is why running scripts from `~/.local/` silently fails.

### The fix

Scripts are installed to `/etc/lgtvcontrol/` and labelled `bin_t` via `semanage fcontext`. This is the standard Fedora approach to making custom paths executable by systemd. It survives reboots and SELinux filesystem relabels.

```
/usr/local/bin/
  lgtv             ← CLI shortcut in $PATH (lgtv on|off|toggle|status|gui)

/etc/lgtvcontrol/
  lgtv.py          ← WebSocket client (stdlib only)
  lgtv-gui.py      ← Couch-friendly GUI control panel
  lgtv-tray.py     ← System tray indicator & tooltip for Desktop Mode
  lgtv-on.sh       ← calls: python3 /etc/lgtvcontrol/lgtv.py on --auto
  lgtv-off.sh      ← calls: python3 /etc/lgtvcontrol/lgtv.py off --auto
  disabled         ← state marker when TV auto-sync is deactivated
  tv_ip            ← TV IP address (written by installer)
  tv_input         ← HDMI input to switch to after power-on (optional)
  tv_mac           ← TV MAC address (written by installer, used for WoL)
  client.key       ← auth key (written during pairing)

/etc/systemd/system/
  lgtv-startup.service   ← powers on at boot
  lgtv-shutdown.service  ← powers off at shutdown
  lgtv-sleep.service     ← powers off on suspend, powers on at resume
```

### TV communication

`lgtv.py` connects over WebSocket (port 3001, TLS) and sends LG's SSAP protocol commands:

- **on** → `ssap://com.webos.service.tvpower/power/turnOnScreen`, then if an input is configured, `ssap://tv/switchInput` with `{"inputId": <tv_input>}` to bring up the HDMI port (e.g. `HDMI3`)
- **off** → `ssap://system/turnOff` with `standbyMode: active` (keeps network chip alive for WoL)

The default input is read from `/etc/lgtvcontrol/tv_input`. You can override it for a single run without changing the config: `lgtv on HDMI2`.

Pairing is done once. The client key is saved to `/etc/lgtvcontrol/client.key` and sent with every subsequent connection.

### Wake-on-LAN

When powering on, `lgtv.py` attempts to connect to the TV. If the first attempt fails (TV is in standby), it sends a WoL magic packet to the TV's MAC address via UDP broadcast e.g. (`192.168.1.255`, port 9), then retries the connection up to 8 times with 5-second delays while the TV boots.

The TV's MAC is detected automatically from the ARP cache during install.

### Deactivating TV Control (Temporary or Permanent)

When using a Gaming HTPC, you may want to prevent the PC from automatically waking or turning off the TV (e.g. when downloading updates in the background, streaming to another room via Moonlight/Steam Link, or using a secondary monitor).

You can easily deactivate or re-enable the sync at any time without uninstalling:

```bash
lgtv disable    # Deactivates auto-sync (or 'lgtv deactivate')
lgtv enable     # Reactivates auto-sync (or 'lgtv activate')
lgtv toggle     # Toggles between active and deactivated states
lgtv status     # Shows whether sync is active or deactivated, along with TV IP/MAC
```

- When deactivated, systemd hooks (`lgtv-on.sh` and `lgtv-off.sh`) skip all network connections and WoL packets instantly (< 1ms) with exit code 0.
- Manual commands (`lgtv on` / `lgtv off`) still work when manually typed.
- Toggling automatically displays a native desktop notification (`notify-send`).
- The configuration directory `/etc/lgtvcontrol` has `1777` permissions, allowing standard desktop users to toggle without needing `sudo`.

---

## GUI, System Tray & Steam Integration

For a Gaming HTPC, operating from the couch with a gamepad or wireless mouse is essential:

### 1. Couch-Friendly GUI Control Panel (`lgtv gui`)
Run `lgtv gui` from the terminal, or launch **LG TV Control Panel** from the KDE Plasma Application Menu / Steam.
- High-contrast, OLED-friendly dark theme with large fonts readable from 3 meters away.
- Big status badge showing whether Auto-Sync is `ACTIVATED` or `DEACTIVATED`.
- One-click buttons to toggle auto-sync, turn screen ON, or turn screen OFF.
- Falls back automatically to `kdialog` or `zenity` if Tkinter is not installed.

### 2. Desktop System Tray Applet with Tooltip (`scripts/lgtv-tray.py`)
In Bazzite Desktop Mode (KDE Plasma):
- Displays a TV icon in the system tray panel.
- **Hover Tooltip**: Shows current status (e.g., `LG TV Control: ACTIVATED (Auto-power sync enabled)`).
- **Left-Click**: Instantly toggles between Activated and Deactivated states.
- **Right-Click Context Menu**: Status indicator, Toggle Auto-Sync, Turn Screen ON/OFF, and Open Control Panel.

### 3. Steam Gamepad UI (Big Picture) Integration
Installed `.desktop` files in `/usr/local/share/applications/` allow easy Steam integration:
- Open Steam → **Games** → **Add a Non-Steam Game to My Library...**
- Select **Toggle LG TV Sync** or **LG TV Control Panel**.
- Now you can toggle TV sync straight from your controller in Big Picture Mode!

---

## Changing the TV IP / HDMI input

No need to re-run the installer. Use the built-in `config` command:

```bash
sudo lgtv config          # interactive (shows current values)
sudo lgtv config --show   # just print current values
sudo lgtv config --ip 192.168.1.42
sudo lgtv config --input HDMI2
sudo lgtv config --ip 192.168.1.42 --input none   # none/'' disables input switching
```

---

## Useful commands

```bash
# Toggle / check sync state
lgtv toggle
lgtv status
lgtv gui

# Power control
lgtv on
lgtv off

# Check service status
systemctl status lgtv-startup.service
systemctl status lgtv-shutdown.service
systemctl status lgtv-sleep.service

# View logs
journalctl -u lgtv-startup -u lgtv-shutdown -u lgtv-sleep -f

# Re-pair if the TV rejects the stored key
sudo lgtv pair
```

---

## Uninstall

```bash
./uninstall.sh
```

Removes the services, `/etc/lgtvcontrol/`, and the SELinux fcontext rules.

---

## Development

```bash
pip install -r requirements-test.txt
pytest tests/
```
