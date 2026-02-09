/** Chat panel — renders text/confirm responses, input field. */

import { sendCommand } from "../app";
import {
  RESP_CONFIRM,
  RESP_ERROR,
  RESP_LIST,
  RESP_PROGRESS,
  RESP_TABLE,
  RESP_TEXT,
  type ConfirmContent,
  type ErrorContent,
  type ListContent,
  type ProgressContent,
  type ResponsePayload,
  type TableContent,
  type TextContent,
} from "../protocol";
import { store, type ChatEntry, type State } from "../store";

export function mountChatPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  // Only render if active panel is "chat"
  if (state.activePanel !== "chat") {
    container.innerHTML = "";
    return;
  }

  // Build once, then update
  let log = container.querySelector<HTMLElement>(".chat-log");
  let form = container.querySelector<HTMLFormElement>(".chat-form");

  if (!log) {
    container.innerHTML = "";
    log = el("div", "chat-log");
    form = document.createElement("form");
    form.className = "chat-form";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "chat-input";
    input.placeholder = state.connected ? "Type a command..." : "Disconnected";
    input.disabled = !state.connected;
    input.autocomplete = "off";

    form.appendChild(input);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || !state.activeAgent) return;
      sendCommand(state.activeAgent, text);
      input.value = "";
    });

    container.appendChild(log);
    container.appendChild(form);
  }

  // Update input state
  const input = form!.querySelector<HTMLInputElement>(".chat-input")!;
  input.disabled = !state.connected;
  input.placeholder = state.connected ? "Type a command..." : "Disconnected";

  // Show all chat entries — commands route through admin regardless of tab
  renderEntries(log, state.chat);
}

function renderEntries(log: HTMLElement, entries: ChatEntry[]): void {
  // Clear and re-render (simple approach — good enough for chat)
  log.innerHTML = "";
  for (const entry of entries) {
    const row = el("div", "chat-entry");

    // Command
    const cmd = el("div", "chat-command");
    cmd.textContent = `> ${entry.command}`;
    row.appendChild(cmd);

    // Response
    if (entry.response) {
      const resp = renderResponse(entry.response);
      row.appendChild(resp);
    } else {
      const pending = el("div", "chat-pending");
      pending.textContent = "...";
      row.appendChild(pending);
    }

    log.appendChild(row);
  }

  // Auto-scroll
  log.scrollTop = log.scrollHeight;
}

function renderResponse(resp: ResponsePayload): HTMLElement {
  switch (resp.type) {
    case RESP_TEXT:
      return renderText(resp.content as TextContent);
    case RESP_TABLE:
      return renderTable(resp.content as TableContent);
    case RESP_LIST:
      return renderList(resp.content as ListContent);
    case RESP_CONFIRM:
      return renderConfirm(resp.content as ConfirmContent);
    case RESP_PROGRESS:
      return renderProgress(resp.content as ProgressContent);
    case RESP_ERROR:
      return renderError(resp.content as ErrorContent);
    default:
      return renderGeneric(resp);
  }
}

function renderText(content: TextContent): HTMLElement {
  const div = el("div", "chat-response chat-text");
  if (content.format === "markdown") {
    // Simple markdown: bold, italic, code, links
    div.innerHTML = simpleMarkdown(content.text);
  } else {
    div.textContent = content.text;
  }
  return div;
}

function renderTable(content: TableContent): HTMLElement {
  const div = el("div", "chat-response chat-table");
  if (content.title) {
    const title = el("div", "chat-table-title");
    title.textContent = content.title;
    div.appendChild(title);
  }
  const table = document.createElement("table");
  table.className = "chat-table-grid";
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const col of content.columns) {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of content.rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell != null ? String(cell) : "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  div.appendChild(table);
  return div;
}

function renderList(content: ListContent): HTMLElement {
  const div = el("div", "chat-response chat-list");
  if (content.title) {
    const title = el("div", "chat-list-title");
    title.textContent = content.title;
    div.appendChild(title);
  }
  const ul = document.createElement("ul");
  for (const item of content.items) {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  }
  div.appendChild(ul);
  return div;
}

function renderConfirm(content: ConfirmContent): HTMLElement {
  const div = el("div", "chat-response chat-confirm");
  const prompt = el("p", "confirm-prompt");
  prompt.textContent = content.prompt;
  div.appendChild(prompt);
  for (const opt of content.options) {
    const btn = el("button", "confirm-option") as HTMLButtonElement;
    btn.textContent = opt;
    div.appendChild(btn);
  }
  return div;
}

function renderProgress(content: ProgressContent): HTMLElement {
  const div = el("div", "chat-response chat-progress");
  div.textContent = content.message;
  if (content.percent != null) {
    const bar = el("div", "progress-bar");
    const fill = el("div", "progress-fill");
    fill.style.width = `${content.percent}%`;
    bar.appendChild(fill);
    div.appendChild(bar);
  }
  return div;
}

function renderError(content: ErrorContent): HTMLElement {
  const div = el("div", "chat-response chat-error");
  div.textContent = content.message;
  return div;
}

function renderGeneric(resp: ResponsePayload): HTMLElement {
  const div = el("div", "chat-response chat-generic");
  div.textContent = `[${resp.type} response]`;
  return div;
}

function simpleMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
