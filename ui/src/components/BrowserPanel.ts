/** Browser panel — dispatches to topic browser or generic table/list browser. */

import { onResponse, sendStructuredCommand } from "../app";
import type {
  EditorContent,
  ListContent,
  ResponsePayload,
  TableContent,
  TopicDetailContent,
} from "../protocol";
import { store, type State } from "../store";

// ── Mount ────────────────────────────────────────────────

export function mountBrowserPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  const agent = state.agents.find((a) => a.agent_id === state.activeAgent);
  const panel = agent?.panels.find((p) => p.id === state.activePanel);
  if (!panel || panel.type !== "browser") {
    return;
  }

  // Dispatch to the right sub-renderer based on panel id
  if (panel.id === "topics") {
    renderTopicsBrowser(container, state);
  } else {
    renderGenericBrowser(container, state, panel.id, panel.label);
  }
}

// ══════════════════════════════════════════════════════════
// Topics Browser (drill-down: list → detail → editor)
// ══════════════════════════════════════════════════════════

type TopicView = "list" | "detail" | "editor";

let topicViewState: TopicView = "list";
let topicSlug = "";
let topicName = "";
let topicDetailData: TopicDetailContent | null = null;
let topicEditorFile = "";
let topicEditorTitle = "";
let topicEditorContent = "";
let topicEditorDirty = false;
let topicLastPanelKey = "";
let topicItems: string[] = [];

function renderTopicsBrowser(container: HTMLElement, state: State): void {
  const panelKey = `${state.activeAgent}:${state.activePanel}`;
  if (panelKey !== topicLastPanelKey) {
    topicLastPanelKey = panelKey;
    topicViewState = "list";
    topicDetailData = null;
    fetchTopics();
  }

  container.innerHTML = "";
  const wrapper = el("div", "browser-panel");

  switch (topicViewState) {
    case "list":
      renderTopicList(wrapper);
      break;
    case "detail":
      renderTopicDetail(wrapper);
      break;
    case "editor":
      renderTopicEditor(wrapper);
      break;
  }

  container.appendChild(wrapper);
}

function fetchTopics(): void {
  const id = sendStructuredCommand("topics", {});
  onResponse(id, (resp) => {
    if (resp.type === "list") {
      topicItems = (resp.content as ListContent).items;
    }
    store.update({});
  });
}

function renderTopicList(parent: HTMLElement): void {
  const header = el("div", "browser-header");
  const title = el("h3", "browser-title");
  title.textContent = "Topics";
  header.appendChild(title);

  const refreshBtn = el("button", "browser-btn");
  refreshBtn.textContent = "Refresh";
  refreshBtn.addEventListener("click", fetchTopics);
  header.appendChild(refreshBtn);
  parent.appendChild(header);

  if (topicItems.length === 0) {
    const empty = el("p", "browser-empty");
    empty.textContent = "No topics yet. Run 'aggregate' in chat.";
    parent.appendChild(empty);
    return;
  }

  const list = document.createElement("ul");
  list.className = "browser-topic-list";
  for (const item of topicItems) {
    const li = document.createElement("li");
    li.className = "browser-topic-item";
    li.textContent = item;
    const match = item.match(/\]\s+(\S+):/);
    if (match) {
      const slug = match[1];
      li.addEventListener("click", () => openTopic(slug));
    }
    list.appendChild(li);
  }
  parent.appendChild(list);
}

// ── Topic detail ────────────────────────────────────────

function openTopic(slug: string): void {
  topicSlug = slug;
  topicViewState = "detail";
  topicDetailData = null;
  store.update({});

  const id = sendStructuredCommand("topic", { action: "view", slug });
  onResponse(id, (resp) => {
    if (resp.type === "topic_detail") {
      topicDetailData = resp.content as TopicDetailContent;
      topicName = topicDetailData.name;
    }
    store.update({});
  });
}

