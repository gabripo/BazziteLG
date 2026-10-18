#!/usr/bin/env python3
"""LG TV System Tray Applet & Tooltip for Bazzite Desktop Mode (KDE Plasma).

Provides:
- Live tooltip showing current TV auto-power sync state.
- One-click toggle between Activated and Deactivated.
- Right-click context menu for manual ON/OFF and opening the Control Panel.
- Native integration with KDE Plasma system tray.
"""

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

def run_qt_tray():
    # Try importing Qt bindings
    QApp = None
    for mod in ("PyQt6.QtWidgets", "PySide6.QtWidgets", "PyQt5.QtWidgets", "PySide2.QtWidgets"):
        try:
            m = __import__(mod, fromlist=["QApplication", "QSystemTrayIcon", "QMenu", "QAction"])
            QApplication = getattr(m, "QApplication")
            QSystemTrayIcon = getattr(m, "QSystemTrayIcon")
            QMenu = getattr(m, "QMenu")
            QAction = getattr(m, "QAction", None)
            if not QAction:
                # PyQt5/PySide2 QAction is in QtWidgets or QtGui
                try:
                    from PyQt5.QtWidgets import QAction
                except ImportError:
                    from PySide2.QtWidgets import QAction
            from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter if "PySide6" in mod else None
            break
        except ImportError:
            continue
    else:
        return False

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = QSystemTrayIcon()

    def update_tray():
        disabled = is_disabled()
        tray.setToolTip(get_tooltip_text())
        # Use system icon if available
        icon_name = "media-playback-pause" if disabled else "video-display"
        try:
            from PyQt6.QtGui import QIcon
            tray.setIcon(QIcon.fromTheme(icon_name))
        except Exception:
            try:
                from PySide6.QtGui import QIcon
                tray.setIcon(QIcon.fromTheme(icon_name))
            except Exception:
                pass

    def on_toggle():
        run_lgtv("toggle")
        # Give filesystem a moment to update
        time.sleep(0.1)
        update_tray()

    def on_open_gui():
        gui_script = CONF_DIR / "lgtv-gui.py"
        if not gui_script.exists():
            gui_script = Path(__file__).parent / "lgtv-gui.py"
        subprocess.Popen([sys.executable, str(gui_script)])

    def build_menu():
        menu = QMenu()
        disabled = is_disabled()

        status_action = menu.addAction(f"Status: {'DEACTIVATED' if disabled else 'ACTIVATED'}")
        status_action.setEnabled(False)

        toggle_text = "Activate Auto-Sync" if disabled else "Deactivate Auto-Sync"
        act_toggle = menu.addAction(toggle_text)
        act_toggle.triggered.connect(on_toggle)

        menu.addSeparator()

        act_on = menu.addAction("Turn TV Screen ON")
        act_on.triggered.connect(lambda: run_lgtv("on"))

        act_off = menu.addAction("Turn TV Screen OFF")
        act_off.triggered.connect(lambda: run_lgtv("off"))

        menu.addSeparator()

        act_gui = menu.addAction("Open Control Panel...")
        act_gui.triggered.connect(on_open_gui)

        act_quit = menu.addAction("Quit Tray")
        act_quit.triggered.connect(app.quit)

        return menu

    def on_tray_activated(reason):
        # Trigger on left-click (Trigger = 3 in Qt)
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, 3):
            on_toggle()
        elif reason in (QSystemTrayIcon.ActivationReason.Context, 1, 2):
            tray.setContextMenu(build_menu())

    tray.activated.connect(on_tray_activated)
    tray.setContextMenu(build_menu())
    update_tray()
    tray.show()

    # Periodic check for external changes (e.g. from terminal or shortcut)
    try:
        from PyQt6.QtCore import QTimer
    except ImportError:
        try:
            from PySide6.QtCore import QTimer
        except ImportError:
            try:
                from PyQt5.QtCore import QTimer
            except ImportError:
                from PySide2.QtCore import QTimer

    timer = QTimer()
    timer.timeout.connect(update_tray)
    timer.start(2000)

    return app.exec() if hasattr(app, "exec") else app.exec_()


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


def main():
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
