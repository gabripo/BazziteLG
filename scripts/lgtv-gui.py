#!/usr/bin/env python3
"""LG TV Control Panel — Couch-friendly GUI for Bazzite Gaming HTPC.

Zero external dependencies: uses Tkinter (standard library) with
automatic fallback to kdialog or zenity on Bazzite OS.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

CONF_DIR = Path("/etc/lgtvcontrol")
LGTV_PY = CONF_DIR / "lgtv.py"
if not LGTV_PY.exists():
    LGTV_PY = Path(__file__).parent / "lgtv.py"

IP_FILE = CONF_DIR / "tv_ip"
INPUT_FILE = CONF_DIR / "tv_input"
MAC_FILE = CONF_DIR / "tv_mac"
KEY_FILE = CONF_DIR / "client.key"
DISABLED_FILE = CONF_DIR / "disabled"


def conf_val(p: Path) -> str:
    return p.read_text().strip() if p.exists() else ""


def is_disabled() -> bool:
    return DISABLED_FILE.exists()


def run_lgtv_cmd(cmd: str, *args) -> tuple[int, str]:
    target = [sys.executable, str(LGTV_PY), cmd] + list(args)
    res = subprocess.run(target, capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    return res.returncode, out


# ── Tkinter GUI (Preferred) ───────────────────────────────────────────────────

def launch_tkinter():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("LG TV Control Panel")
    root.geometry("520x460")
    root.configure(bg="#181825")
    root.resizable(False, False)

    # Styles & Fonts
    FONT_FAMILY = "DejaVu Sans" if "DejaVu Sans" in tk.font.families() else "Helvetica"
    font_title = (FONT_FAMILY, 18, "bold")
    font_status = (FONT_FAMILY, 14, "bold")
    font_body = (FONT_FAMILY, 12)
    font_btn = (FONT_FAMILY, 13, "bold")
    font_meta = (FONT_FAMILY, 11)

    # Header
    header_frame = tk.Frame(root, bg="#181825")
    header_frame.pack(fill="x", padx=24, pady=(20, 10))

    lbl_title = tk.Label(
        header_frame,
        text="📺 LG OLED TV Control",
        font=font_title,
        fg="#cdd6f4",
        bg="#181825",
    )
    lbl_title.pack(anchor="w")

    lbl_sub = tk.Label(
        header_frame,
        text="Automatic power management for Bazzite Gaming HTPC",
        font=font_meta,
        fg="#a6adc8",
        bg="#181825",
    )
    lbl_sub.pack(anchor="w", pady=(2, 0))

    # Status Card
    status_card = tk.Frame(root, bg="#1e1e2e", highlightthickness=2, highlightbackground="#313244", bd=0)
    status_card.pack(fill="x", padx=24, pady=12)

    lbl_badge = tk.Label(status_card, font=font_status, padx=16, pady=10)
    lbl_badge.pack(fill="x")

    lbl_desc = tk.Label(status_card, font=font_body, fg="#bac2de", bg="#1e1e2e", pady=4)
    lbl_desc.pack(fill="x")

    # Meta Info Frame
    info_frame = tk.Frame(root, bg="#181825")
    info_frame.pack(fill="x", padx=24, pady=6)

    lbl_info_ip = tk.Label(info_frame, font=font_meta, fg="#9399b2", bg="#181825")
    lbl_info_ip.pack(anchor="w")

    lbl_info_input = tk.Label(info_frame, font=font_meta, fg="#9399b2", bg="#181825")
    lbl_info_input.pack(anchor="w")

    def refresh_ui():
        disabled = is_disabled()
        if disabled:
            lbl_badge.config(
                text="○  AUTO-SYNC: DEACTIVATED",
                fg="#f38ba8",
                bg="#31222b",
            )
            lbl_desc.config(
                text="TV will NOT power on/off with PC sleep or boot",
                bg="#31222b",
                fg="#f2cdcd",
            )
            status_card.config(highlightbackground="#f38ba8", bg="#31222b")
            btn_toggle.config(
                text="⏻  ACTIVATE AUTO-SYNC",
                bg="#a6e3a1",
                activebackground="#94e2d5",
                fg="#11111b",
            )
        else:
            lbl_badge.config(
                text="●  AUTO-SYNC: ACTIVATED",
                fg="#a6e3a1",
                bg="#1a2e26",
            )
            lbl_desc.config(
                text="TV automatically syncs power with HTPC",
                bg="#1a2e26",
                fg="#a6adc8",
            )
            status_card.config(highlightbackground="#a6e3a1", bg="#1a2e26")
            btn_toggle.config(
                text="⏸  DEACTIVATE AUTO-SYNC",
                bg="#f38ba8",
                activebackground="#eba0ac",
                fg="#11111b",
            )

        tv_ip = conf_val(IP_FILE) or "Not configured"
        mac = conf_val(MAC_FILE) or "Not set"
        input_id = conf_val(INPUT_FILE) or "None (no switch)"
        lbl_info_ip.config(text=f"Target: {tv_ip}   |   WoL MAC: {mac}")
        lbl_info_input.config(text=f"Default HDMI: {input_id}")

    # Action Buttons
    btn_frame = tk.Frame(root, bg="#181825")
    btn_frame.pack(fill="x", padx=24, pady=12)

    def on_toggle():
        btn_toggle.config(state="disabled")
        root.update()
        code, out = run_lgtv_cmd("toggle")
        btn_toggle.config(state="normal")
        if code != 0:
            messagebox.showerror("Error", out or "Failed to toggle state.")
        refresh_ui()

    def on_power(mode: str):
        lbl_desc.config(text=f"Sending {mode.upper()} command to TV...", fg="#f9e2af")
        root.update()
        code, out = run_lgtv_cmd(mode)
        refresh_ui()
        if code != 0:
            messagebox.showwarning("Warning", f"Command output:\n{out}")

    btn_toggle = tk.Button(
        btn_frame,
        text="Toggle Auto-Sync",
        font=font_btn,
        relief="flat",
        cursor="hand2",
        pady=8,
        command=on_toggle,
    )
    btn_toggle.pack(fill="x", pady=4)

    power_grid = tk.Frame(btn_frame, bg="#181825")
    power_grid.pack(fill="x", pady=6)

    btn_on = tk.Button(
        power_grid,
        text="☼ Turn TV ON",
        font=font_btn,
        bg="#89b4fa",
        activebackground="#b4befe",
        fg="#11111b",
        relief="flat",
        cursor="hand2",
        pady=6,
        command=lambda: on_power("on"),
    )
    btn_on.pack(side="left", fill="x", expand=True, padx=(0, 4))

    btn_off = tk.Button(
        power_grid,
        text="☾ Turn TV OFF",
        font=font_btn,
        bg="#45475a",
        activebackground="#585b70",
        fg="#cdd6f4",
        relief="flat",
        cursor="hand2",
        pady=6,
        command=lambda: on_power("off"),
    )
    btn_off.pack(side="right", fill="x", expand=True, padx=(4, 0))

    # Footer Refresh & Close
    footer = tk.Frame(root, bg="#181825")
    footer.pack(fill="x", side="bottom", padx=24, pady=14)

    btn_refresh = tk.Button(
        footer,
        text="🗘 Refresh",
        font=font_meta,
        bg="#313244",
        fg="#cdd6f4",
        relief="flat",
        cursor="hand2",
        command=refresh_ui,
    )
    btn_refresh.pack(side="left")

    btn_close = tk.Button(
        footer,
        text="Close",
        font=font_meta,
        bg="#313244",
        fg="#cdd6f4",
        relief="flat",
        cursor="hand2",
        command=root.destroy,
    )
    btn_close.pack(side="right")

    refresh_ui()
    root.mainloop()


# ── kdialog / zenity Fallback ─────────────────────────────────────────────────

def launch_dialog_fallback():
    kdialog = shutil.which("kdialog")
    zenity = shutil.which("zenity")

    while True:
        disabled = is_disabled()
        status_text = "DEACTIVATED (TV power sync paused)" if disabled else "ACTIVATED (Auto-sync active)"
        toggle_label = "Activate Auto-Sync" if disabled else "Deactivate Auto-Sync"

        if kdialog:
            cmd = [
                kdialog,
                "--title", "LG TV Power Control",
                "--menu", f"Current Status: {status_text}\nChoose an action:",
                "toggle", f"1. {toggle_label}",
                "on",     "2. Turn TV ON (Wake-on-LAN)",
                "off",    "3. Turn TV OFF (Standby)",
                "status", "4. View Status Details",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            choice = res.stdout.strip()
            if res.returncode != 0 or not choice:
                break
        elif zenity:
            cmd = [
                zenity,
                "--title", "LG TV Power Control",
                "--list",
                "--column", "Code", "--column", "Action",
                "--hide-column", "1",
                "--text", f"Status: {status_text}",
                "toggle", toggle_label,
                "on",     "Turn TV ON (Wake-on-LAN)",
                "off",    "Turn TV OFF (Standby)",
                "status", "View Status Details",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            choice = res.stdout.strip()
            if res.returncode != 0 or not choice:
                break
        else:
            print("No GUI environment (tkinter, kdialog, or zenity) available.")
            print(f"Current status: {status_text}")
            run_lgtv_cmd("status")
            return

        if choice in ("toggle", "on", "off"):
            code, out = run_lgtv_cmd(choice)
            if kdialog:
                subprocess.run([kdialog, "--msgbox", out or "Done"])
            elif zenity:
                subprocess.run([zenity, "--info", "--text", out or "Done"])
        elif choice == "status":
            code, out = run_lgtv_cmd("status")
            if kdialog:
                subprocess.run([kdialog, "--msgbox", out])
            elif zenity:
                subprocess.run([zenity, "--info", "--text", out])


def main():
    try:
        launch_tkinter()
    except Exception:
        launch_dialog_fallback()


if __name__ == "__main__":
    main()
