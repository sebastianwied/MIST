/** Error popup — shows transient error messages. */

import { store, type State } from "../store";

export function mountErrorPopup(container: HTMLElement): void {
  store.subscribe((state) => render(container, state));
}

function render(container: HTMLElement, state: State): void {
  if (!state.error) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");
  container.innerHTML = "";

  const msg = document.createElement("p");
  msg.className = "error-message";
  msg.textContent = state.error;

  const dismiss = document.createElement("button");
  dismiss.className = "error-dismiss";
  dismiss.textContent = "Dismiss";
  dismiss.addEventListener("click", () => store.setError(null));

  container.appendChild(msg);
  container.appendChild(dismiss);
}
