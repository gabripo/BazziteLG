import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField, staticClasses } from "@decky/ui";
import { call, definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";

const TITLE = "LG TV Control";

interface Status {
  sync_enabled: boolean;
  status_text: string;
  tv_ip: string;
  tv_mac: string;
  tv_input: string;
  paired: boolean;
}

interface SyncResult {
  success: boolean;
  sync_enabled?: boolean;
  error?: string;
}

interface CommandResult {
  success: boolean;
  output: string;
}

const toast = (body: string, title: string = TITLE) => toaster.toast({ title, body });

const TvIcon = () => (
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

const Content = () => {
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [tvIp, setTvIp] = useState("");
  const [tvMac, setTvMac] = useState("");
  const [tvInput, setTvInput] = useState("");
  const [paired, setPaired] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetchStatus = async () => {
    try {
      const status = await call<[], Status>("get_status");
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

  const handleToggle = async (checked: boolean) => {
    setSyncEnabled(checked);
    try {
      const res = await call<[boolean], SyncResult>("set_sync", checked);
      if (res.success) {
        setSyncEnabled(Boolean(res.sync_enabled));
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

  const handlePower = async (mode: "on" | "off") => {
    setBusy(true);
    toast(`Sending TV ${mode.toUpperCase()} command...`);
    try {
      const res = await call<[], CommandResult>(mode === "on" ? "power_on" : "power_off");
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
          <ButtonItem layout="below" disabled={busy} onClick={() => handlePower("on")}>
            Turn TV ON (Wake-on-LAN)
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => handlePower("off")}>
            Turn TV OFF (Standby)
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="TV Info">
        <PanelSectionRow>
          <Field label="State">{syncEnabled ? "ACTIVATED" : "DEACTIVATED"}</Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="TV IP Address">{tvIp}</Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="WoL MAC">{tvMac}</Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="HDMI Input">{tvInput}</Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Client Key">{paired ? "Paired" : "Missing key"}</Field>
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

export default definePlugin(() => ({
  name: TITLE,
  titleView: <div className={staticClasses.Title}>{TITLE}</div>,
  icon: <TvIcon />,
  content: <Content />,
  onDismount() {},
}));
