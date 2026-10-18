# BazziteLG Decky Loader Plugin

Control your LG OLED TV power and sync directly from the **Steam Quick Access Menu (`...`)** on Bazzite OS.

## Features

- **Auto Power Sync Toggle**: Instantly pause or resume automatic TV power sync on sleep, wake, and boot.
- **Quick Power Controls**:
  - Turn TV ON (Wake-on-LAN magic packet + HDMI input switch).
  - Turn TV OFF (active standby).
- **Live Status & Info**: Displays whether sync is Active, TV IP address, WoL MAC, and configured HDMI port.
- **Native Steam Toasts**: Shows on-screen notification popups inside Steam Gamepad UI when settings change.

## Setup on Bazzite

1. **Enable Decky Loader via Bazzite Portal**:
   - Open **Bazzite Portal** in Desktop or Gaming mode and toggle **Decky Loader** ON.

2. **Deploy the Plugin**:
   Simply copy or symlink this folder to your Decky plugins directory:
   ```bash
   mkdir -p ~/homebrew/plugins
   cp -r decky-plugin ~/homebrew/plugins/bazzite-lgtv
   ```
   *(Or create a symlink for live development: `ln -s "$(pwd)/decky-plugin" ~/homebrew/plugins/bazzite-lgtv`)*

3. Restart Steam or Decky Loader (`systemctl --user restart plugin_loader` or reboot).

No node/npm build step is required — a pre-bundled `dist/index.js` is included out of the box.

## Structure

```
decky-plugin/
├── plugin.json         ← Decky Loader manifest
├── package.json        ← Frontend npm / rollup configuration
├── tsconfig.json       ← TypeScript configuration
├── rollup.config.js    ← Bundler config (@decky/rollup)
├── src/
│   └── index.tsx       ← React / TypeScript frontend source
├── dist/
│   └── index.js        ← Pre-bundled ES module (ready to run without build step)
└── main.py             ← Python backend executed by Decky Loader
```
