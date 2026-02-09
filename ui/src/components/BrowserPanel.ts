/** Browser panel — renders table/list responses in a two-pane layout. */

import {
  RESP_LIST,
  RESP_TABLE,
  type ListContent,
  type ResponsePayload,
  type TableContent,
} from "../protocol";
import { store, type ChatEntry, type State } from "../store";

export function mountBrowserPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  const agent = state.agents.find((a) => a.agent_id === state.activeAgent);
  const panel = agent?.panels.find((p) => p.id === state.activePanel);
  if (!panel || panel.type !== "browser") {
    // Don't clear — other panels handle this
    return;
  }

  container.innerHTML = "";
  const wrapper = el("div", "browser-panel");

  // Find the latest table or list response for this agent
  const entries = state.chat
    .filter((e) => e.agentId === state.activeAgent && e.response)
    .filter(
      (e) =>
        e.response!.type === RESP_TABLE || e.response!.type === RESP_LIST,
    );

  const latest = entries[entries.length - 1];
  if (!latest || !latest.response) {
    wrapper.innerHTML = '<p class="browser-empty">No data yet.</p>';
    container.appendChild(wrapper);
    return;
  }

  if (latest.response.type === RESP_TABLE) {
    renderTable(wrapper, latest.response.content as TableContent);
  } else if (latest.response.type === RESP_LIST) {
    renderList(wrapper, latest.response.content as ListContent);
  }

  container.appendChild(wrapper);
}

function renderTable(parent: HTMLElement, content: TableContent): void {
  if (content.title) {
    const h = el("h3", "browser-title");
    h.textContent = content.title;
    parent.appendChild(h);
  }

  const table = document.createElement("table");
  table.className = "browser-table";

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

  parent.appendChild(table);
}

function renderList(parent: HTMLElement, content: ListContent): void {
  if (content.title) {
    const h = el("h3", "browser-title");
    h.textContent = content.title;
    parent.appendChild(h);
  }

  const ul = document.createElement("ul");
  ul.className = "browser-list";
  for (const item of content.items) {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  }
  parent.appendChild(ul);
}

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
