# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest tests/

# Run a single test
pytest tests/test_lgtv.py::test_name

# Install test dependencies
pip install -r requirements-test.txt

# Install to the local system
./install.sh

# Test installed scripts (off 10s → on)
./install.sh --test

# Uninstall
./uninstall.sh
```

## Architecture

The project has one real source file: `scripts/lgtv.py`. Everything else is glue.

**`scripts/lgtv.py`** — standalone Python script, zero external dependencies. Implements a minimal WebSocket client from scratch (RFC 6455 framing, TLS via `ssl`, masking, all frame sizes) because the TV requires WSS on port 3001. Uses LG's SSAP protocol over that WebSocket. Runtime config is read from `/etc/lgtvcontrol/`: `tv_ip`, `client.key`, `tv_input` (optional HDMI input to switch to after power-on), and `tv_mac` (optional, for WoL).

Commands: `pair | on [input_id] [--auto] | off [--auto] | enable | disable | toggle | status | gui | config [--show|--ip IP|--input ID]`.
- `enable` / `disable` / `toggle`: creates or deletes `/etc/lgtvcontrol/disabled`. When deactivated, automated hooks (`lgtv-on.sh` / `lgtv-off.sh` or `--auto`) skip all TV power commands instantly with exit code 0.
- `status`: prints active/deactivated state, TV IP, MAC, input, pairing status, and systemd service states.
- `gui`: launches the couch-friendly GUI control panel (`scripts/lgtv-gui.py`, with Tkinter and kdialog/zenity fallbacks).
- `lgtv`: `/usr/local/bin/lgtv` CLI wrapper installed to `$PATH`.
- Desktop entries in `/usr/local/share/applications` for KDE launcher and Steam Gamepad UI integration.
- `decky-plugin/`: Decky Loader plugin for Steam Quick Access Menu (`...`) controller control.


`on`/`off` register with a stored client key then send a single SSAP request. `on` additionally sends `ssap://tv/switchInput` (payload `{"inputId": ...}`) after `turnOnScreen` when an input is set — the default comes from `tv_input`, a CLI arg overrides it per-run. `pair` does the same registration flow but waits for user approval on the TV and saves the returned key. `config` (sync, no network) reads/writes `tv_ip` and `tv_input` — interactive with no flags, or via `--ip`/`--input` (`none`/`''` clears the input).

**Retry/WoL loop** — `run()` retries the connection up to 8 times (5s delay). On the first failure for `on`, it broadcasts a WoL magic packet to the TV's MAC so the TV wakes from standby before retrying.

**Systemd services** (in `systemd/`, installed to `/etc/systemd/system/`):
- `lgtv-startup.service` — runs `lgtv-on.sh` at boot (`WantedBy=multi-user.target`)
- `lgtv-shutdown.service` — runs `lgtv-off.sh` at shutdown (`Conflicts=reboot.target` so reboots are skipped)
- `lgtv-sleep.service` — `ExecStart=lgtv-off.sh` before suspend, `ExecStop=lgtv-on.sh` after resume; `RemainAfterExit=yes` + `WantedBy=sleep.target` makes this work across all sleep states

**SELinux** — scripts must be in `/etc/lgtvcontrol/` with `bin_t` context, applied via `semanage fcontext`. This is why `~/.local/` paths don't work on Bazzite: systemd's `init_t` domain cannot execute `user_home_t` files. `/usr/local/bin/lgtv` is also labelled. `/etc/lgtvcontrol` has `1777` permissions so desktop users can toggle state without sudo.

**Tests** (`tests/test_lgtv.py`) — pure unit tests, no system dependencies. `conftest.py` adds `scripts/` to `sys.path` so `import lgtv` works. `asyncio_mode = "auto"` in `pyproject.toml` means async test functions need no decorator. Tests cover: WebSocket frame encoding/decoding, `ws_connect`, `run()` for all commands, retry logic, WoL behaviour, HDMI input switching, `config_command`, `disable_command`, `enable_command`, `toggle_command`, `status_command`, notifications, and service/template validation.

> Note: `scripts/lgtv.py` imports the Linux-only `fcntl` module, so the test suite runs on Linux (the Bazzite target), not Windows.
