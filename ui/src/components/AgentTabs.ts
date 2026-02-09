/** Agent tab bar — switches between agents and their panels. */

import { store, type State } from "../store";
import type { AgentManifest } from "../protocol";

export function mountAgentTabs(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  container.innerHTML = "";

  if (!state.connected || state.agents.length === 0) {
    container.classList.add("disconnected");
    container.textContent = state.connected ? "No agents" : "Disconnected";
    return;
  }
  container.classList.remove("disconnected");

  // Agent tabs
  const tabs = el("div", "tabs");
  for (const agent of state.agents) {
    const tab = el("button", "tab");
    tab.textContent = agent.name;
    if (agent.agent_id === state.activeAgent) tab.classList.add("active");
    tab.addEventListener("click", () => store.switchAgent(agent.agent_id));
    tabs.appendChild(tab);
  }
  container.appendChild(tabs);

  // Panel sub-tabs for active agent
  const agent = state.agents.find((a) => a.agent_id === state.activeAgent);
  if (agent && agent.panels.length > 1) {
    const panels = el("div", "panel-tabs");
    for (const panel of agent.panels) {
      const btn = el("button", "panel-tab");
      btn.textContent = panel.label;
      if (panel.id === state.activePanel) btn.classList.add("active");
      btn.addEventListener("click", () =>
        store.update({ activePanel: panel.id }),
      );
      panels.appendChild(btn);
    }
    container.appendChild(panels);
  }
}

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
