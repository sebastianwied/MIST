/** Editor panel — renders markdown content with optional editing. */

import { RESP_EDITOR, type EditorContent, type ResponsePayload } from "../protocol";
import { store, type State } from "../store";

export function mountEditorPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  const agent = state.agents.find((a) => a.agent_id === state.activeAgent);
  const panel = agent?.panels.find((p) => p.id === state.activePanel);
  if (!panel || panel.type !== "editor") return;

  container.innerHTML = "";
  const wrapper = el("div", "editor-panel");

  // Find the latest editor response for this agent
  const entries = state.chat
    .filter((e) => e.agentId === state.activeAgent && e.response)
    .filter((e) => e.response!.type === RESP_EDITOR);

  const latest = entries[entries.length - 1];
  if (!latest || !latest.response) {
    wrapper.innerHTML = '<p class="editor-empty">No document open.</p>';
    container.appendChild(wrapper);
    return;
  }

  const content = latest.response.content as EditorContent;

  // Title bar
  const titleBar = el("div", "editor-title-bar");
  const title = el("span", "editor-title");
  title.textContent = content.title;
  titleBar.appendChild(title);
  if (content.read_only) {
    const badge = el("span", "editor-badge");
    badge.textContent = "read-only";
    titleBar.appendChild(badge);
  }
  wrapper.appendChild(titleBar);

  // Content area
  const textarea = document.createElement("textarea");
  textarea.className = "editor-content";
  textarea.value = content.content;
  textarea.readOnly = content.read_only ?? false;
  textarea.spellcheck = false;
  wrapper.appendChild(textarea);

  container.appendChild(wrapper);
}

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
