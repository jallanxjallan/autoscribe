"use strict";

function notify(message, timeout = 4000) {
  const text = String(message ?? "").trim();
  if (!text) return;

  try {
    const NoticeClass = globalThis.Notice;
    if (typeof NoticeClass === "function") {
      new NoticeClass(text, timeout);
      return;
    }
  } catch (_) {}

  try {
    const toast = document.createElement("div");
    toast.textContent = text;
    toast.setAttribute("role", "status");
    toast.style.cssText = [
      "position:fixed",
      "right:1rem",
      "top:1rem",
      "z-index:2147483647",
      "max-width:min(34rem,calc(100vw - 2rem))",
      "padding:.7rem .9rem",
      "border:1px solid var(--background-modifier-border)",
      "border-radius:var(--radius-m,8px)",
      "background:var(--background-primary)",
      "color:var(--text-normal)",
      "box-shadow:var(--shadow-l)",
      "white-space:pre-wrap"
    ].join(";");
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), timeout);
  } catch (_) {
    console.log(text);
  }
}

module.exports = { notify };
