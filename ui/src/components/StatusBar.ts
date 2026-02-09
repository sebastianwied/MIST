/** Status bar — connection state and LLM activity. */

import { store, type State } from "../store";

export function mountStatusBar(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  container.innerHTML = "";

  // Connection indicator
  const conn = el("span", state.connected ? "status-connected" : "status-disconnected");
  conn.textContent = state.connected ? "Connected" : "Disconnected";
  container.appendChild(conn);

  // Agent count
  if (state.agents.length > 0) {
    const agents = el("span", "status-agents");
    agents.textContent = `${state.agents.length} agent${state.agents.length !== 1 ? "s" : ""}`;
    container.appendChild(agents);
  }

  // LLM indicator
  if (state.llmActive) {
    const llm = el("span", "status-llm");
    llm.textContent = "LLM active";
    container.appendChild(llm);
  }
}

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
