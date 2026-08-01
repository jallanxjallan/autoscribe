"use strict";

function openWorkflowModal({ app, title, render, width = "min(96vw, 78rem)" }) {
  if (!app?.workspace) throw new Error("Obsidian app object unavailable.");
  if (typeof render !== "function") throw new Error("Workflow modal requires a render function.");

  return new Promise((resolve, reject) => {
    let closed = false;
    const overlay = document.createElement("div");
    overlay.className = "autoscribe-workflow-overlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:var(--layer-modal,1000);display:grid;place-items:center;background:rgba(0,0,0,.48);padding:2vh 2vw;";

    const dialog = document.createElement("div");
    dialog.className = "modal autoscribe-workflow-modal";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", title);
    dialog.style.cssText = `width:${width};max-height:96vh;overflow:auto;background:var(--background-primary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:var(--radius-l);box-shadow:var(--shadow-l);padding:1rem;`;

    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1rem;position:sticky;top:-1rem;background:var(--background-primary);z-index:2;padding:.25rem 0 .65rem;";
    const heading = document.createElement("h2");
    heading.textContent = title;
    heading.style.margin = "0";
    const closeButton = document.createElement("button");
    closeButton.textContent = "Close";
    header.append(heading, closeButton);

    const container = document.createElement("div");
    container.className = "autoscribe-workflow-content";
    dialog.append(header, container);
    overlay.append(dialog);
    document.body.append(overlay);

    function close(value = null) {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKeyDown, true);
      if (container.__fileStateSelectionTimer) clearInterval(container.__fileStateSelectionTimer);
      overlay.remove();
      resolve(value);
    }
    function onKeyDown(event) {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    }
    closeButton.onclick = () => close();
    overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(); });
    document.addEventListener("keydown", onKeyDown, true);

    Promise.resolve(render(container, { close }))
      .catch((error) => {
        console.error(`${title} failed:`, error);
        if (!closed) {
          container.replaceChildren();
          const pre = document.createElement("pre");
          pre.style.whiteSpace = "pre-wrap";
          pre.textContent = error?.stack || error?.message || String(error);
          container.append(pre);
          new Notice(`${title} failed: ${error?.message || error}`, 10000);
        }
        reject(error);
      });
  });
}

module.exports = { openWorkflowModal };
