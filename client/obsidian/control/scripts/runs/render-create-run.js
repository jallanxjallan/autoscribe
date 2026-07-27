"use strict";

const fs = require("fs");
const path = require("path");

const { el, clear, button } = require("../lib/dom.js");
const { callFeeder } = require("../lib/feeder-ipc.js");
const { readClipboardSelection } = require("../lib/clipboard-selection.js");
const { loadControlSnapshot, snapshotList } = require("../lib/control-loader.js");
const { listPlanRecords } = require("../plans/plan-store.js");


const SYSTEM_TMP_ROOT = "/tmp";
const TRANSCLUSION_RE = /!\[\[([^\]]+)\]\]/g;

function splitFrontmatter(text) {
  const match = String(text).match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
  return match
    ? { frontmatter: match[1], body: match[2] }
    : { frontmatter: "", body: String(text) };
}

function vaultRelativePath(vaultRoot, filePath) {
  const raw = String(filePath || "").trim();
  if (!raw) throw new Error("Selected file has no path.");

  const absolute = path.isAbsolute(raw)
    ? path.normalize(raw)
    : path.resolve(vaultRoot, raw);
  const relative = path.relative(vaultRoot, absolute);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Selected file is outside the vault: ${raw}`);
  }

  return relative.split(path.sep).join("/");
}

function parseTransclusion(rawTarget) {
  const target = String(rawTarget || "").split("|")[0].trim();
  const hashAt = target.indexOf("#");

  if (hashAt < 0) {
    return { linkpath: target, fragment: "" };
  }

  return {
    linkpath: target.slice(0, hashAt).trim(),
    fragment: target.slice(hashAt + 1).trim(),
  };
}

function extractHeadingSection(body, heading) {
  const wanted = heading.trim().toLowerCase();
  const lines = body.split(/\r?\n/);
  let start = -1;
  let level = 0;

  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (match && match[2].trim().toLowerCase() === wanted) {
      start = index;
      level = match[1].length;
      break;
    }
  }

  if (start < 0) {
    throw new Error(`Transcluded heading not found: ${heading}`);
  }

  let end = lines.length;
  for (let index = start + 1; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+/);
    if (match && match[1].length <= level) {
      end = index;
      break;
    }
  }

  return lines.slice(start, end).join("\n");
}

function extractBlock(body, blockId) {
  const escaped = String(blockId).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const marker = new RegExp(`\\s*\\^${escaped}\\s*$`);
  const lines = body.split(/\r?\n/);
  const index = lines.findIndex((line) => marker.test(line));

  if (index < 0) {
    throw new Error(`Transcluded block not found: ^${blockId}`);
  }

  let start = index;
  while (start > 0 && lines[start - 1].trim() !== "") start -= 1;

  let end = index + 1;
  while (end < lines.length && lines[end].trim() !== "") end += 1;

  const selected = lines.slice(start, end);
  selected[selected.length - 1] = selected[selected.length - 1].replace(marker, "");
  return selected.join("\n").trimEnd();
}

function selectFragment(body, fragment) {
  if (!fragment) return body;
  if (fragment.startsWith("^")) return extractBlock(body, fragment.slice(1));
  return extractHeadingSection(body, fragment);
}

async function resolveBodyTransclusions(app, body, sourcePath, stack = []) {
  const matches = [...String(body).matchAll(TRANSCLUSION_RE)];
  if (!matches.length) return String(body);

  let output = "";
  let cursor = 0;

  for (const match of matches) {
    output += body.slice(cursor, match.index);
    cursor = match.index + match[0].length;

    const { linkpath, fragment } = parseTransclusion(match[1]);
    if (!linkpath) {
      throw new Error(`Empty transclusion in ${sourcePath}: ${match[0]}`);
    }

    const target = app.metadataCache.getFirstLinkpathDest(linkpath, sourcePath);
    if (!target) {
      throw new Error(`Could not resolve transclusion ${match[0]} in ${sourcePath}`);
    }
    if (target.extension !== "md") {
      throw new Error(`Transclusion is not a Markdown note: ${match[0]} in ${sourcePath}`);
    }
    if (stack.includes(target.path)) {
      const chain = [...stack, target.path].join(" -> ");
      throw new Error(`Circular transclusion detected: ${chain}`);
    }

    const embeddedText = await app.vault.read(target);
    const embeddedBody = splitFrontmatter(embeddedText).body;
    const selected = selectFragment(embeddedBody, fragment);
    const resolved = await resolveBodyTransclusions(
      app,
      selected,
      target.path,
      [...stack, target.path]
    );

    output += resolved;
  }

  output += body.slice(cursor);
  return output;
}

async function stageDispatchFiles(app, items) {
  const vaultRoot = app.vault.adapter.basePath;
  const stagingRoot = fs.mkdtempSync(
    path.join(SYSTEM_TMP_ROOT, "autoscribe-dispatch-")
  );
  const stagedPaths = [];

  try {
    for (const item of items) {
      const relativePath = vaultRelativePath(vaultRoot, item.path);
      const source = app.vault.getAbstractFileByPath(relativePath);

      if (!source || source.extension !== "md") {
        throw new Error(`Selected Markdown file was not found: ${item.path}`);
      }

      const original = await app.vault.read(source);
      const { frontmatter, body } = splitFrontmatter(original);
      const resolvedBody = await resolveBodyTransclusions(
        app,
        body,
        source.path,
        [source.path]
      );

      const stagedPath = path.join(stagingRoot, ...relativePath.split("/"));
      fs.mkdirSync(path.dirname(stagedPath), { recursive: true });
      fs.writeFileSync(stagedPath, frontmatter + resolvedBody, "utf8");
      stagedPaths.push(stagedPath);
    }
  } catch (error) {
    fs.rmSync(stagingRoot, { recursive: true, force: true });
    throw error;
  }

  return { stagingRoot, stagedPaths };
}

function normalizePlan(record) {
  if (!record) return null;

  const slug = String(
    record.slug ||
    record.record_identity ||
    ""
  ).trim();

  if (!slug) return null;

  return {
    ...record,
    slug,
    label: String(record.label || slug),
    ttl: Number.isFinite(Number(record.ttl))
      ? Number(record.ttl)
      : null,
  };
}

function localUploadedPlans(app) {
  return listPlanRecords(app)
    .filter((record) => !record.read_error)
    .filter(
      (record) =>
        record.pending_upload === false ||
        Boolean(record.uploaded_at)
    )
    .map(normalizePlan)
    .filter(Boolean)
    .sort((a, b) =>
      String(a.label).localeCompare(String(b.label))
    );
}

function refreshUploadedPlans() {
  const snapshot = loadControlSnapshot();

  if (snapshot.error) {
    const detail = snapshot.stderr
      ? `; ${snapshot.stderr}`
      : "";

    throw new Error(
      `Could not refresh uploaded plans: ${snapshot.error}${detail}`
    );
  }

  return snapshotList(snapshot.data, "plans")
    .map(normalizePlan)
    .filter((plan) => plan && plan.ttl !== -2)
    .sort((a, b) => {
      const ttlA =
        a.ttl === null
          ? Number.NEGATIVE_INFINITY
          : a.ttl;

      const ttlB =
        b.ttl === null
          ? Number.NEGATIVE_INFINITY
          : b.ttl;

      return (
        ttlB - ttlA ||
        String(a.label).localeCompare(String(b.label))
      );
    });
}

function planOptionText(plan) {
  if (plan.ttl === null) {
    return `${plan.label} — ${plan.slug}`;
  }

  const ttl =
    plan.ttl < 0
      ? "persistent"
      : `${plan.ttl}s TTL`;

  return `${plan.label} — ${plan.slug} (${ttl})`;
}

function renderFiles(
  container,
  items,
  heading = "Files selected for dispatch"
) {
  container.innerHTML = "";
  container.appendChild(el("h3", { text: heading }));

  if (!items.length) {
    container.appendChild(
      el("p", {
        text: "No files loaded from the clipboard.",
      })
    );
    return;
  }

  const table = el("table");
  table.style.width = "100%";

  table.appendChild(
    el(
      "tr",
      {},
      ["#", "File", "Slug"].map((text) =>
        el("th", { text })
      )
    )
  );

  items.forEach((item, index) => {
    table.appendChild(
      el("tr", {}, [
        el("td", { text: String(index + 1) }),
        el("td", { text: item.path }),
        el("td", { text: item.slug || "—" }),
      ])
    );
  });

  container.appendChild(table);
}

async function clearClipboard() {
  const clipboard = globalThis.navigator?.clipboard;

  if (typeof clipboard?.writeText !== "function") {
    throw new Error(
      "Clipboard writing is not available in this Obsidian environment."
    );
  }

  await clipboard.writeText("");
}

function closeCurrentLeaf(app) {
  const leaf = app?.workspace?.activeLeaf;

  if (leaf && typeof leaf.detach === "function") {
    leaf.detach();
  }
}

async function renderCreateRun({ app, container }) {
  clear(container);

  let plans = localUploadedPlans(app);
  let items = [];
  let dispatching = false;

  container.appendChild(
    el("h2", { text: "Dispatch Run" })
  );

  container.appendChild(
    el("p", {
      text:
        "Loads the current clipboard selection locally. " +
        "No client or pipeline status is queried before dispatch.",
    })
  );

  const planSelect = el("select");
  planSelect.style.width = "100%";

  const filesBox = el("div");

  const output = el("pre", { text: "" });
  output.style.whiteSpace = "pre-wrap";

  let dispatchBtn;

  function fillPlans(preferred = "") {
    planSelect.innerHTML = "";

    for (const plan of plans) {
      planSelect.appendChild(
        el("option", {
          value: plan.slug,
          text: planOptionText(plan),
        })
      );
    }

    if (!plans.length) {
      planSelect.appendChild(
        el("option", {
          value: "",
          text: "No locally cached uploaded plans found.",
          disabled: true,
        })
      );
    }

    planSelect.disabled = !plans.length;

    if (
      preferred &&
      plans.some((plan) => plan.slug === preferred)
    ) {
      planSelect.value = preferred;
    }

    updateAvailability();
  }

  function updateAvailability() {
    if (!dispatchBtn) return;

    dispatchBtn.disabled =
      dispatching ||
      !planSelect.value ||
      !items.length;
  }

  async function loadClipboard() {
    items = await readClipboardSelection(app);

    renderFiles(filesBox, items);
    output.textContent = "";

    updateAvailability();
  }

  const refreshPlansBtn = button(
    "Refresh plans",
    () => {
      try {
        const selected = planSelect.value;

        plans = refreshUploadedPlans();
        fillPlans(selected);

        output.textContent =
          `Loaded ${plans.length} uploaded plan` +
          `${plans.length === 1 ? "" : "s"}.`;
      } catch (error) {
        output.textContent = error.message;

        new Notice(
          `Plan refresh failed: ${error.message}`,
          10000
        );
      }
    }
  );

  const reloadClipboardBtn = button(
    "Reload clipboard",
    async () => {
      try {
        await loadClipboard();
      } catch (error) {
        items = [];

        renderFiles(filesBox, items);
        output.textContent = error.message;

        updateAvailability();

        new Notice(
          `Clipboard selection failed: ${error.message}`,
          10000
        );
      }
    }
  );

  dispatchBtn = button(
    "Dispatch Run",
    async () => {
      if (dispatching) return;

      try {
        const planSlug = planSelect.value;

        if (!planSlug) {
          throw new Error("Select an uploaded plan.");
        }

        if (!items.length) {
          throw new Error(
            "The clipboard contains no dispatchable files."
          );
        }

        const dispatchedItems = items.map(
          (item) => ({ ...item })
        );

        dispatching = true;
        updateAvailability();

        output.textContent =
          "Resolving transclusions into system /tmp…";

        const { stagedPaths } = await stageDispatchFiles(
          app,
          dispatchedItems
        );

        output.textContent = "Dispatching staged files…";

        const result = callFeeder(
          app,
          "dispatch.run",
          {
            paths: stagedPaths,
            plan_slug: planSlug,
          }
        );

        let clipboardWarning = "";

        try {
          await clearClipboard();
        } catch (error) {
          clipboardWarning =
            "\n\nWarning: dispatch succeeded, " +
            "but the clipboard could not be cleared: " +
            error.message;
        }

        clear(container);

        container.appendChild(
          el("h2", {
            text: "Dispatch complete",
          })
        );

        container.appendChild(
          el("p", {
            text:
              "The following files left the client " +
              `with plan ${planSlug}.`,
          })
        );

        const receiptBox = el("div");

        renderFiles(
          receiptBox,
          dispatchedItems,
          "Dispatched files"
        );

        container.appendChild(receiptBox);

        const count = Number(result?.count);

        const detail = Number.isFinite(count)
          ? `Feeder accepted ${count} record` +
            `${count === 1 ? "" : "s"}.`
          : "Feeder accepted the dispatch.";

        container.appendChild(
          el("pre", {
            text: detail + clipboardWarning,
          })
        );

        const closeBtn = button(
          "Close",
          () => closeCurrentLeaf(app)
        );

        container.appendChild(closeBtn);

        new Notice("Dispatch complete.");
      } catch (error) {
        output.textContent = error.message;

        new Notice(
          `Dispatch failed: ${error.message}`,
          10000
        );

        console.error(error);

        dispatching = false;
        updateAvailability();
      }
    }
  );

  planSelect.addEventListener(
    "change",
    updateAvailability
  );

  const planRow = el("div");
  planRow.style.display = "flex";
  planRow.style.gap = "0.5rem";
  planRow.style.alignItems = "center";

  planRow.append(
    el(
      "label",
      {},
      ["Uploaded plan ", planSelect]
    ),
    refreshPlansBtn
  );

  const actionRow = el("div");
  actionRow.style.display = "flex";
  actionRow.style.gap = "0.5rem";

  actionRow.append(
    reloadClipboardBtn,
    dispatchBtn
  );

  container.append(
    planRow,
    filesBox,
    actionRow,
    output
  );

  fillPlans();

  try {
    await loadClipboard();
  } catch (error) {
    items = [];

    renderFiles(filesBox, items);
    output.textContent = error.message;

    updateAvailability();
  }
}

module.exports = { renderCreateRun };