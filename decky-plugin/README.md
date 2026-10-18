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

2. **Deploy the Plugin**: run `./install.sh` from the repository root and answer **Y** when it offers the Decky plugin.
   To deploy by hand instead (`~/homebrew/plugins` is owned by root on Bazzite):
   ```bash
   sudo mkdir -p ~/homebrew/plugins/bazzite-lgtv/dist
   sudo cp decky-plugin/{plugin.json,package.json,main.py} ~/homebrew/plugins/bazzite-lgtv/
   sudo cp decky-plugin/dist/index.js ~/homebrew/plugins/bazzite-lgtv/dist/
   sudo systemctl restart plugin_loader
   ```

The main `lgtv` install must be present — the plugin drives `/etc/lgtvcontrol/lgtv.py`.

No node/npm build step is required — a pre-bundled `dist/index.js` is included out of the box.
To rebuild it from `src/index.tsx`: `npm install && npm run build` inside `decky-plugin/`.

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
