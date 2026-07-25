"use strict";

const { el, clear, button } = require("../lib/dom.js");
const { callFeeder } = require("../lib/feeder-ipc.js");
const { readClipboardSelection } = require("../lib/clipboard-selection.js");
const { loadControlSnapshot, snapshotList } = require("../lib/control-loader.js");
const { listPlanRecords } = require("../plans/plan-store.js");

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

        output.textContent = "Dispatching…";

        const result = callFeeder(
          app,
          "dispatch.run",
          {
            paths: dispatchedItems.map(
              (item) => item.path
            ),
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