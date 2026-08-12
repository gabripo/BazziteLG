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
/etc/lgtvcontrol/
  lgtv.py          ← WebSocket client (stdlib only)
  lgtv-on.sh       ← calls: python3 /etc/lgtvcontrol/lgtv.py on
  lgtv-off.sh      ← calls: python3 /etc/lgtvcontrol/lgtv.py off
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

The default input is read from `/etc/lgtvcontrol/tv_input`. You can override it for a single run without changing the config: `sudo python3 /etc/lgtvcontrol/lgtv.py on HDMI2`.

Pairing is done once. The client key is saved to `/etc/lgtvcontrol/client.key` and sent with every subsequent connection.

### Wake-on-LAN

When powering on, `lgtv.py` attempts to connect to the TV. If the first attempt fails (TV is in standby), it sends a WoL magic packet to the TV's MAC address via UDP broadcast e.g. (`192.168.1.255`, port 9), then retries the connection up to 8 times with 5-second delays while the TV boots.

The TV's MAC is detected automatically from the ARP cache during install.

### Shutdown vs reboot

`lgtv-shutdown.service` has `Conflicts=reboot.target`, so the screen turns off on **shutdown only** — reboots leave it alone.

### Suspend/resume

`lgtv-sleep.service` runs `lgtv-off.sh` before the system suspends and `lgtv-on.sh` after it wakes. It uses `RemainAfterExit=yes` so systemd tracks the "active" state across the sleep cycle and calls `ExecStop` (the on command) on resume. It activates for all sleep states: suspend, hibernate, and hybrid-sleep.

---

## Changing the TV IP / HDMI input

No need to re-run the installer. Use the built-in `config` command:

```bash
sudo python3 /etc/lgtvcontrol/lgtv.py config          # interactive (shows current values)
sudo python3 /etc/lgtvcontrol/lgtv.py config --show   # just print current values
sudo python3 /etc/lgtvcontrol/lgtv.py config --ip 192.168.1.42
sudo python3 /etc/lgtvcontrol/lgtv.py config --input HDMI2
sudo python3 /etc/lgtvcontrol/lgtv.py config --ip 192.168.1.42 --input none   # none/'' disables input switching
```

Changing the IP does **not** require re-pairing — the client key is stored by the TV and is not tied to the IP the connection comes from. Switching to a *different* TV requires `pair` again.

---

## Useful commands

```bash
# Check service status
systemctl status lgtv-startup.service
systemctl status lgtv-shutdown.service
systemctl status lgtv-sleep.service

# View logs
journalctl -u lgtv-startup -u lgtv-shutdown -u lgtv-sleep -f

# Manually trigger
sudo systemctl start lgtv-startup.service
sudo systemctl start lgtv-shutdown.service

# Re-pair if the TV rejects the stored key
sudo python3 /etc/lgtvcontrol/lgtv.py pair

# Change TV IP / HDMI input
sudo python3 /etc/lgtvcontrol/lgtv.py config
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
