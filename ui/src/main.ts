/** MIST UI entry point. */

import { connect } from "./app";
import { mountAgentTabs } from "./components/AgentTabs";
import { mountBrowserPanel } from "./components/BrowserPanel";
import { mountBrokerDashboard } from "./components/BrokerDashboard";
import { mountChatPanel } from "./components/ChatPanel";
import { mountEditorPanel } from "./components/EditorPanel";
import { mountErrorPopup } from "./components/ErrorPopup";
import { mountSettingsPanel } from "./components/SettingsPanel";
import { mountStatusBar } from "./components/StatusBar";

// Mount components to DOM elements
const tabs = document.getElementById("agent-tabs")!;
const panel = document.getElementById("panel-container")!;
const status = document.getElementById("status-bar")!;
const errorPopup = document.getElementById("error-popup")!;

mountAgentTabs(tabs);
mountChatPanel(panel);
mountBrowserPanel(panel);
mountEditorPanel(panel);
mountSettingsPanel(panel);
mountBrokerDashboard(panel);
mountStatusBar(status);
mountErrorPopup(errorPopup);

// Connect to broker WebSocket
connect();
