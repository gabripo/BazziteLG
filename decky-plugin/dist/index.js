import { definePlugin, PanelSection, PanelSectionRow, ToggleField, ButtonItem, Field } from "decky-frontend-lib";
import { useState, useEffect, createElement as h } from "react";

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

const Content = ({ serverAPI }) => {
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [tvIp, setTvIp] = useState("");
  const [tvMac, setTvMac] = useState("");
  const [tvInput, setTvInput] = useState("");
  const [paired, setPaired] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await serverAPI.callPluginMethod("get_status", {});
      if (res.success && res.result) {
        setSyncEnabled(Boolean(res.result.sync_enabled));
        setTvIp(res.result.tv_ip || "(not set)");
        setTvMac(res.result.tv_mac || "(not set)");
        setTvInput(res.result.tv_input || "(none)");
        setPaired(Boolean(res.result.paired));
      }
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
      const res = await serverAPI.callPluginMethod("set_sync", { enabled: checked });
      if (res.success && res.result) {
        setSyncEnabled(res.result.sync_enabled);
        serverAPI.toaster.toast({
          title: "LG TV Control",
          body: res.result.sync_enabled ? "Auto-sync is ACTIVATED" : "Auto-sync is DEACTIVATED",
        });
      } else {
        fetchStatus();
      }
    } catch (e) {
      console.error("[BazziteLG] Toggle error:", e);
      fetchStatus();
    }
  };

  const handlePower = async (mode) => {
    setBusy(true);
    serverAPI.toaster.toast({
      title: "LG TV Control",
      body: `Sending TV ${mode.toUpperCase()} command...`,
    });
    try {
      const res = await serverAPI.callPluginMethod(mode === "on" ? "power_on" : "power_off", {});
      setBusy(false);
      if (res.success) {
        serverAPI.toaster.toast({
          title: "LG TV Control",
          body: `TV ${mode.toUpperCase()} command sent successfully`,
        });
      } else {
        serverAPI.toaster.toast({
          title: "LG TV Control Failed",
          body: (res.result && res.result.output) || "Error communicating with TV",
        });
      }
    } catch (e) {
      setBusy(false);
      serverAPI.toaster.toast({
        title: "LG TV Control Error",
        body: String(e),
      });
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
        h(Field, { label: "State", value: syncEnabled ? "ACTIVATED" : "DEACTIVATED" })
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "TV IP Address", value: tvIp })
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "WoL MAC", value: tvMac })
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "HDMI Input", value: tvInput })
      ),
      h(PanelSectionRow, null,
        h(Field, { label: "Client Key", value: paired ? "Paired" : "Missing key" })
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

export default definePlugin((serverAPI) => {
  return {
    title: "LG TV Control",
    name: "LG TV Control",
    icon: h(TvIcon, null),
    content: h(Content, { serverAPI }),
    onDismount() {},
  };
});
