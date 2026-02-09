/** Reactive state store for MIST UI. */

import type { AgentManifest, Message, ResponsePayload } from "./protocol";

// Chat entry — a command + its response
export interface ChatEntry {
  id: string;
  command: string;
  response: ResponsePayload | null;
  timestamp: string;
  agentId: string;
}

export interface State {
  connected: boolean;
  agents: AgentManifest[];
  activeAgent: string | null;
  activePanel: string | null;
  chat: ChatEntry[];
  llmActive: boolean;
  error: string | null;
}

type Listener = (state: State) => void;

class Store {
  private state: State = {
    connected: false,
    agents: [],
    activeAgent: null,
    activePanel: null,
    chat: [],
    llmActive: false,
    error: null,
  };

  private listeners: Set<Listener> = new Set();

  get(): State {
    return this.state;
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.state);
    return () => this.listeners.delete(fn);
  }

  update(partial: Partial<State>): void {
    this.state = { ...this.state, ...partial };
    for (const fn of this.listeners) {
      fn(this.state);
    }
  }

  setConnected(connected: boolean): void {
    this.update({ connected });
  }

  setCatalog(agents: AgentManifest[]): void {
    const activeAgent = this.state.activeAgent ?? agents[0]?.agent_id ?? null;
    let activePanel = this.state.activePanel;
    if (!activePanel && activeAgent) {
      const agent = agents.find((a) => a.agent_id === activeAgent);
      const defaultPanel = agent?.panels.find((p) => p.default);
      activePanel = defaultPanel?.id ?? agent?.panels[0]?.id ?? null;
    }
    this.update({ agents, activeAgent, activePanel });
  }

  switchAgent(agentId: string): void {
    const agent = this.state.agents.find((a) => a.agent_id === agentId);
    const defaultPanel = agent?.panels.find((p) => p.default);
    const activePanel = defaultPanel?.id ?? agent?.panels[0]?.id ?? null;
    this.update({ activeAgent: agentId, activePanel });
  }

  addCommand(entry: ChatEntry): void {
    this.update({ chat: [...this.state.chat, entry] });
  }

  setResponse(msgId: string, response: ResponsePayload): void {
    const chat = this.state.chat.map((e) =>
      e.id === msgId ? { ...e, response } : e,
    );
    this.update({ chat });
  }

  setError(error: string | null): void {
    this.update({ error });
  }
}

export const store = new Store();
