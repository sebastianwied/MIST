/** WebSocket connection and message routing. */

import {
  createMessage,
  MSG_AGENT_CATALOG,
  MSG_AGENT_LIST,
  MSG_COMMAND,
  MSG_ERROR,
  MSG_RESPONSE,
  type AgentManifest,
  type Message,
  type ResponsePayload,
} from "./protocol";
import { store, type ChatEntry } from "./store";

const UI_ID = "ui";
const WS_URL = "ws://127.0.0.1:8765";
const RECONNECT_DELAY = 3000;

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connect(): void {
  if (ws && ws.readyState <= WebSocket.OPEN) return;

  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    store.setConnected(true);
    store.setError(null);
    requestCatalog();
  });

  ws.addEventListener("message", (event) => {
    try {
      const msg: Message = JSON.parse(event.data as string);
      handleMessage(msg);
    } catch {
      console.error("Failed to parse message:", event.data);
    }
  });

  ws.addEventListener("close", () => {
    store.setConnected(false);
    ws = null;
    scheduleReconnect();
  });

  ws.addEventListener("error", () => {
    store.setError("Connection failed");
  });
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY);
}

function send(msg: Message): void {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    store.setError("Not connected");
    return;
  }
  ws.send(JSON.stringify(msg));
}

function requestCatalog(): void {
  const msg = createMessage(MSG_AGENT_LIST, UI_ID, "broker", {});
  send(msg);
}

export function sendCommand(agentId: string, text: string): string {
  // Parse "command arg1 arg2" into command + text
  const parts = text.trim().split(/\s+/);
  const command = parts[0] || "";
  const rest = parts.slice(1).join(" ");

  const payload: Record<string, unknown> = {
    command,
    args: {},
    text: rest,
  };

  const msg = createMessage(MSG_COMMAND, UI_ID, agentId, payload);
  send(msg);

  // Add pending entry to chat
  const entry: ChatEntry = {
    id: msg.id,
    command: text,
    response: null,
    timestamp: msg.timestamp!,
    agentId,
  };
  store.addCommand(entry);

  return msg.id;
}

function handleMessage(msg: Message): void {
  switch (msg.type) {
    case MSG_AGENT_CATALOG:
      handleCatalog(msg);
      break;
    case MSG_RESPONSE:
      handleResponse(msg);
      break;
    case MSG_ERROR:
      handleError(msg);
      break;
    default:
      console.log("Unhandled message type:", msg.type, msg);
  }
}

function handleCatalog(msg: Message): void {
  const agents = (msg.payload.agents ?? []) as AgentManifest[];
  store.setCatalog(agents);
}

function handleResponse(msg: Message): void {
  const payload = msg.payload as unknown as ResponsePayload;
  if (msg.reply_to) {
    store.setResponse(msg.reply_to, payload);
  }
}

function handleError(msg: Message): void {
  const error = (msg.payload.error as string) ?? "Unknown error";
  if (msg.reply_to) {
    store.setResponse(msg.reply_to, {
      type: "error",
      content: { message: error },
    });
  } else {
    store.setError(error);
  }
}
