"use strict";

/**
 * Shared Library State implementation.
 *
 * The active Library vault is the source of instruction files. Every explicit
 * instruction Markdown file is listed, whether or not Git considers it dirty.
 * Git supplies local state. The service supplies authoritative server state
 * and performs instruction synchronization. Library never invokes `asc`
 * directly, keeping the UI behind the service boundary.
 */
module.exports = async function libraryState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = require;
  const fs = nodeRequire("node:fs");
  const path = nodeRequire("node:path");
  const { spawn } = nodeRequire("node:child_process");

  const vaultRoot = path.resolve(app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath);
  const service = nodeRequire(path.join(vaultRoot, "_control", "scripts", "lib", "dispatch-service.js"));

  async function callService(command, input = null) {
    const executable = service.serviceCommand(app);
    const response = await service.run(executable.command, [...executable.prefix, command], {
      cwd: vaultRoot,
      input: input == null ? "" : JSON.stringify(input),
    });
    const output = JSON.parse(String(response.stdout || "{}").trim() || "{}");
    if (!output.ok) throw new Error(output.error || `${command} failed`);
    return output;
  }

  function notify(message, timeout = 5000) {
    const text = String(message || "");
    const candidates = [
      globalThis?.Notice,
      globalThis?.window?.Notice,
    ];
    for (const NoticeClass of candidates) {
      try {
        if (typeof NoticeClass === "function") {
          new NoticeClass(text, timeout);
          return;
        }
      } catch (_) {}
    }

    // Last-resort visible toast for QuickAdd/user-script environments where
    // Obsidian's Notice constructor is not exposed globally.
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

  function run(command, args, { input = null } = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        cwd: vaultRoot,
        shell: false,
        stdio: ["pipe", "pipe", "pipe"],
      });
      const stdout = [];
      const stderr = [];
      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk) => stdout.push(chunk));
      child.stderr.on("data", (chunk) => stderr.push(chunk));
      child.once("error", reject);
      child.once("close", (status) => {
        const out = stdout.join("");
        const err = stderr.join("");
        if (status !== 0) return reject(new Error(err.trim() || out.trim() || `${command} exited with status ${status}`));
        resolve({ stdout: out, stderr: err });
      });
      if (input == null) child.stdin.end();
      else child.stdin.end(input);
    });
  }

  function normalizeRelative(filePath) {
    return String(filePath || "").replace(/\\/g, "/").replace(/^\.\//, "");
  }

  function ignoredPath(relativePath) {
    const normalized = normalizeRelative(relativePath);
    const parts = normalized.split("/").filter(Boolean);
    return parts.includes(".obsidian") || parts.includes(".git") || normalized.toLowerCase().endsWith(".json");
  }

  async function readGitState() {
    const { stdout } = await run("git", ["status", "--porcelain=v1", "-z", "--untracked-files=all"]);
    const chunks = stdout.split("\0").filter(Boolean);
    const state = new Map();

    for (let index = 0; index < chunks.length; index += 1) {
      const entry = chunks[index];
      if (entry.length < 4) continue;
      const status = entry.slice(0, 2);
      const relativePath = normalizeRelative(entry.slice(3));
      let originalPath = null;
      if (status.includes("R") || status.includes("C")) {
        originalPath = normalizeRelative(chunks[index + 1] || "");
        index += 1;
      }
      if (ignoredPath(relativePath)) continue;
      state.set(relativePath, { status, originalPath });
    }
    return state;
  }

  function parseFrontmatter(text) {
    const match = text.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)([\s\S]*)$/);
    if (!match) return null;
    const yaml = match[1];
    const value = (key) => {
      const found = yaml.match(new RegExp(`^${key}:\\s*["']?([^\\r\\n"']+)["']?\\s*$`, "m"));
      return String(found?.[1] || "").trim();
    };
    return {
      slug: value("slug"),
      type: value("type"),
      kind: value("kind"),
      scope: value("scope"),
      component: value("component"),
      title: value("title"),
      body: match[2],
    };
  }

  function instructionRecordFromPath(relativePath) {
    const normalized = normalizeRelative(relativePath);
    if (ignoredPath(normalized) || path.extname(normalized).toLowerCase() !== ".md") return null;
    const absolutePath = path.resolve(vaultRoot, normalized);
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) return null;
    const parsed = parseFrontmatter(fs.readFileSync(absolutePath, "utf8"));
    if (!parsed?.slug || !parsed.body.trim()) return null;
    if (parsed.type !== "instruction" && parsed.kind !== "instruction") return null;
    return {
      identity: parsed.slug,
      title: path.basename(absolutePath, path.extname(absolutePath)),
      content: parsed.body,
      filename: path.basename(absolutePath),
      relativePath: normalized,
      scope: parsed.scope || "",
      component: parsed.component || "",
    };
  }

  function walkMarkdown(dir, prefix = "") {
    const found = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === ".git" || entry.name === ".obsidian") continue;
      const relativePath = normalizeRelative(path.posix.join(prefix, entry.name));
      const absolutePath = path.join(dir, entry.name);
      if (entry.isDirectory()) found.push(...walkMarkdown(absolutePath, relativePath));
      else if (entry.isFile() && entry.name.toLowerCase().endsWith(".md")) found.push(relativePath);
    }
    return found;
  }

  function redisInstructionMap(snapshot) {
    const registries = snapshot?.registries || {};
    const values = registries.instructions || registries.instruction || {};
    const map = new Map();
    if (Array.isArray(values)) {
      for (const record of values) {
        const slug = String(record?.record_identity || record?.slug || "").trim();
        if (slug) map.set(slug, record);
      }
    } else if (values && typeof values === "object") {
      for (const [key, record] of Object.entries(values)) {
        const slug = String(record?.record_identity || record?.slug || key || "").trim();
        if (slug) map.set(slug, record);
      }
    }
    return map;
  }

  async function readServerInstructions() {
    const snapshot = await callService("define-plan-snapshot");
    return redisInstructionMap(snapshot.server);
  }

  function gitLabel(status) {
    if (!status) return "clean";
    const compact = status.trim();
    if (!compact) return "clean";
    if (status.includes("?")) return "untracked";
    if (status.includes("A")) return "added";
    if (status.includes("D")) return "deleted";
    if (status.includes("R")) return "renamed";
    if (status.includes("M")) return "modified";
    return compact;
  }

  async function readInstructionRows() {
    const git = await readGitState();
    const records = walkMarkdown(vaultRoot)
      .map((relativePath) => instructionRecordFromPath(relativePath))
      .filter(Boolean)
      .sort((a, b) => a.relativePath.localeCompare(b.relativePath));

    const rows = records.map((record) => {
      const gitInfo = git.get(record.relativePath) || null;
      return {
        ...record,
        gitStatus: gitInfo?.status || "",
        gitState: gitLabel(gitInfo?.status || ""),
        originalPath: gitInfo?.originalPath || null,
        remote: "checking",
        remoteDetail: "",
      };
    });

    const redis = await readServerInstructions();
    rows.forEach((row) => {
      const remote = redis.get(row.identity) || null;
      row.remote = remote ? "present" : "missing";
      row.remoteDetail = remote
        ? `Redis: ${row.identity}${remote.title ? ` — ${remote.title}` : ""}`
        : `Redis record missing: ${row.identity}`;
    });
    return rows;
  }

  async function uploadInstructions(rows) {
    if (!rows.length) throw new Error("No instruction files selected.");
    const result = await callService("instructions-sync", {
      version: 1,
      root: vaultRoot,
      paths: rows.map((row) => row.relativePath),
    });
    return { records: rows, result };
  }

  // Dashboard and other read-only Library views consume the same snapshot as
  // the modal instead of duplicating Git, frontmatter, or service logic.
  if (params.mode === "snapshot") return readInstructionRows();


  return new Promise((resolve) => {
    let closed = false;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:var(--layer-modal,1000);display:grid;place-items:center;background:rgba(0,0,0,.48);padding:2vh 2vw;";
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Library State");
    dialog.style.cssText = "width:min(96vw,76rem);max-height:96vh;overflow:auto;background:var(--background-primary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:var(--radius-l);box-shadow:var(--shadow-l);padding:1rem;";

    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1rem;position:sticky;top:-1rem;background:var(--background-primary);z-index:3;padding:.25rem 0 .65rem;";
    const heading = document.createElement("h2");
    heading.textContent = "Library State";
    heading.style.margin = "0";
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "Close";
    header.append(heading, closeButton);

    const container = document.createElement("div");
    dialog.append(header, container);
    overlay.append(dialog);
    document.body.append(overlay);

    function close(value = null) {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
      resolve(value);
    }
    function onKeyDown(event) {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    }
    closeButton.onclick = () => close();
    overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(); });
    document.addEventListener("keydown", onKeyDown, true);

    const vaultLine = document.createElement("div");
    vaultLine.textContent = vaultRoot;
    vaultLine.style.cssText = "font-family:var(--font-monospace);color:var(--text-muted);margin:-.4rem 0 .8rem;overflow-wrap:anywhere;";
    container.append(vaultLine);

    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.8rem;";
    const refreshButton = document.createElement("button");
    refreshButton.type = "button";
    refreshButton.textContent = "Refresh";
    const selectNeededButton = document.createElement("button");
    selectNeededButton.type = "button";
    selectNeededButton.textContent = "Select Upload Needed";
    const selectAllButton = document.createElement("button");
    selectAllButton.type = "button";
    selectAllButton.textContent = "Select All";
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.textContent = "Clear";
    const uploadButton = document.createElement("button");
    uploadButton.type = "button";
    uploadButton.textContent = "Upload";
    uploadButton.classList.add("mod-cta");
    toolbar.append(refreshButton, selectNeededButton, selectAllButton, clearButton, uploadButton);
    container.append(toolbar);

    const summary = document.createElement("div");
    summary.style.cssText = "margin:.4rem 0 .7rem;color:var(--text-muted);";
    const list = document.createElement("div");
    list.style.cssText = "border:1px solid var(--background-modifier-border);border-radius:var(--radius-m);max-height:58vh;overflow:auto;padding:.35rem;";
    const output = document.createElement("pre");
    output.style.cssText = "white-space:pre-wrap;max-height:18rem;overflow:auto;margin-top:.8rem;";
    container.append(summary, list, output);

    let rows = [];
    let boxes = [];

    function uploadNeeded(row) {
      return row.gitState !== "clean" || row.remote === "missing";
    }

    function updateSummary() {
      const selected = boxes.filter((box) => box?.checked).length;
      const dirty = rows.filter((row) => row.gitState !== "clean").length;
      const missing = rows.filter((row) => row.remote === "missing").length;
      summary.textContent = `${rows.length} instruction(s) · ${dirty} locally changed · ${missing} Redis missing · ${selected} selected`;
      uploadButton.disabled = selected === 0;
    }

    function stateText(row) {
      return `${row.gitState} / ${row.remote}`;
    }

    function renderRows() {
      list.replaceChildren();
      boxes = [];

      const groups = new Map();
      rows.forEach((row, index) => {
        const folder = path.posix.dirname(row.relativePath) === "." ? "Vault root" : path.posix.dirname(row.relativePath);
        if (!groups.has(folder)) groups.set(folder, []);
        groups.get(folder).push({ row, index });
      });

      for (const [folder, items] of groups) {
        const section = document.createElement("section");
        section.style.cssText = "margin:.25rem 0 .7rem;border:1px solid var(--background-modifier-border);border-radius:var(--radius-m);overflow:hidden;";

        const folderHeading = document.createElement("div");
        folderHeading.style.cssText = "display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:1rem;padding:.55rem .75rem;background:var(--background-secondary);font-weight:600;position:sticky;top:0;z-index:2;";
        const folderName = document.createElement("span");
        folderName.textContent = folder;
        const folderCount = document.createElement("span");
        const folderNeeded = items.filter(({ row }) => uploadNeeded(row)).length;
        folderCount.textContent = `${items.length} instruction${items.length === 1 ? "" : "s"}${folderNeeded ? ` · ${folderNeeded} need upload` : ""}`;
        folderCount.style.cssText = "font-size:var(--font-ui-smaller);font-weight:400;color:var(--text-muted);";
        folderHeading.append(folderName, folderCount);
        section.append(folderHeading);

        const columnHeading = document.createElement("div");
        columnHeading.style.cssText = "display:grid;grid-template-columns:1.6rem 10.5rem minmax(0,1fr);gap:.7rem;align-items:center;padding:.35rem .7rem;color:var(--text-muted);font-size:var(--font-ui-smaller);border-top:1px solid var(--background-modifier-border);border-bottom:1px solid var(--background-modifier-border);";
        columnHeading.append(document.createElement("span"), Object.assign(document.createElement("span"), { textContent: "State" }), Object.assign(document.createElement("span"), { textContent: "Instruction" }));
        section.append(columnHeading);

        items.forEach(({ row, index: rowIndex }, itemIndex) => {
          const label = document.createElement("label");
          label.style.cssText = `display:grid;grid-template-columns:1.6rem 10.5rem minmax(0,1fr);gap:.7rem;align-items:center;padding:.5rem .7rem;cursor:pointer;${itemIndex ? "border-top:1px solid var(--background-modifier-border);" : ""}`;

          const box = document.createElement("input");
          box.type = "checkbox";
          box.dataset.rowIndex = String(rowIndex);
          box.addEventListener("change", updateSummary);
          boxes[rowIndex] = box;

          const state = document.createElement("code");
          state.textContent = stateText(row);
          state.style.cssText = "font-size:var(--font-ui-smaller);color:var(--text-muted);white-space:nowrap;";
          state.title = row.remoteDetail || stateText(row);

          const file = document.createElement("a");
          const linkTarget = row.relativePath.replace(/\.md$/i, "");
          file.classList.add("internal-link");
          file.dataset.href = linkTarget;
          file.href = linkTarget;
          file.style.cssText = "min-width:0;overflow-wrap:anywhere;";
          file.textContent = `[[${path.posix.basename(linkTarget)}]]`;
          file.title = `${row.relativePath}\n${row.identity}`;
          file.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            void app.workspace.openLinkText(linkTarget, "", false);
          });

          label.append(box, state, file);
          section.append(label);
        });
        list.append(section);
      }

      if (!rows.length) {
        const empty = document.createElement("div");
        empty.textContent = "No instruction files found in the active vault.";
        empty.style.cssText = "padding:1rem;text-align:center;color:var(--text-muted);";
        list.append(empty);
      }
      updateSummary();
    }

    async function refresh({ announce = true } = {}) {
      if (announce) notify("Refreshing Library State…", 3000);
      refreshButton.disabled = true;
      selectNeededButton.disabled = true;
      selectAllButton.disabled = true;
      uploadButton.disabled = true;
      output.textContent = "Reading Library and checking Redis state…";
      try {
        rows = await readInstructionRows();
        output.textContent = "";
        renderRows();
        if (announce) notify(`Library State refreshed: ${rows.length} instruction(s).`, 5000);
      } catch (error) {
        rows = [];
        renderRows();
        output.textContent = error?.stack || error?.message || String(error);
        notify(`Library State failed: ${error?.message || error}`, 9000);
      } finally {
        refreshButton.disabled = false;
        selectNeededButton.disabled = false;
        selectAllButton.disabled = false;
        updateSummary();
      }
    }

    refreshButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void refresh({ announce: true });
    });
    selectNeededButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      rows.forEach((row, index) => { if (boxes[index]) boxes[index].checked = uploadNeeded(row); });
      updateSummary();
    });
    selectAllButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      boxes.forEach((box) => { if (box) box.checked = true; });
      updateSummary();
    });
    clearButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      boxes.forEach((box) => { if (box) box.checked = false; });
      updateSummary();
    });
    uploadButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const selected = rows.filter((_, index) => boxes[index]?.checked);
      if (!selected.length) {
        notify("No instructions selected for upload.", 5000);
        output.textContent = "No instructions selected for upload.";
        return;
      }

      const originalLabel = uploadButton.textContent;
      const startMessage = `Uploading ${selected.length} instruction${selected.length === 1 ? "" : "s"}…`;
      uploadButton.textContent = startMessage;
      uploadButton.disabled = true;
      refreshButton.disabled = true;
      selectNeededButton.disabled = true;
      selectAllButton.disabled = true;
      clearButton.disabled = true;
      output.textContent = startMessage;
      notify(startMessage, 5000);
      console.info(`[Library State] ${startMessage}`);

      // Give Obsidian a paint cycle before spawning the CLI. If the button
      // text and notice appear, we know the click handler itself fired.
      await new Promise((resolveTick) => globalThis.setTimeout(resolveTick, 0));

      try {
        const outcome = await uploadInstructions(selected);
        const doneMessage = `Upload completed for ${outcome.records.length} selected instruction(s).`;
        output.textContent = [
          doneMessage,
          Array.isArray(outcome.result?.items) ? `\nService results:\n${outcome.result.items.map((item) => `${item.slug}: ${item.status}`).join("\n")}` : "",
        ].filter(Boolean).join("\n");
        notify(doneMessage, 7000);
        console.info(`[Library State] ${doneMessage}`);
        rows = await readInstructionRows();
        renderRows();
      } catch (error) {
        const failure = `Upload failed: ${error?.message || error}`;
        output.textContent = error?.stack || error?.message || String(error);
        notify(failure, 10000);
        console.error("[Library State]", error);
      } finally {
        uploadButton.textContent = originalLabel;
        refreshButton.disabled = false;
        selectNeededButton.disabled = false;
        selectAllButton.disabled = false;
        clearButton.disabled = false;
        updateSummary();
      }
    });

    refresh({ announce: false });
  });
};
