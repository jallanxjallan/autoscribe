"use strict";

function createRefreshControl(parent, {
  onRefresh,
  label = "Refresh",
  busyLabel = "Refreshing…",
  status = "",
} = {}) {
  if (!parent?.createEl) throw new Error("Refresh control requires an Obsidian container");
  if (typeof onRefresh !== "function") throw new Error("Refresh control requires onRefresh");

  const row = parent.createEl("div");
  row.style.cssText = "display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.6rem 0 1rem";

  const button = row.createEl("button", { text: label });
  button.type = "button";

  const statusEl = row.createSpan({ text: String(status || "") });

  async function refresh() {
    if (button.disabled) return;
    button.disabled = true;
    button.setText(busyLabel);
    try {
      await onRefresh({ button, status: statusEl });
    } finally {
      button.disabled = false;
      button.setText(label);
    }
  }

  button.addEventListener("click", refresh);

  return {
    row,
    button,
    status: statusEl,
    refresh,
    setStatus(value) {
      statusEl.setText(String(value || ""));
    },
  };
}

module.exports = { createRefreshControl };