function renderTopicDetail(parent: HTMLElement): void {
  const header = el("div", "browser-header");
  const backBtn = el("button", "browser-btn");
  backBtn.textContent = "< Topics";
  backBtn.addEventListener("click", () => {
    topicViewState = "list";
    store.update({});
  });
  header.appendChild(backBtn);

  const title = el("h3", "browser-title");
  title.textContent = topicName || topicSlug;
  header.appendChild(title);
  parent.appendChild(header);

  if (!topicDetailData) {
    const loading = el("p", "browser-empty");
    loading.textContent = "Loading...";
    parent.appendChild(loading);
    return;
  }

  // Synthesis section
  const synthSection = el("div", "browser-section");
  const synthHeader = el("div", "browser-section-header");
  const synthTitle = el("h4", "browser-section-title");
  synthTitle.textContent = "Synthesis";
  synthHeader.appendChild(synthTitle);

  const editSynthBtn = el("button", "browser-btn");
  editSynthBtn.textContent = "Edit";
  editSynthBtn.addEventListener("click", () =>
    openTopicEditor(topicSlug, "synthesis", `${topicName} — Synthesis`, topicDetailData?.synthesis ?? ""),
  );
  synthHeader.appendChild(editSynthBtn);
  synthSection.appendChild(synthHeader);

  const synthPreview = el("div", "browser-synthesis-preview");
  if (topicDetailData.synthesis) {
    synthPreview.textContent = topicDetailData.synthesis.slice(0, 500)
      + (topicDetailData.synthesis.length > 500 ? "..." : "");
  } else {
    synthPreview.textContent = "(no synthesis yet — run 'sync')";
    synthPreview.classList.add("browser-empty-text");
  }
  synthSection.appendChild(synthPreview);
  parent.appendChild(synthSection);

  // Buffer count
  if (topicDetailData.buffer_count > 0) {
    const bufInfo = el("p", "browser-buffer-info");
    bufInfo.textContent = `${topicDetailData.buffer_count} unsynced entries in buffer`;
    parent.appendChild(bufInfo);
  }

  // Notes section
  const notesSection = el("div", "browser-section");
  const notesHeader = el("div", "browser-section-header");
  const notesTitle = el("h4", "browser-section-title");
  notesTitle.textContent = `Notes (${topicDetailData.notes.length})`;
  notesHeader.appendChild(notesTitle);
  notesSection.appendChild(notesHeader);

  if (topicDetailData.notes.length === 0) {
    const empty = el("p", "browser-empty-text");
    empty.textContent = "No long-form notes yet.";
    notesSection.appendChild(empty);
  } else {
    const notesList = document.createElement("ul");
    notesList.className = "browser-notes-list";
    for (const filename of topicDetailData.notes) {
      const li = document.createElement("li");
      li.className = "browser-note-item";
      li.textContent = filename;
      li.addEventListener("click", () =>
        loadAndOpenTopicEditor(topicSlug, filename, `${topicName} — ${filename}`),
      );
      notesList.appendChild(li);
    }
    notesSection.appendChild(notesList);
  }
  parent.appendChild(notesSection);
}

// ── Topic editor ────────────────────────────────────────

function openTopicEditor(slug: string, filename: string, title: string, content: string): void {
  topicSlug = slug;
  topicEditorFile = filename;
  topicEditorTitle = title;
  topicEditorContent = content;
  topicEditorDirty = false;
  topicViewState = "editor";
  store.update({});
}

function loadAndOpenTopicEditor(slug: string, filename: string, title: string): void {
  const id = sendStructuredCommand("topic", { action: "read", slug, filename });
  onResponse(id, (resp) => {
    if (resp.type === "editor") {
      const ed = resp.content as EditorContent;
      openTopicEditor(slug, filename, ed.title || title, ed.content);
    }
  });
}

