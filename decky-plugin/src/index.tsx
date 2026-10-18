import {
  definePlugin,
  ServerAPI,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  ButtonItem,
  Field,
} from "decky-frontend-lib";
import { useState, useEffect, VFC } from "react";

interface StatusResponse {
  sync_enabled: boolean;
  status_text: string;
  tv_ip: string;
  tv_mac: string;
  tv_input: string;
  paired: boolean;
}

const TvIcon: VFC = () => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    width="1em"
    height="1em"
    style={{ display: "inline-block", verticalAlign: "middle" }}
  >
    <path d="M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z" />
  </svg>
);

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
  const [syncEnabled, setSyncEnabled] = useState<boolean>(true);
  const [tvIp, setTvIp] = useState<string>("");
  const [tvMac, setTvMac] = useState<string>("");
  const [tvInput, setTvInput] = useState<string>("");
  const [paired, setPaired] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);

  const fetchStatus = async () => {
    try {
      const res = await serverAPI.callPluginMethod<{}, StatusResponse>("get_status", {});
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

  const handleToggle = async (checked: boolean) => {
    setSyncEnabled(checked);
    try {
      const res = await serverAPI.callPluginMethod<{ enabled: boolean }, { success: boolean; sync_enabled: boolean }>(
        "set_sync",
        { enabled: checked }
      );
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

  const handlePower = async (mode: "on" | "off") => {
    setBusy(true);
    serverAPI.toaster.toast({
      title: "LG TV Control",
      body: `Sending TV ${mode.toUpperCase()} command...`,
    });
    try {
      const res = await serverAPI.callPluginMethod<{}, { success: boolean; output: string }>(
        mode === "on" ? "power_on" : "power_off",
        {}
      );
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

  return (
    <div style={{ paddingBottom: "20px" }}>
      <PanelSection title="Power Sync">
        <PanelSectionRow>
          <ToggleField
            label="Auto Power Sync"
            description={syncEnabled ? "TV turns on/off with PC sleep/wake/boot" : "Sync paused (TV stays in current state)"}
            checked={syncEnabled}
            onChange={handleToggle}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Quick Power Actions">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => handlePower("on")}
          >
            Turn TV ON (Wake-on-LAN)
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => handlePower("off")}
          >
            Turn TV OFF (Standby)
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="TV Info">
        <PanelSectionRow>
          <Field label="State" value={syncEnabled ? "ACTIVATED" : "DEACTIVATED"} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="TV IP Address" value={tvIp} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="WoL MAC" value={tvMac} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="HDMI Input" value={tvInput} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Client Key" value={paired ? "Paired" : "Missing key"} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={fetchStatus}>
            Refresh Status
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </div>
  );
};

export default definePlugin((serverAPI: ServerAPI) => {
  return {
    title: "LG TV Control",
    name: "LG TV Control",
    icon: <TvIcon />,
    content: <Content serverAPI={serverAPI} />,
    onDismount() {},
  };
});
