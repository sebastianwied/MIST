/** Browser panel — interactive topic browser with drill-down and editing. */

import { onResponse, sendStructuredCommand } from "../app";
import type {
  EditorContent,
  ListContent,
  ResponsePayload,
  TopicDetailContent,
} from "../protocol";
import { store, type State } from "../store";

// Internal navigation state
type View = "list" | "detail" | "editor";

let currentView: View = "list";
let currentSlug = "";
let currentName = "";
let detailData: TopicDetailContent | null = null;
let editorFile = "";
let editorTitle = "";
let editorContent = "";
let editorDirty = false;
let lastPanelKey = "";

export function mountBrowserPanel(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  const agent = state.agents.find((a) => a.agent_id === state.activeAgent);
  const panel = agent?.panels.find((p) => p.id === state.activePanel);
  if (!panel || panel.type !== "browser") {
    return;
  }

  // Reset to list view when switching panels
  const panelKey = `${state.activeAgent}:${state.activePanel}`;
  if (panelKey !== lastPanelKey) {
    lastPanelKey = panelKey;
    currentView = "list";
    detailData = null;
    fetchTopics();
  }

  container.innerHTML = "";
  const wrapper = el("div", "browser-panel");

  switch (currentView) {
    case "list":
      renderTopicList(wrapper, state);
      break;
    case "detail":
      renderTopicDetail(wrapper);
      break;
    case "editor":
      renderEditor(wrapper);
      break;
  }

  container.appendChild(wrapper);
}

// ── Topic list ──────────────────────────────────────────

let topicItems: string[] = [];

function fetchTopics(): void {
  const id = sendStructuredCommand("topics", {});
  onResponse(id, (resp) => {
    if (resp.type === "list") {
      topicItems = (resp.content as ListContent).items;
    }
    // Re-render
    store.update({});
  });
}

function renderTopicList(parent: HTMLElement, state: State): void {
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
    // Extract slug from "[id] slug: name"
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
  currentSlug = slug;
  currentView = "detail";
  detailData = null;
  store.update({});

  const id = sendStructuredCommand("topic", { action: "view", slug });
  onResponse(id, (resp) => {
    if (resp.type === "topic_detail") {
      detailData = resp.content as TopicDetailContent;
      currentName = detailData.name;
    }
    store.update({});
  });
}

function renderTopicDetail(parent: HTMLElement): void {
  // Back button
  const header = el("div", "browser-header");
  const backBtn = el("button", "browser-btn");
  backBtn.textContent = "< Topics";
  backBtn.addEventListener("click", () => {
    currentView = "list";
    store.update({});
  });
  header.appendChild(backBtn);

  const title = el("h3", "browser-title");
  title.textContent = currentName || currentSlug;
  header.appendChild(title);
  parent.appendChild(header);

  if (!detailData) {
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
    openEditor(currentSlug, "synthesis", `${currentName} — Synthesis`, detailData?.synthesis ?? ""),
  );
  synthHeader.appendChild(editSynthBtn);
  synthSection.appendChild(synthHeader);

  const synthPreview = el("div", "browser-synthesis-preview");
  if (detailData.synthesis) {
    synthPreview.textContent = detailData.synthesis.slice(0, 500)
      + (detailData.synthesis.length > 500 ? "..." : "");
  } else {
    synthPreview.textContent = "(no synthesis yet — run 'sync')";
    synthPreview.classList.add("browser-empty-text");
  }
  synthSection.appendChild(synthPreview);
  parent.appendChild(synthSection);

  // Buffer count
  if (detailData.buffer_count > 0) {
    const bufInfo = el("p", "browser-buffer-info");
    bufInfo.textContent = `${detailData.buffer_count} unsynced entries in buffer`;
    parent.appendChild(bufInfo);
  }

  // Notes section
  const notesSection = el("div", "browser-section");
  const notesHeader = el("div", "browser-section-header");
  const notesTitle = el("h4", "browser-section-title");
  notesTitle.textContent = `Notes (${detailData.notes.length})`;
  notesHeader.appendChild(notesTitle);
  notesSection.appendChild(notesHeader);

  if (detailData.notes.length === 0) {
    const empty = el("p", "browser-empty-text");
    empty.textContent = "No long-form notes yet.";
    notesSection.appendChild(empty);
  } else {
    const notesList = document.createElement("ul");
    notesList.className = "browser-notes-list";
    for (const filename of detailData.notes) {
      const li = document.createElement("li");
      li.className = "browser-note-item";
      li.textContent = filename;
      li.addEventListener("click", () =>
        loadAndOpenEditor(currentSlug, filename, `${currentName} — ${filename}`),
      );
      notesList.appendChild(li);
    }
    notesSection.appendChild(notesList);
  }
  parent.appendChild(notesSection);
}

// ── Editor ──────────────────────────────────────────────

function openEditor(slug: string, filename: string, title: string, content: string): void {
  currentSlug = slug;
  editorFile = filename;
  editorTitle = title;
  editorContent = content;
  editorDirty = false;
  currentView = "editor";
  store.update({});
}

function loadAndOpenEditor(slug: string, filename: string, title: string): void {
  const id = sendStructuredCommand("topic", { action: "read", slug, filename });
  onResponse(id, (resp) => {
    if (resp.type === "editor") {
      const ed = resp.content as EditorContent;
      openEditor(slug, filename, ed.title || title, ed.content);
    }
  });
}

function renderEditor(parent: HTMLElement): void {
  // Header with back and save
  const header = el("div", "browser-header");

  const backBtn = el("button", "browser-btn");
  backBtn.textContent = `< ${currentName || currentSlug}`;
  backBtn.addEventListener("click", () => {
    if (editorDirty && !confirm("Discard unsaved changes?")) return;
    openTopic(currentSlug);
  });
  header.appendChild(backBtn);

  const title = el("span", "browser-editor-title");
  title.textContent = editorTitle;
  header.appendChild(title);

  const saveBtn = el("button", "browser-btn browser-save-btn") as HTMLButtonElement;
  saveBtn.textContent = "Save";
  saveBtn.disabled = !editorDirty;
  saveBtn.addEventListener("click", () => {
    const textarea = parent.querySelector<HTMLTextAreaElement>(".browser-editor-textarea");
    if (!textarea) return;
    const content = textarea.value;

    const id = sendStructuredCommand("topic", {
      action: "write",
      slug: currentSlug,
      filename: editorFile,
      content,
    });
    onResponse(id, () => {
      editorDirty = false;
      editorContent = content;
      // Refresh detail data after save
      const detailId = sendStructuredCommand("topic", { action: "view", slug: currentSlug });
      onResponse(detailId, (resp) => {
        if (resp.type === "topic_detail") {
          detailData = resp.content as TopicDetailContent;
        }
      });
      store.update({});
    });
  });
  header.appendChild(saveBtn);
  parent.appendChild(header);

  // Textarea editor
  const textarea = document.createElement("textarea");
  textarea.className = "browser-editor-textarea";
  textarea.value = editorContent;
  textarea.spellcheck = false;
  textarea.addEventListener("input", () => {
    editorDirty = true;
    // Update save button state
    const btn = parent.querySelector<HTMLButtonElement>(".browser-save-btn");
    if (btn) btn.disabled = false;
  });
  parent.appendChild(textarea);
}

// ── Helpers ─────────────────────────────────────────────

function el(tag: string, className: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}
