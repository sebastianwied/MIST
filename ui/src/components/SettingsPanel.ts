/** Settings panel — placeholder for settings and personality editor. */

import { store, type State } from "../store";

export function mountSettingsPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  // Settings is a special panel accessible via admin agent
  if (state.activePanel !== "settings") return;

  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "settings-panel";

  const heading = document.createElement("h2");
  heading.textContent = "Settings";
  wrapper.appendChild(heading);

  const info = document.createElement("p");
  info.className = "settings-info";
  info.textContent = "Use 'settings' and 'set <key> <value>' commands in chat to manage settings.";
  wrapper.appendChild(info);

  container.appendChild(wrapper);
}