function renderTopicEditor(parent: HTMLElement): void {
  const header = el("div", "browser-header");

  const backBtn = el("button", "browser-btn");
  backBtn.textContent = `< ${topicName || topicSlug}`;
  backBtn.addEventListener("click", () => {
    if (topicEditorDirty && !confirm("Discard unsaved changes?")) return;
    openTopic(topicSlug);
  });
  header.appendChild(backBtn);

  const title = el("span", "browser-editor-title");
  title.textContent = topicEditorTitle;
  header.appendChild(title);

  const saveBtn = el("button", "browser-btn browser-save-btn") as HTMLButtonElement;
  saveBtn.textContent = "Save";
  saveBtn.disabled = !topicEditorDirty;
  saveBtn.addEventListener("click", () => {
    const textarea = parent.querySelector<HTMLTextAreaElement>(".browser-editor-textarea");
    if (!textarea) return;
    const content = textarea.value;

    const id = sendStructuredCommand("topic", {
      action: "write",
      slug: topicSlug,
      filename: topicEditorFile,
      content,
    });
    onResponse(id, () => {
      topicEditorDirty = false;
      topicEditorContent = content;
      const detailId = sendStructuredCommand("topic", { action: "view", slug: topicSlug });
      onResponse(detailId, (resp) => {
        if (resp.type === "topic_detail") {
          topicDetailData = resp.content as TopicDetailContent;
        }
      });
      store.update({});
    });
  });
  header.appendChild(saveBtn);
  parent.appendChild(header);

  const textarea = document.createElement("textarea");
  textarea.className = "browser-editor-textarea";
  textarea.value = topicEditorContent;
  textarea.spellcheck = false;
  textarea.addEventListener("input", () => {
    topicEditorDirty = true;
    const btn = parent.querySelector<HTMLButtonElement>(".browser-save-btn");
    if (btn) btn.disabled = false;
  });
  parent.appendChild(textarea);
}

// ══════════════════════════════════════════════════════════
// Generic Browser (table/list from a fetch command)
// ══════════════════════════════════════════════════════════

// Map panel id → command to fetch data
const PANEL_COMMANDS: Record<string, string> = {
  library: "articles",
};

// Per-panel cached response
const genericData = new Map<string, ResponsePayload>();
let genericLastPanelKey = "";

function renderGenericBrowser(
  container: HTMLElement,
  state: State,
  panelId: string,
  panelLabel: string,
): void {
  const panelKey = `${state.activeAgent}:${state.activePanel}`;
  if (panelKey !== genericLastPanelKey) {
    genericLastPanelKey = panelKey;
    fetchGenericData(panelId);
  }

  container.innerHTML = "";
  const wrapper = el("div", "browser-panel");

  // Header
  const header = el("div", "browser-header");
  const title = el("h3", "browser-title");
  title.textContent = panelLabel;
  header.appendChild(title);

  const refreshBtn = el("button", "browser-btn");
  refreshBtn.textContent = "Refresh";
  refreshBtn.addEventListener("click", () => fetchGenericData(panelId));
  header.appendChild(refreshBtn);
  wrapper.appendChild(header);

  const data = genericData.get(panelId);
  if (!data) {
    const loading = el("p", "browser-empty");
    loading.textContent = "Loading...";
    wrapper.appendChild(loading);
  } else if (data.type === "table") {
    renderGenericTable(wrapper, data.content as TableContent);
  } else if (data.type === "list") {
    renderGenericList(wrapper, data.content as ListContent);
  } else if (data.type === "text") {
    const text = el("p", "browser-empty");
    text.textContent = (data.content as { text: string }).text;
    wrapper.appendChild(text);
  } else if (data.type === "error") {
    const err = el("p", "browser-empty");
    err.textContent = (data.content as { message: string }).message;
    err.style.color = "var(--error)";
    wrapper.appendChild(err);
  } else {
    const empty = el("p", "browser-empty");
    empty.textContent = "No data.";
    wrapper.appendChild(empty);
  }

  container.appendChild(wrapper);
}

function fetchGenericData(panelId: string): void {
  const command = PANEL_COMMANDS[panelId];
  if (!command) return;

  const id = sendStructuredCommand(command, {});
  onResponse(id, (resp) => {
    genericData.set(panelId, resp);
    store.update({});
  });
}

function renderGenericTable(parent: HTMLElement, content: TableContent): void {
  if (content.title) {
    const t = el("p", "chat-table-title");
    t.textContent = content.title;
    parent.appendChild(t);
  }

  const table = document.createElement("table");
  table.className = "browser-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const col of content.columns) {
    const th = document.createElement("th");
    th.textContent = col;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
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

function renderGenericList(parent: HTMLElement, content: ListContent): void {
  if (content.title) {
    const t = el("p", "chat-list-title");
    t.textContent = content.title;
    parent.appendChild(t);
  }

  if (content.items.length === 0) {
    const empty = el("p", "browser-empty");
    empty.textContent = "No items.";
    parent.appendChild(empty);
    return;
  }

  const list = document.createElement("ul");
  list.className = "browser-list";
  for (const item of content.items) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
  parent.appendChild(list);
}

// ── Helpers ─────────────────────────────────────────────

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
