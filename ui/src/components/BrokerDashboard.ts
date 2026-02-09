/** Broker dashboard — connection stats and agent status. */

import { store, type State } from "../store";

export function mountBrokerDashboard(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  if (state.activePanel !== "dashboard") return;

  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "dashboard-panel";

  const heading = document.createElement("h2");
  heading.textContent = "Broker Dashboard";
  wrapper.appendChild(heading);

  // Connection status
  const status = document.createElement("div");
  status.className = "dashboard-status";
  status.innerHTML = `
    <p><strong>Connection:</strong> ${state.connected ? "Active" : "Disconnected"}</p>
    <p><strong>Agents:</strong> ${state.agents.length}</p>
    <p><strong>Messages sent:</strong> ${state.chat.length}</p>
  `;
  wrapper.appendChild(status);

  // Agent list
  if (state.agents.length > 0) {
    const agentSection = document.createElement("div");
    agentSection.className = "dashboard-agents";

    const agentHeading = document.createElement("h3");
    agentHeading.textContent = "Registered Agents";
    agentSection.appendChild(agentHeading);

    const ul = document.createElement("ul");
    for (const agent of state.agents) {
      const li = document.createElement("li");
      li.textContent = `${agent.name} (${agent.agent_id}) — ${agent.commands.length} commands`;
      ul.appendChild(li);
    }
    agentSection.appendChild(ul);
    wrapper.appendChild(agentSection);
  }

  container.appendChild(wrapper);
}
