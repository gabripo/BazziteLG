#!/usr/bin/env python3
"""LG TV System Tray Applet & Tooltip for Bazzite Desktop Mode (KDE Plasma).

Provides:
- Live tooltip showing current TV auto-power sync state.
- One-click toggle between Activated and Deactivated.
- Right-click context menu for manual ON/OFF and opening the Control Panel.
- Native integration with KDE Plasma system tray.
"""

import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONF_DIR = Path("/etc/lgtvcontrol")
LGTV_PY = CONF_DIR / "lgtv.py"
if not LGTV_PY.exists():
    LGTV_PY = Path(__file__).parent / "lgtv.py"

DISABLED_FILE = CONF_DIR / "disabled"


def is_disabled() -> bool:
    return DISABLED_FILE.exists()


def run_lgtv(cmd: str) -> None:
    subprocess.Popen([sys.executable, str(LGTV_PY), cmd])


def get_tooltip_text() -> str:
    if is_disabled():
        return "LG TV Control: DEACTIVATED\nAuto-power sync is paused (TV stays on/off)"
    return "LG TV Control: ACTIVATED\nAuto-power sync is enabled with HTPC"


# ── Qt Backend (Native for KDE Plasma on Bazzite) ───────────────────────────────

def _import_qt():
    """Return (QtWidgets, QtGui, QtCore) from the first available Qt binding."""
    for binding in ("PyQt6", "PySide6", "PyQt5", "PySide2"):
        try:
            widgets = __import__(f"{binding}.QtWidgets", fromlist=["QtWidgets"])
            gui = __import__(f"{binding}.QtGui", fromlist=["QtGui"])
            core = __import__(f"{binding}.QtCore", fromlist=["QtCore"])
            return widgets, gui, core
        except ImportError:
            continue
    return None


def run_qt_tray():
    qt = _import_qt()
    if qt is None:
        return False
    QtWidgets, QtGui, QtCore = qt

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("LG TV Control")   # name shown in KDE's tray settings
    app.setDesktopFileName("lgtv-tray")

    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray is available in this session.", file=sys.stderr)
        return True

    Trigger = QtWidgets.QSystemTrayIcon.ActivationReason.Trigger
    fallback_icon = app.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon)

    tray = QtWidgets.QSystemTrayIcon()
    menu = QtWidgets.QMenu()   # must outlive the tray, so keep one instance

    def update_tray():
        tray.setToolTip(get_tooltip_text())
        icon_name = "media-playback-pause" if is_disabled() else "video-display"
        tray.setIcon(QtGui.QIcon.fromTheme(icon_name, fallback_icon))

    def on_toggle():
        run_lgtv("toggle")
        # lgtv.py runs async; refresh once it has had time to flip the state file
        QtCore.QTimer.singleShot(500, update_tray)

    def on_open_gui():
        gui_script = CONF_DIR / "lgtv-gui.py"
        if not gui_script.exists():
            gui_script = Path(__file__).parent / "lgtv-gui.py"
        subprocess.Popen([sys.executable, str(gui_script)])

    def build_menu():
        menu.clear()
        disabled = is_disabled()

        status_action = menu.addAction(f"Status: {'DEACTIVATED' if disabled else 'ACTIVATED'}")
        status_action.setEnabled(False)

        toggle_text = "Activate Auto-Sync" if disabled else "Deactivate Auto-Sync"
        menu.addAction(toggle_text).triggered.connect(on_toggle)

        menu.addSeparator()
        menu.addAction("Turn TV Screen ON").triggered.connect(lambda: run_lgtv("on"))
        menu.addAction("Turn TV Screen OFF").triggered.connect(lambda: run_lgtv("off"))

        menu.addSeparator()
        menu.addAction("Open Control Panel...").triggered.connect(on_open_gui)
        menu.addAction("Quit Tray").triggered.connect(app.quit)

    def on_tray_activated(reason):
        if reason == Trigger:   # left-click
            on_toggle()

    menu.aboutToShow.connect(build_menu)   # rebuild so labels reflect current state
    build_menu()
    tray.setContextMenu(menu)
    tray.activated.connect(on_tray_activated)
    update_tray()
    tray.show()

    # Periodic check for external changes (e.g. from terminal or shortcut)
    timer = QtCore.QTimer()
    timer.timeout.connect(update_tray)
    timer.start(2000)

    app.exec() if hasattr(app, "exec") else app.exec_()
    return True


# ── AppIndicator / Gtk Fallback ───────────────────────────────────────────────

def run_appindicator_tray():
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as appindicator
        except (ValueError, ImportError):
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3 as appindicator
        from gi.repository import Gtk, GLib
    except Exception:
        return False

    indicator = appindicator.Indicator.new(
        "lgtv-control",
        "video-display",
        appindicator.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(appindicator.IndicatorStatus.ACTIVE)

    def update():
        disabled = is_disabled()
        icon = "media-playback-pause" if disabled else "video-display"
        indicator.set_icon_full(icon, get_tooltip_text())
        return True

    def build_menu():
        menu = Gtk.Menu()
        disabled = is_disabled()

        status_item = Gtk.MenuItem(label=f"Status: {'DEACTIVATED' if disabled else 'ACTIVATED'}")
        status_item.set_sensitive(False)
        menu.append(status_item)

        toggle_label = "Activate Auto-Sync" if disabled else "Deactivate Auto-Sync"
        toggle_item = Gtk.MenuItem(label=toggle_label)
        toggle_item.connect("activate", lambda _: (run_lgtv("toggle"), update()))
        menu.append(toggle_item)

        menu.append(Gtk.SeparatorMenuItem())

        on_item = Gtk.MenuItem(label="Turn TV Screen ON")
        on_item.connect("activate", lambda _: run_lgtv("on"))
        menu.append(on_item)

        off_item = Gtk.MenuItem(label="Turn TV Screen OFF")
        off_item.connect("activate", lambda _: run_lgtv("off"))
        menu.append(off_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit Tray")
        quit_item.connect("activate", lambda _: Gtk.main_quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    indicator.set_menu(build_menu())
    update()
    GLib.timeout_add_seconds(2, update)
    Gtk.main()
    return True


def _acquire_single_instance_lock():
    """Return a held lock file, or None if another tray instance is running."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    lock = open(Path(runtime_dir) / "lgtv-tray.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def main():
    lock = _acquire_single_instance_lock()
    if lock is None:
        print("LG TV tray is already running.")
        return

    # 1. Try native Qt (ideal for KDE Plasma on Bazzite)
    if run_qt_tray():
        return
    # 2. Try AppIndicator / Gtk
    if run_appindicator_tray():
        return

    print("No system tray backend (PyQt/PySide or PyGObject) is currently installed.")
    print("You can toggle TV control via CLI:")
    print("  lgtv toggle")
    print("Or open the GUI control panel:")
    print("  lgtv gui")


if __name__ == "__main__":
    main()
