# Stage Files

```dataviewjs
const { spawnSync } = require("child_process");
const vaultRoot = app.vault.adapter.basePath;
const root = dv.container;
const state = {
  files: [],
  selected: new Set(),
  stage: "",
  status: "",
  sort: "title_asc",
};

function ipc(request) {
  const obsExecutable = "/home/jeremy/Python3.13Env/bin/obs";
  const result = spawnSync(
    obsExecutable,
    ["--vault", vaultRoot, "ipc"],
    {
      input: JSON.stringify(request),
      encoding: "utf8",
      cwd: vaultRoot,
      maxBuffer: 16 * 1024 * 1024,
      timeout: 30000,
    },
  );
  if (result.error) {
    throw new Error(`obs IPC could not start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    console.error("Stage Files IPC stderr:", result.stderr);
    console.error("Stage Files IPC stdout:", result.stdout);
    const lines = (result.stderr || result.stdout || `exit status ${result.status}`)
      .trim()
      .split("\n")
      .filter(Boolean);
    const detail = lines.at(-1) || `exit status ${result.status}`;
    throw new Error(`obs IPC failed: ${detail}`);
  }
  try {
    const response = JSON.parse(result.stdout);
    if (response && response.ok === false) {
      throw new Error(response.error || response.error_type || "obs IPC failed");
    }
    return response;
  } catch (error) {
    if (error instanceof Error && !error.message.startsWith("Unexpected token")) {
      throw error;
    }
    console.error("Invalid Stage Files IPC output:", result.stdout);
    throw new Error("obs IPC returned invalid JSON; see developer console");
  }
}

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  if (text !== null) node.textContent = text;
  return node;
}

function shortDate(timestamp) {
  if (!timestamp) return "—";
  return new Date(timestamp * 1000).toLocaleString();
}

function shortHash(commit) {
  return commit?.hash ? commit.hash.slice(0, 8) : "—";
}

function render() {
  root.replaceChildren();
  const controls = el("div", { className: "stage-files-controls" });
  const stage = el("input", { placeholder: "stage (blank = all)", value: state.stage });
  const status = el("input", { placeholder: "status (blank = all)", value: state.status });
  const sort = el("select");
  for (const [value, label] of [
    ["title_asc", "Title A–Z"],
    ["mtime_desc", "Touched newest"],
    ["user_commit_desc", "User commit newest"],
  ]) {
    const option = el("option", { value }, label);
    option.selected = state.sort === value;
    sort.append(option);
  }
  const refresh = el("button", {}, "Refresh");
  refresh.onclick = () => {
    try {
      state.stage = stage.value.trim();
      state.status = status.value.trim();
      state.sort = sort.value;
      const response = ipc({
        action: "stage_files.refresh",
        filters: {
          stage: state.stage ? [state.stage] : [],
          status: state.status ? [state.status] : [],
        },
        sort: state.sort,
      });
      if (!response || response.ok !== true) {
        throw new Error(response?.error || "Stage Files refresh failed");
      }
      if (!Array.isArray(response.files)) {
        console.error("Unexpected Stage Files response:", response);
        throw new Error("Stage Files returned no file list");
      }
      state.files = response.files;
      state.selected.clear();
      render();
    } catch (error) {
      new Notice(error.message, 10000);
    }
  };
  controls.append(stage, status, sort, refresh);
  root.append(controls);

  const table = el("table", { className: "stage-files-table" });
  const head = el("tr");
  for (const label of ["", "File", "Stage", "Status", "Git", "User commit", "Dispatch", "Touched"]) {
    head.append(el("th", {}, label));
  }
  table.append(head);
  for (const file of state.files) {
    const row = el("tr");
    const checkbox = el("input", { type: "checkbox", checked: state.selected.has(file.path) });
    checkbox.onchange = () => checkbox.checked ? state.selected.add(file.path) : state.selected.delete(file.path);
    const link = el("a", { href: file.path }, file.title);
    link.onclick = (event) => {
      event.preventDefault();
      app.workspace.openLinkText(file.path, "", false);
    };
    const user = file.user_commit ?? null;
    const gitState = file.worktree?.label ?? "unknown";
    const dispatchState = file.dispatch?.state ?? "unknown";
    const dispatchReason = file.dispatch?.reason ?? "";
    row.append(
      el("td", {}, null),
      el("td", {}, null),
      el("td", {}, file.stage || "—"),
      el("td", {}, file.status || "—"),
      el("td", {}, gitState),
      el("td", {}, user ? `${shortHash(user)} · ${user.subject ?? ""}` : "—"),
      el("td", {}, dispatchReason ? `${dispatchState}: ${dispatchReason}` : dispatchState),
      el("td", {}, shortDate(file.mtime)),
    );
    row.children[0].append(checkbox);
    row.children[1].append(link);
    table.append(row);
  }
  root.append(table);

  const commitBox = el("div", { className: "stage-files-commit" });
  const message = el("input", { placeholder: "Git message / batch label" });
  const amendLabel = el("label");
  const amend = el("input", { type: "checkbox" });
  amendLabel.append(amend, document.createTextNode(" Amend current user commit"));
  const commit = el("button", {}, "Commit selected files");
  commit.onclick = () => {
    try {
      const paths = [...state.selected];
      const response = ipc({ action: "stage_files.commit", paths, message: message.value, amend: amend.checked });
      if (!response || response.ok !== true) {
        throw new Error(response?.error || "Stage Files commit failed");
      }
      const committedFiles = Array.isArray(response.files) ? response.files.length : paths.length;
      const commitHash = response.commit ? response.commit.slice(0, 8) : "unknown";
      new Notice(`Committed ${committedFiles} file(s): ${commitHash}`);
      state.selected.clear();
      refresh.click();
    } catch (error) {
      new Notice(error.message, 10000);
    }
  };
  commitBox.append(message, amendLabel, commit);
  root.append(commitBox);
}

render();
```
