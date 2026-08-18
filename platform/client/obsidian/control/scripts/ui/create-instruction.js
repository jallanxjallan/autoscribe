"use strict";

const { loadConfig } = require("../lib/config-loader");

function types() {
  return Object.entries(loadConfig("instructions").library_types || {}).map(([id, item]) => ({ id, ...item }));
}

/** Shared Create Instruction implementation for any instruction vault. */
module.exports = async function createInstruction(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const selection = await openDialog();
  if (!selection) return;

  const title = titleCase(selection.title);
  if (!title) return notice("The title is blank.", 7000);

  const type = types().find((item) => item.prefix === selection.prefix);
  if (!type) throw new Error("Unknown instruction type.");

  const folder = normalize(type.folder);
  await ensureFolder(app, folder);
  const filePath = normalize(`${folder}/${title}.md`);
  if (app.vault.getAbstractFileByPath(filePath)) return notice(`A note already exists at ${filePath}`, 7000);

  const workflow = loadConfig("workflow");
  const instructionConfig = loadConfig("instructions");
  const slug = `${type.prefix}.${kebab(title)}.${suffix(Number(workflow.slug?.suffix_length || 6))}`;
  const defaults = instructionConfig.created_frontmatter || {};
  const frontmatter = [
    "---",
    `slug: ${slug}`,
    `title: ${title}`,
    ...Object.entries({ ...defaults, component: type.component, scope: type.scope }).map(([key, value]) =>
      `${key}: ${Array.isArray(value) ? JSON.stringify(value) : value}`
    ),
    "---",
    `# ${title}`,
    "",
  ].join("\n");

  let file;
  notice(`Creating ${title}…`, 3500);
  try {
    file = await app.vault.create(filePath, frontmatter);
    await app.workspace.getLeaf(false).openFile(file, { active: true });
    notice(`Created ${title}.`, 5000);
  } catch (error) {
    if (file && app.vault.getAbstractFileByPath(file.path)) {
      try { await app.vault.delete(file, true); } catch (_) {}
    }
    console.error("Create Instruction failed:", error);
    notice(`Create Instruction failed: ${error?.message || String(error)}`, 9000);
  }
};

function notice(message, timeout = 5000) {
  const text = String(message || "");
  const nodeRequire = typeof require === "function" ? require : globalThis.window?.require;
  const candidates = [globalThis?.Notice, globalThis?.window?.Notice];
  try {
    if (typeof nodeRequire === "function") candidates.push(nodeRequire("obsidian")?.Notice);
  } catch (_) {}
  for (const NoticeClass of candidates) {
    try {
      if (typeof NoticeClass === "function") {
        new NoticeClass(text, timeout);
        return;
      }
    } catch (_) {}
  }
  try {
    const toast = document.createElement("div");
    toast.textContent = text;
    toast.style.cssText = [
      "position:fixed",
      "right:1rem",
      "bottom:1rem",
      "z-index:100000",
      "max-width:min(36rem,80vw)",
      "padding:.7rem .9rem",
      "background:var(--background-secondary)",
      "color:var(--text-normal)",
      "border:1px solid var(--background-modifier-border)",
      "border-radius:var(--radius-m)",
      "box-shadow:var(--shadow-l)",
    ].join(";");
    document.body.append(toast);
    globalThis.setTimeout(() => toast.remove(), timeout);
    return;
  } catch (_) {}
  console.log(text);
}

function normalize(value) {
  return String(value || "").replace(/\\\\/g, "/").replace(/^\/+|\/+$/g, "");
}

async function ensureFolder(app, folderPath) {
  const parts = normalize(folderPath).split("/").filter(Boolean);
  let current = "";
  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    if (!app.vault.getAbstractFileByPath(current)) await app.vault.createFolder(current);
  }
}

function titleCase(value) {
  return String(value || "").trim().replace(/\s+/g, " ").replace(/\b([A-Za-z])([A-Za-z'’.-]*)/g,
    (_, first, rest) => first.toUpperCase() + rest.toLowerCase());
}

function kebab(value) {
  return String(value || "")
    .normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "untitled";
}

function suffix(length) {
  const alphabet = String(loadConfig("workflow").slug?.suffix_alphabet || "abcdefghjkmnpqrstuvwxyz23456789");
  const cryptoObj = globalThis.crypto;
  if (cryptoObj?.getRandomValues) {
    const bytes = new Uint8Array(length);
    cryptoObj.getRandomValues(bytes);
    return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
  }
  let out = "";
  for (let i = 0; i < length; i += 1) out += alphabet[Math.floor(Math.random() * alphabet.length)];
  return out;
}

function openDialog() {
  return new Promise((resolve) => {
    let finished = false;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:var(--layer-modal,1000);display:grid;place-items:center;background:rgba(0,0,0,.45);";
    const dialog = document.createElement("div");
    dialog.style.cssText = "width:min(38rem,90vw);background:var(--background-primary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:var(--radius-l);box-shadow:var(--shadow-l);padding:1rem;";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Create Instruction");

    const heading = document.createElement("h2");
    heading.textContent = "Create Instruction";
    heading.style.marginTop = "0";
    const intro = document.createElement("p");
    intro.textContent = "Enter a title, then choose the instruction type.";
    intro.style.color = "var(--text-muted)";
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Writer Editor";
    input.style.width = "100%";
    const preview = document.createElement("div");
    preview.style.cssText = "margin:.75rem 0;padding:.65rem .8rem;background:var(--background-secondary);border-radius:var(--radius-s);font-family:var(--font-monospace);color:var(--text-muted);";
    const choices = document.createElement("div");
    choices.style.cssText = "display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;";

    const buttons = types().map((type) => {
      const button = document.createElement("button");
      button.type = "button";
      button.classList.add("mod-cta");
      button.disabled = true;
      button.textContent = `${type.label}  ${type.prefix}.`;
      button.onclick = () => close({ title: input.value, prefix: type.prefix });
      choices.append(button);
      return button;
    });

    function update() {
      const ok = Boolean(input.value.trim());
      for (const button of buttons) button.disabled = !ok;
      const title = titleCase(input.value);
      preview.textContent = ok ? `Filename: ${title}.md    Slug: <prefix>.${kebab(title)}.<id>` : "Filename: —    Slug: —";
    }
    function close(value) {
      if (finished) return;
      finished = true;
      document.removeEventListener("keydown", keydown, true);
      overlay.remove();
      resolve(value);
    }
    function keydown(event) {
      if (event.key === "Escape") { event.preventDefault(); close(null); }
    }

    input.addEventListener("input", update);
    overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(null); });
    document.addEventListener("keydown", keydown, true);
    dialog.append(heading, intro, input, preview, choices);
    overlay.append(dialog);
    document.body.append(overlay);
    update();
    requestAnimationFrame(() => input.focus());
  });
}
