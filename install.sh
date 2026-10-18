#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TV_IP="192.168.1.30"
DEFAULT_HDMI_INPUT="HDMI_3"
CONF_DIR="/etc/lgtvcontrol"
SERVICE_DIR="/etc/systemd/system"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}  [!!]${NC} %s\n" "$*"; }
info() { printf "\n${BOLD}==> %s${NC}\n" "$*"; }
die()  { printf "${RED} [ERR]${NC} %s\n" "$*" >&2; exit 1; }

cmd_exists()       { command -v "$1" >/dev/null 2>&1; }
selinux_enforcing(){ cmd_exists getenforce && [[ "$(getenforce 2>/dev/null)" == "Enforcing" ]]; }

semanage_add() {
    sudo semanage fcontext -a -t bin_t "$1" 2>/dev/null \
        || sudo semanage fcontext -m -t bin_t "$1"
}

# ---------------------------------------------------------------------------
# Test mode — turn screen off, countdown, turn screen on
# ---------------------------------------------------------------------------
run_test() {
    [[ -x "$CONF_DIR/lgtv-off.sh" && -x "$CONF_DIR/lgtv-on.sh" ]] \
        || die "Scripts not found in $CONF_DIR — run install first."

    info "Screen test"
    printf "  Turning screen OFF... "
    "$CONF_DIR/lgtv-off.sh" && printf "${GREEN}done${NC}\n" \
        || { printf "${RED}FAILED${NC}\n"; exit 1; }

    for i in {10..1}; do
        printf "\r  Turning screen back ON in %2d seconds... " "$i"
        sleep 1
    done
    printf "\r  Turning screen ON...                         \n"

    "$CONF_DIR/lgtv-on.sh" && printf "  ${GREEN}done${NC}\n" \
        || { printf "  ${RED}FAILED${NC}\n"; exit 1; }

    echo
    ok "Test complete — screen should be on."
}

