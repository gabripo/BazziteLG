// Pre-built bundle equivalent to `npm run build` (@decky/rollup) for src/index.tsx.
// Decky Loader provides React as the SP_REACT global and @decky/ui as DFL;
// the @decky/api preamble below is what @decky/rollup inlines.

const manifest = {"name":"LG TV Control"};
const API_VERSION = 1;
const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!internalAPIConnection) {
    throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
}
let api;
try {
    api = internalAPIConnection.connect(API_VERSION, manifest.name);
}
catch {
    api = internalAPIConnection.connect(1, manifest.name);
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
}
if (api._version != API_VERSION) {
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
}
const call = api.call;
const toaster = api.toaster;
const definePlugin = (fn) => {
    return (...args) => {
        return fn(...args);
    };
};

const { PanelSection, PanelSectionRow, ToggleField, ButtonItem, Field, staticClasses } = DFL;
const { useState, useEffect, createElement: h } = SP_REACT;

const TITLE = "LG TV Control";
const toast = (body, title = TITLE) => toaster.toast({ title, body });

const TvIcon = () =>
  h("svg", {
    viewBox: "0 0 24 24",
    fill: "currentColor",
    width: "1em",
    height: "1em",
    style: { display: "inline-block", verticalAlign: "middle" }
  },
    h("path", {
      d: "M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z"
    })
  );

const Content = () => {
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [tvIp, setTvIp] = useState("");
  const [tvMac, setTvMac] = useState("");
  const [tvInput, setTvInput] = useState("");
  const [paired, setPaired] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetchStatus = async () => {
    try {
      const status = await call("get_status");
      setSyncEnabled(Boolean(status.sync_enabled));
      setTvIp(status.tv_ip || "(not set)");
      setTvMac(status.tv_mac || "(not set)");
      setTvInput(status.tv_input || "(none)");
      setPaired(Boolean(status.paired));
    } catch (e) {
      console.error("[BazziteLG] Failed to fetch status:", e);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleToggle = async (checked) => {
    setSyncEnabled(checked);
    try {
      const res = await call("set_sync", checked);
      if (res.success) {
        setSyncEnabled(res.sync_enabled);
        toast(res.sync_enabled ? "Auto-sync is ACTIVATED" : "Auto-sync is DEACTIVATED");
      } else {
        toast(res.error || "Could not change auto-sync", "LG TV Control Failed");
        fetchStatus();
      }
    } catch (e) {
      console.error("[BazziteLG] Toggle error:", e);
      fetchStatus();
    }
  };

  const handlePower = async (mode) => {
    setBusy(true);
    toast(`Sending TV ${mode.toUpperCase()} command...`);
    try {
      const res = await call(mode === "on" ? "power_on" : "power_off");
      if (res.success) {
        toast(`TV ${mode.toUpperCase()} command sent successfully`);
      } else {
        toast(res.output || "Error communicating with TV", "LG TV Control Failed");
      }
    } catch (e) {
      toast(String(e), "LG TV Control Error");
    } finally {
      setBusy(false);
    }
  };

  return h("div", { style: { paddingBottom: "20px" } },
    h(PanelSection, { title: "Power Sync" },
      h(PanelSectionRow, null,
        h(ToggleField, {
          label: "Auto Power Sync",
          description: syncEnabled ? "TV turns on/off with PC sleep/wake/boot" : "Sync paused (TV stays in current state)",
          checked: syncEnabled,
          onChange: handleToggle,
        })
      )
    ),
    h(PanelSection, { title: "Quick Power Actions" },
      h(PanelSectionRow, null,
        h(ButtonItem, {
          layout: "below",
          disabled: busy,
          onClick: () => handlePower("on"),
        }, "Turn TV ON (Wake-on-LAN)")
      ),
      h(PanelSectionRow, null,
        h(ButtonItem, {
          layout: "below",
          disabled: busy,
          onClick: () => handlePower("off"),
        }, "Turn TV OFF (Standby)")
      )
    ),
    h(PanelSection, { title: "TV Info" },
      h(PanelSectionRow, null,
        h(Field, { label: "State" }, syncEnabled ? "ACTIVATED" : "DEACTIVATED")
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "TV IP Address" }, tvIp)
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "WoL MAC" }, tvMac)
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "HDMI Input" }, tvInput)
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "Client Key" }, paired ? "Paired" : "Missing key")
      ),
      h(PanelSectionRow, null,
        h(ButtonItem, {
          layout: "below",
          onClick: fetchStatus,
        }, "Refresh Status")
      )
    )
  );
};

var index = definePlugin(() => {
  return {
    name: TITLE,
    titleView: h("div", { className: staticClasses.Title }, TITLE),
    icon: h(TvIcon, null),
    content: h(Content, null),
    onDismount() {},
  };
});

export { index as default };
