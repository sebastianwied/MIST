/** MIST protocol v2 — mirrors core/src/mist_core/protocol.py */

// Message type constants
export const MSG_AGENT_REGISTER = "agent.register";
export const MSG_AGENT_READY = "agent.ready";
export const MSG_AGENT_DISCONNECT = "agent.disconnect";
export const MSG_AGENT_LIST = "agent.list";
export const MSG_AGENT_CATALOG = "agent.catalog";

export const MSG_COMMAND = "command";
export const MSG_RESPONSE = "response";

export const MSG_SERVICE_REQUEST = "service.request";
export const MSG_SERVICE_RESPONSE = "service.response";
export const MSG_SERVICE_ERROR = "service.error";

export const MSG_AGENT_MESSAGE = "agent.message";
export const MSG_AGENT_BROADCAST = "agent.broadcast";
export const MSG_ERROR = "error";

// Response type constants
export const RESP_TEXT = "text";
export const RESP_TABLE = "table";
export const RESP_LIST = "list";
export const RESP_EDITOR = "editor";
export const RESP_CONFIRM = "confirm";
export const RESP_PROGRESS = "progress";
export const RESP_ERROR = "error";

// Message envelope
export interface Message {
  type: string;
  id: string;
  from: string;
  to: string;
  payload: Record<string, unknown>;
  reply_to?: string;
  timestamp?: string;
}

// Response payload types
export interface TextContent {
  text: string;
  format: "plain" | "markdown";
}

export interface TableContent {
  columns: string[];
  rows: (string | number | null)[][];
  title?: string;
}

export interface ListContent {
  items: string[];
  title?: string;
}

export interface EditorContent {
  content: string;
  title: string;
  path?: string;
  read_only?: boolean;
}

export interface ConfirmContent {
  prompt: string;
  options: string[];
  context?: string;
}

export interface ProgressContent {
  message: string;
  percent?: number;
}

export interface ErrorContent {
  message: string;
  code?: string;
  details?: string;
}

export interface TopicDetailContent {
  slug: string;
  name: string;
  synthesis: string;
  notes: string[];
  buffer_count: number;
}

// Structured response payload
export interface ResponsePayload {
  type: string;
  content: TextContent | TableContent | ListContent | EditorContent | ConfirmContent | ProgressContent | ErrorContent | TopicDetailContent;
}

// Agent manifest (from catalog)
export interface AgentManifest {
  agent_id: string;
  name: string;
  description: string;
  commands: { name: string; description: string; args?: Record<string, unknown> }[];
  panels: { id: string; label: string; type: string; default?: boolean }[];
}

// Helpers
export function createMessage(
  type: string,
  from: string,
  to: string,
  payload: Record<string, unknown>,
  replyTo?: string,
): Message {
  return {
    type,
    id: crypto.randomUUID().replace(/-/g, ""),
    from,
    to,
    payload,
    ...(replyTo ? { reply_to: replyTo } : {}),
    timestamp: new Date().toISOString(),
  };
}