# ---------------------------------------------------------------------------
# Args: --test (screen test) | --input <id> (HDMI input, skips the prompt)
# ---------------------------------------------------------------------------
INPUT_ARG=""
RUN_TEST=0
i=1
while [[ $i -le $# ]]; do
    case "${!i}" in
        --test)
            RUN_TEST=1
            ;;
        --input)
            i=$((i + 1))
            [[ $i -le $# ]] || die "--input requires a value (e.g. HDMI_2 or none)"
            INPUT_ARG="${!i}"
            ;;
        *)
            die "Unknown option: ${!i}"
            ;;
    esac
    i=$((i + 1))
done

if [[ "$RUN_TEST" -eq 1 ]]; then
    run_test
    exit 0
fi

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
info "Checking dependencies"

cmd_exists python3 || die "python3 not found. Install it first."
ok "python3"

if selinux_enforcing; then
    cmd_exists semanage \
        || die "semanage not found. Install: sudo dnf install policycoreutils-python-utils"
    ok "semanage (SELinux is Enforcing)"
    cmd_exists restorecon && ok "restorecon" \
        || warn "restorecon not found — install policycoreutils for best results"
else
    warn "SELinux is not Enforcing — skipping SELinux context steps"
fi

# ---------------------------------------------------------------------------
# Gather config
# ---------------------------------------------------------------------------
info "Configuration"

read -rp "$(printf "  LG TV IP address [${DEFAULT_TV_IP}]: ")" TV_IP
TV_IP="${TV_IP:-$DEFAULT_TV_IP}"

if [[ ! "$TV_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    die "'$TV_IP' is not a valid IPv4 address"
fi
ok "TV IP: $TV_IP"

if [[ -n "$INPUT_ARG" ]]; then
    HDMI_INPUT="$INPUT_ARG"
else
    read -rp "$(printf "  HDMI input to switch to after power-on [${DEFAULT_HDMI_INPUT}] (or 'none'): ")" HDMI_INPUT
    HDMI_INPUT="${HDMI_INPUT:-$DEFAULT_HDMI_INPUT}"
fi
if [[ "$HDMI_INPUT" =~ ^[Hh][Dd][Mm][Ii][\ _-]?([0-9])$ ]]; then
    HDMI_INPUT="HDMI_${BASH_REMATCH[1]}"   # webOS ids are HDMI_1..HDMI_4
fi
if [[ "$HDMI_INPUT" == "none" ]]; then
    HDMI_INPUT=""
elif [[ -n "$HDMI_INPUT" && ! "$HDMI_INPUT" =~ ^[A-Za-z0-9./_-]+$ ]]; then
    die "'$HDMI_INPUT' is not a valid input id"
fi
if [[ -n "$HDMI_INPUT" ]]; then
    ok "HDMI input: $HDMI_INPUT"
else
    warn "No HDMI input configured — TV will not switch inputs on power-on"
fi

# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------
echo
printf "  Scripts:  %s\n" "$CONF_DIR"
printf "  Services: %s\n" "$SERVICE_DIR"
echo
read -rp "$(printf "${BOLD}Continue? [Y/n]: ${NC}")" answer
answer="${answer:-Y}"
[[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]] || { echo "Aborted."; exit 0; }

# ---------------------------------------------------------------------------
# Install scripts
# ---------------------------------------------------------------------------
info "Installing scripts to $CONF_DIR"

sudo mkdir -p "$CONF_DIR"

# TV IP (read by lgtv.py at runtime)
echo "${TV_IP}" | sudo tee "$CONF_DIR/tv_ip" > /dev/null
sudo chmod 644 "$CONF_DIR/tv_ip"
ok "tv_ip"

# Default HDMI input (read by lgtv.py at runtime; empty = no input switching)
if [[ -n "$HDMI_INPUT" ]]; then
    echo "$HDMI_INPUT" | sudo tee "$CONF_DIR/tv_input" > /dev/null
    sudo chmod 644 "$CONF_DIR/tv_input"
    ok "tv_input"
else
    sudo rm -f "$CONF_DIR/tv_input"   # clear any stale value from a previous install
fi

# lgtv.py
sudo cp "$SCRIPT_DIR/scripts/lgtv.py" "$CONF_DIR/lgtv.py"
sudo chmod 755 "$CONF_DIR/lgtv.py"
ok "lgtv.py"

# GUI and Tray helpers
sudo cp "$SCRIPT_DIR/scripts/lgtv-gui.py" "$CONF_DIR/lgtv-gui.py"
sudo chmod 755 "$CONF_DIR/lgtv-gui.py"
ok "lgtv-gui.py"

sudo cp "$SCRIPT_DIR/scripts/lgtv-tray.py" "$CONF_DIR/lgtv-tray.py"
sudo chmod 755 "$CONF_DIR/lgtv-tray.py"
ok "lgtv-tray.py"

# Shell wrappers
for cmd in on off; do
    sudo cp "$SCRIPT_DIR/scripts/lgtv-${cmd}.sh.tpl" "$CONF_DIR/lgtv-${cmd}.sh"
    sudo chmod 755 "$CONF_DIR/lgtv-${cmd}.sh"
    ok "lgtv-${cmd}.sh"
done

# CLI command in PATH
sudo mkdir -p /usr/local/bin
sudo cp "$SCRIPT_DIR/scripts/lgtv-cli" /usr/local/bin/lgtv
sudo chmod 755 /usr/local/bin/lgtv
ok "lgtv command (/usr/local/bin/lgtv)"

# Set sticky permissions so desktop user can toggle active state without sudo
sudo chmod 1777 "$CONF_DIR"
ok "Set permissions (1777 on $CONF_DIR for passwordless user toggle)"

# Desktop and Steam integration (.desktop files)
APPS_DIR="/usr/local/share/applications"
sudo mkdir -p "$APPS_DIR"
if [[ -d "$SCRIPT_DIR/desktop" ]]; then
    for f in "$SCRIPT_DIR"/desktop/*.desktop; do
        if [[ -f "$f" ]]; then
            sudo cp "$f" "$APPS_DIR/"
            sudo chmod 644 "$APPS_DIR/$(basename "$f")"
            ok "$(basename "$f")"
        fi
    done
    cmd_exists update-desktop-database && sudo update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# SELinux file contexts
# ---------------------------------------------------------------------------
if selinux_enforcing; then
    info "Applying SELinux file contexts"

    semanage_add "${CONF_DIR}/lgtv-on\.sh"
    semanage_add "${CONF_DIR}/lgtv-off\.sh"
    semanage_add "${CONF_DIR}/lgtv\.py"
    semanage_add "${CONF_DIR}/lgtv-gui\.py"
    semanage_add "${CONF_DIR}/lgtv-tray\.py"
    semanage_add "/usr/local/bin/lgtv"

    if cmd_exists restorecon; then
        sudo restorecon -Rv "$CONF_DIR/" /usr/local/bin/lgtv > /dev/null
        ok "Contexts applied and restored"
    else
        warn "restorecon not found — reboot or run: sudo restorecon -Rv $CONF_DIR/ /usr/local/bin/lgtv"
    fi
fi

# ---------------------------------------------------------------------------
# Pair with TV
# ---------------------------------------------------------------------------
info "Pairing with TV at $TV_IP"

if [[ -f "$CONF_DIR/client.key" ]]; then
    warn "Existing client key found."
    read -rp "$(printf "  Re-pair with TV? [y/N]: ")" repair
    repair="${repair:-N}"
    if [[ ! "$repair" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        ok "Keeping existing key"
    else
        sudo python3 "$CONF_DIR/lgtv.py" pair || die "Pairing failed"
    fi
else
    echo "  Make sure your TV is on and reachable at $TV_IP"
    echo "  A prompt will appear on the TV — press OK with your remote."
    echo
    sudo python3 "$CONF_DIR/lgtv.py" pair || die "Pairing failed. Ensure TV is on and try again."
fi

# ---------------------------------------------------------------------------
# Detect TV MAC address for Wake-on-LAN
# ---------------------------------------------------------------------------
info "Detecting TV MAC address (Wake-on-LAN)"

# Ping once to ensure the ARP cache is fresh, then read /proc/net/arp
ping -c 1 -W 2 "$TV_IP" > /dev/null 2>&1 || true
tv_mac=$(awk -v ip="$TV_IP" '$1==ip && $4!="00:00:00:00:00:00" { print $4 }' /proc/net/arp 2>/dev/null || true)

if [[ -n "$tv_mac" ]]; then
    echo "$tv_mac" | sudo tee "$CONF_DIR/tv_mac" > /dev/null
    sudo chmod 644 "$CONF_DIR/tv_mac"
    ok "TV MAC: $tv_mac (saved for Wake-on-LAN)"
else
    warn "Could not detect TV MAC — Wake-on-LAN will not be available"
    warn "If needed: echo 'AA:BB:CC:DD:EE:FF' | sudo tee $CONF_DIR/tv_mac"
fi

# ---------------------------------------------------------------------------
# Systemd services
# ---------------------------------------------------------------------------
info "Installing systemd services"

for svc in lgtv-startup lgtv-shutdown lgtv-sleep; do
    sudo cp "$SCRIPT_DIR/systemd/${svc}.service" "$SERVICE_DIR/"
    ok "${svc}.service"
done

sudo systemctl daemon-reload
sudo systemctl enable lgtv-startup.service lgtv-shutdown.service lgtv-sleep.service
ok "Services enabled"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
info "Installation complete"
printf "  Useful commands:\n"
printf "    Toggle auto-sync: lgtv toggle (or lgtv disable / lgtv enable)\n"
printf "    Check status:     lgtv status\n"
printf "    Control panel:    lgtv gui\n"
printf "    Screen test:      ./install.sh --test\n"
printf "    View logs:        journalctl -u lgtv-startup -u lgtv-shutdown -u lgtv-sleep -f\n"
printf "    Re-pair TV:       sudo lgtv pair\n"
printf "    Change IP/input:  sudo lgtv config\n"
echo


# shellcheck disable=SC2059
read -rp "$(printf "${BOLD}Run screen test now? (off 10s → on) [Y/n]: ${NC}")" answer
answer="${answer:-Y}"
if [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    run_test
fi
