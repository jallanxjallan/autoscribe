# Stage Files

```dataviewjs
const { spawnSync } = require("child_process");
const vaultRoot = app.vault.adapter.basePath;
const state = {
  files: [],
  selected: new Set(),
  stage: "",
  status: "",
  sort: "title_asc",
};

function ipc(request) {
  const result = spawnSync("obs", ["--vault", vaultRoot, "ipc"], {
    input: JSON.stringify(request),
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "obs IPC failed").trim());
  }
  return JSON.parse(result.stdout);
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
  container.empty();
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
      state.files = response.files;
      state.selected.clear();
      render();
    } catch (error) {
      new Notice(error.message, 10000);
    }
  };
  controls.append(stage, status, sort, refresh);
  container.append(controls);

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
    const user = file.user_commit;
    row.append(
      el("td", {}, null),
      el("td", {}, null),
      el("td", {}, file.stage || "—"),
      el("td", {}, file.status || "—"),
      el("td", {}, file.worktree.label),
      el("td", {}, user ? `${shortHash(user)} · ${user.subject}` : "—"),
      el("td", {}, file.dispatch.reason ? `${file.dispatch.state}: ${file.dispatch.reason}` : file.dispatch.state),
      el("td", {}, shortDate(file.mtime)),
    );
    row.children[0].append(checkbox);
    row.children[1].append(link);
    table.append(row);
  }
  container.append(table);

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
      new Notice(`Committed ${response.files.length} file(s): ${response.commit.slice(0, 8)}`);
      state.selected.clear();
      refresh.click();
    } catch (error) {
      new Notice(error.message, 10000);
    }
  };
  commitBox.append(message, amendLabel, commit);
  container.append(commitBox);
}

render();
```
