#!/usr/bin/env bash
set -euo pipefail

CONF_DIR="/etc/lgtvcontrol"
SERVICE_DIR="/etc/systemd/system"
OLD_VENV_DIR="/opt/lgtvcontrol"

RED='\033[0;31m'; GREEN='\033[0;32m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { printf "${GREEN}  [OK]${NC} %s\n" "$*"; }
info() { printf "\n${BOLD}==> %s${NC}\n" "$*"; }
die()  { printf "${RED} [ERR]${NC} %s\n" "$*" >&2; exit 1; }

cmd_exists()       { command -v "$1" >/dev/null 2>&1; }
selinux_enforcing(){ cmd_exists getenforce && [[ "$(getenforce 2>/dev/null)" == "Enforcing" ]]; }

echo
printf "${BOLD}This will remove all components from any current or older version:${NC}\n"
printf "  Services:    %s/{lgtv-startup,lgtv-shutdown,lgtv-sleep}.service\n" "$SERVICE_DIR"
printf "  Scripts/Cfg: %s/\n" "$CONF_DIR"
printf "  CLI Command: /usr/local/bin/lgtv\n"
printf "  Desktop:     /usr/local/share/applications/lgtv-*.desktop\n"
printf "  Autostart:   /etc/xdg/autostart/lgtv-tray.desktop\n"
printf "  Decky:       ~/homebrew/plugins/bazzite-lgtv\n"
[[ -d "$OLD_VENV_DIR" ]] && printf "  Legacy Venv: %s/\n" "$OLD_VENV_DIR"
[[ -f "$HOME/.aiopylgtv.sqlite" ]] && printf "  Legacy DB:   %s/.aiopylgtv.sqlite\n" "$HOME"
selinux_enforcing && printf "  SELinux:     fcontext rules for all above paths\n"
echo
read -rp "$(printf "${BOLD}Continue? [y/N]: ${NC}")" answer
[[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]] || { echo "Aborted."; exit 0; }

info "Stopping running processes and services"
pkill -f "lgtv-tray\.py" 2>/dev/null || true
sudo pkill -f "/etc/lgtvcontrol" 2>/dev/null || true

for svc in lgtv-startup lgtv-shutdown lgtv-sleep; do
    sudo systemctl stop "${svc}.service" 2>/dev/null || true
    if systemctl is-enabled --quiet "${svc}.service" 2>/dev/null; then
        sudo systemctl disable "${svc}.service" 2>/dev/null || true
    fi
    sudo rm -f "$SERVICE_DIR/${svc}.service"
    sudo rm -f "/etc/systemd/system/multi-user.target.wants/${svc}.service" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/sleep.target.wants/${svc}.service" 2>/dev/null || true
    ok "${svc}.service stopped and removed"
done
sudo systemctl daemon-reload
sudo systemctl reset-failed 2>/dev/null || true

info "Removing files and directories"
sudo rm -rf "$CONF_DIR"
ok "$CONF_DIR"

sudo rm -f /usr/local/bin/lgtv
ok "/usr/local/bin/lgtv"

# Remove desktop entries from all standard paths
sudo rm -f /usr/local/share/applications/lgtv-*.desktop 2>/dev/null || true
sudo rm -f /etc/xdg/autostart/lgtv-tray.desktop 2>/dev/null || true
rm -f "$HOME/.local/share/applications/lgtv-*.desktop" 2>/dev/null || true
cmd_exists update-desktop-database && sudo update-desktop-database /usr/local/share/applications 2>/dev/null || true
cmd_exists update-desktop-database && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
ok "Desktop entries"

# Remove Decky plugin from all standard locations
decky_removed=0
for candidate in "$HOME/homebrew/plugins/bazzite-lgtv" "/homebrew/plugins/bazzite-lgtv" "/var/homebrew/plugins/bazzite-lgtv"; do
    if [[ -d "$candidate" ]]; then
        sudo rm -rf "$candidate"   # plugins/ is root-owned on Bazzite
        ok "Decky plugin removed ($candidate)"
        decky_removed=1
    fi
done
if [[ "$decky_removed" -eq 1 ]] && systemctl is-active --quiet plugin_loader.service; then
    sudo systemctl restart plugin_loader.service 2>/dev/null || true
fi

# Remove legacy artifacts from v1/v2 (bscpylgtv / SQLite)
if [[ -d "$OLD_VENV_DIR" ]]; then
    sudo rm -rf "$OLD_VENV_DIR"
    ok "$OLD_VENV_DIR (legacy venv)"
fi
if [[ -f "$HOME/.aiopylgtv.sqlite" ]]; then
    rm -f "$HOME/.aiopylgtv.sqlite"
    ok "$HOME/.aiopylgtv.sqlite (legacy auth db)"
fi

if selinux_enforcing && cmd_exists semanage; then
    info "Removing SELinux fcontext rules"
    sudo semanage fcontext -d "${CONF_DIR}/lgtv-on\.sh"   2>/dev/null && ok "lgtv-on.sh rule"   || true
    sudo semanage fcontext -d "${CONF_DIR}/lgtv-off\.sh"  2>/dev/null && ok "lgtv-off.sh rule"  || true
    sudo semanage fcontext -d "${CONF_DIR}/lgtv\.py"      2>/dev/null && ok "lgtv.py rule"       || true
    sudo semanage fcontext -d "${CONF_DIR}/lgtv-gui\.py"  2>/dev/null && ok "lgtv-gui.py rule"   || true
    sudo semanage fcontext -d "${CONF_DIR}/lgtv-tray\.py" 2>/dev/null && ok "lgtv-tray.py rule"  || true
    sudo semanage fcontext -d "${CONF_DIR}(/.*)?"         2>/dev/null && ok "${CONF_DIR} rule"  || true
    sudo semanage fcontext -d "/usr/local/bin/lgtv"       2>/dev/null && ok "lgtv cli rule"      || true
    sudo semanage fcontext -d "${OLD_VENV_DIR}/bin(/.*)?" 2>/dev/null && ok "legacy venv rule"   || true
    if cmd_exists restorecon; then
        sudo restorecon -Rv /usr/local/bin 2>/dev/null || true
    fi
fi

echo
ok "Uninstall complete."
