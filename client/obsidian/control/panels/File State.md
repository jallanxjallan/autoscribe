# File State

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

'use strict';

const { spawnSync } = require('child_process');
const path = require('path');
const { el, clear, button, setTriState } = loadControl("scripts/lib/dom.js");
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");
const {
  currentSelectionPath,
  readCurrentSelection,
  writeCurrentSelection,
} = loadControl("scripts/selections/current-selection.js");
const { currentSelectionSummary } = loadControl("scripts/lib/selection-loader.js");
const { listTransportRuns, responseHistoryForPath, pipelineStateForPath, getArchivedResponseReview, reconsiderResponse } = loadControl("scripts/lib/git-transport.js");
const { renderDiff } = loadControl("scripts/lib/diff-view.js");

const PYTHON_EXECUTABLE = '/home/jeremy/Python3.13Env/bin/python';
const FILE_STATE_HELPER = path.join(__dirname, 'file_state.py');
const LIVE_SELECTION_INTERVAL_MS = 1000;

const SORTS = [
  ['title_asc', 'Title A–Z'],
  ['mtime_desc', 'Touched newest'],
  ['user_commit_desc', 'User commit newest'],
];


function helperRequest(root, request) {
  const result = spawnSync(PYTHON_EXECUTABLE, [FILE_STATE_HELPER], {
    input: JSON.stringify({ ...request, vault_root: root }),
    encoding: 'utf8',
    cwd: root,
    maxBuffer: 32 * 1024 * 1024,
    timeout: 120000,
  });

  if (result.error) {
    throw new Error(`File State helper could not start: ${result.error.message}`);
  }

  let response;
  try {
    response = JSON.parse(result.stdout || '{}');
  } catch {
    const detail = String(result.stderr || result.stdout || `exit status ${result.status}`).trim();
    throw new Error(`File State helper returned invalid JSON: ${detail || '(empty output)'}`);
  }

  if (result.status !== 0 || response?.ok === false) {
    throw new Error(String(response?.error || result.stderr || result.stdout || `exit status ${result.status}`).trim());
  }

  return response.result || {};
}

function selectOptions(select, values) {
  for (const [value, label] of values) {
    select.appendChild(el('option', { value, text: label }));
  }
  return select;
}

function shortDate(timestamp) {
  if (!timestamp) return '—';
  return new Date(Number(timestamp) * 1000).toLocaleString();
}

function shortCommit(commit) {
  if (!commit?.hash) return '—';
  const subject = String(commit.subject || '').trim();
  return `${commit.hash.slice(0, 8)}${subject ? ` · ${subject}` : ''}`;
}

function gitState(file) {
  return String(file?.worktree?.label || 'unknown').trim().toLowerCase() || 'unknown';
}

function displayTitle(file) {
  return file.title || path.basename(file.path || '') || file.path || 'Untitled';
}

function selectionItem(file, index) {
  return {
    order: index + 1,
    path: file.path,
    slug: file.slug || '',
    title: displayTitle(file),
    stage: file.stage || '',
    status: file.status || '',
    action: file.action || '',
    repo_state: gitState(file),
  };
}

function selectionSignature(selection) {
  if (!selection?.items) return '';
  return selection.items
    .map((item) => `${item.path || ''}\0${item.slug || ''}`)
    .join('\u0001');
}

function renderFileState({ app, container }) {
  if (container.__fileStateSelectionTimer) {
    clearInterval(container.__fileStateSelectionTimer);
  }
  clear(container);

  const root = app.vault.adapter.basePath;
  const state = {
    files: [],
    rows: [],
    stage: '',
    status: '',
    action: '',
    sort: 'title_asc',
    gitState: 'all',
    filter: '',
    lastSelectionSignature: null,
  };

  const activeBox = el('div');
  activeBox.style.marginBottom = '1rem';
  activeBox.style.padding = '0.75rem';
  activeBox.style.border = '1px solid var(--background-modifier-border)';
  activeBox.style.borderRadius = '6px';
  container.appendChild(activeBox);

  function renderActiveFileState() {
    activeBox.replaceChildren();
    activeBox.appendChild(el('h2', { text: 'Active File Response State' }));
    const active = app.workspace.getActiveFile();
    if (!active || active.extension !== 'md') {
      activeBox.appendChild(el('p', { text: 'Open a Markdown file, then invoke File State from its hotkey.' }));
      return;
    }
    activeBox.appendChild(el('p', { text: active.path }));
    const frontmatter = app.metadataCache.getFileCache(active)?.frontmatter || {};
    activeBox.appendChild(el('p', { text: `Action: ${frontmatter.action || '—'} · Stage: ${frontmatter.stage || '—'} · Status: ${frontmatter.status || '—'}` }));
    let pipeline;
    try { pipeline = pipelineStateForPath(app, active.path); }
    catch (error) { activeBox.appendChild(el('pre', { text: error.message || String(error) })); return; }
    if (pipeline) {
      activeBox.appendChild(el('p', { text: `Pipeline: ${pipeline.state} · ${pipeline.plan_identity || 'unknown plan'} · ${pipeline.run_identity}` }));
    } else {
      activeBox.appendChild(el('p', { text: 'Pipeline: no dispatch history found.' }));
    }
    let history;
    try { history = responseHistoryForPath(app, active.path); }
    catch (error) { activeBox.appendChild(el('pre', { text: error.message || String(error) })); return; }
    if (!history.length) {
      activeBox.appendChild(el('p', { text: 'No retained response is available for review.' }));
      return;
    }
    const latest = history[0];
    let review;
    try { review = getArchivedResponseReview(app, latest.branch, latest.record.identity); }
    catch (error) { activeBox.appendChild(el('pre', { text: error.message || String(error) })); return; }
    const outcome = latest.decision?.outcome || 'pending';
    activeBox.appendChild(el('p', { text: `Run ${latest.run_identity} · ${latest.plan_identity || 'unknown plan'} · current decision: ${outcome}` }));
    renderDiff(activeBox, review);
    const controls = el('div');
    controls.style.display = 'flex';
    controls.style.gap = '0.75rem';
    controls.style.marginTop = '0.75rem';
    if (outcome === 'declined') {
      controls.appendChild(button('Accept response after all', () => reconsiderActive('accepted', latest, active.path)));
    } else if (outcome === 'accepted') {
      controls.appendChild(button('Roll back accepted response', () => reconsiderActive('declined', latest, active.path)));
    } else {
      controls.appendChild(button('Accept response', () => reconsiderActive('accepted', latest, active.path)));
      controls.appendChild(button('Decline response', () => reconsiderActive('declined', latest, active.path)));
    }
    activeBox.appendChild(controls);
  }

  function reconsiderActive(outcome, run, sourcePath) {
    try {
      const verb = outcome === 'accepted' ? 'accept' : 'roll back';
      if (!window.confirm(`Are you sure you want to ${verb} the retained response for ${sourcePath}?`)) return;
      reconsiderResponse(app, run.branch, run.record.identity, outcome);
      new Notice(outcome === 'accepted' ? 'Response accepted and marked for review.' : 'Accepted response rolled back.');
      renderActiveFileState();
      refreshFiles();
    } catch (error) {
      console.error(error);
      new Notice(`Could not reconsider response: ${error.message}`, 10000);
    }
  }

  const toolbar = el('div');
  toolbar.style.display = 'flex';
  toolbar.style.gap = '0.5rem';
  toolbar.style.alignItems = 'center';
  toolbar.style.flexWrap = 'wrap';
  toolbar.style.marginBottom = '0.75rem';

  const stageInput = el('input', { placeholder: 'Stage (blank = all)' });
  const statusInput = el('input', { placeholder: 'Status (blank = all)' });
  const actionInput = el('input', { placeholder: 'Action (blank = all)' });
  const sortSelect = selectOptions(el('select'), SORTS);
  const refreshButton = button('Refresh', refreshFiles);
  toolbar.append(stageInput, statusInput, actionInput, sortSelect, refreshButton);

  const selectionToolbar = el('div');
  selectionToolbar.style.display = 'flex';
  selectionToolbar.style.gap = '0.5rem';
  selectionToolbar.style.alignItems = 'center';
  selectionToolbar.style.flexWrap = 'wrap';
  selectionToolbar.style.marginBottom = '0.75rem';

  const stateSelect = el('select');
  stateSelect.appendChild(el('option', { value: 'all', text: 'All git states' }));
  const filterInput = el('input', {
    type: 'search',
    placeholder: 'Filter path, title, slug, stage, status, action, or pipeline',
  });
  filterInput.style.minWidth = '20rem';

  const selectVisibleButton = button('Select visible', () => {
    for (const row of visibleRows()) row.checkbox.checked = true;
    updateSelectionStatus();
  });
  const clearVisibleButton = button('Clear visible', () => {
    for (const row of visibleRows()) row.checkbox.checked = false;
    updateSelectionStatus();
  });
  const loadSelectionButton = button('Load current selection', loadCurrentSelection);
  const saveSelectionButton = button('Save current selection', saveCurrentSelection);
  const visibleState = el('input', { type: 'checkbox', title: 'Visible selection state' });
  visibleState.disabled = true;
  const selectionStatus = el('span', { text: '0 selected' });

  selectionToolbar.append(
    el('label', {}, ['Show: ', stateSelect]),
    filterInput,
    selectVisibleButton,
    clearVisibleButton,
    loadSelectionButton,
    saveSelectionButton,
    visibleState,
    selectionStatus,
  );

  const tableBox = el('div');

  const commitBox = el('div');
  commitBox.style.display = 'flex';
  commitBox.style.gap = '0.5rem';
  commitBox.style.alignItems = 'center';
  commitBox.style.flexWrap = 'wrap';
  commitBox.style.marginTop = '0.75rem';

  const messageInput = el('input', { placeholder: 'Commit message' });
  messageInput.style.minWidth = '24rem';
  const amend = el('input', { type: 'checkbox' });
  const amendLabel = el('label', {}, [amend, document.createTextNode(' Amend current user commit')]);
  const commitButton = button('Commit checked files', commitCheckedFiles);
  commitBox.append(messageInput, amendLabel, commitButton);

  container.append(toolbar, selectionToolbar, tableBox, commitBox);

  stageInput.addEventListener('change', refreshFiles);
  statusInput.addEventListener('change', refreshFiles);
  actionInput.addEventListener('change', refreshFiles);
  sortSelect.addEventListener('change', refreshFiles);
  stateSelect.addEventListener('change', applyView);
  filterInput.addEventListener('input', applyView);

  function selectedRows() {
    return state.rows.filter((row) => row.checkbox.checked);
  }

  function visibleRows() {
    return state.rows.filter((row) => row.tr.style.display !== 'none');
  }

  function updateSelectionStatus() {
    const visible = visibleRows();
    const visibleSelected = visible.filter((row) => row.checkbox.checked);
    setTriState(visibleState, visibleSelected.length, visible.length);
    selectionStatus.textContent = `${selectedRows().length} selected; ${visible.length} visible; ${state.rows.length} total`;
  }

  function matchesView(file) {
    if (stageInput.value.trim() && String(file.stage || '').trim() !== stageInput.value.trim()) return false;
    if (statusInput.value.trim() && String(file.status || '').trim() !== statusInput.value.trim()) return false;
    if (actionInput.value.trim() && String(file.action || '').trim() !== actionInput.value.trim()) return false;
    const wantedState = stateSelect.value;
    if (wantedState !== 'all' && gitState(file) !== wantedState) return false;

    const needle = filterInput.value.trim().toLowerCase();
    if (!needle) return true;

    const haystack = [
      file.path,
      file.title,
      file.slug,
      file.stage,
      file.status,
      file.action,
      file.dispatch?.state,
      file.dispatch?.plan_identity,
      gitState(file),
    ].map((value) => String(value || '').toLowerCase()).join(' ');
    return haystack.includes(needle);
  }

  function applyView() {
    for (const row of state.rows) {
      row.tr.style.display = matchesView(row.file) ? '' : 'none';
    }
    updateSelectionStatus();
  }

  function renderTable(previouslySelected = new Set()) {
    tableBox.replaceChildren();

    const table = el('table');
    table.style.width = '100%';
    const head = el('tr');
    for (const label of ['', 'File', 'Stage', 'Status', 'Action', 'Git state', 'User commit', 'Pipeline', 'Touched']) {
      head.appendChild(el('th', { text: label }));
    }
    table.appendChild(head);

    state.rows = state.files.map((file) => {
      const tr = el('tr');
      const checkbox = el('input', {
        type: 'checkbox',
      });
      checkbox.checked = previouslySelected.has(file.path);
      checkbox.addEventListener('change', updateSelectionStatus);

      const checkCell = el('td');
      checkCell.appendChild(checkbox);

      const fileCell = el('td');
      createInternalLink(fileCell, app, file.path, displayTitle(file));

      const dispatchState = String(file.dispatch?.state || 'unknown');
      const dispatchReason = String(file.dispatch?.reason || '').trim();

      tr.append(
        checkCell,
        fileCell,
        el('td', { text: file.stage || '—' }),
        el('td', { text: file.status || '—' }),
        el('td', { text: file.action || '—' }),
        el('td', { text: gitState(file) }),
        el('td', { text: shortCommit(file.user_commit) }),
        el('td', { text: dispatchReason ? `${dispatchState}: ${dispatchReason}` : dispatchState }),
        el('td', { text: shortDate(file.mtime) }),
      );
      table.appendChild(tr);
      return { file, tr, checkbox };
    });

    tableBox.appendChild(table);
    applyView();
  }

  function pipelineStatesByPath() {
    const map = new Map();
    for (const run of listTransportRuns(app)) {
      for (const record of run.dispatch?.records || []) {
        const sourcePath = String(record.source_path || '').replaceAll('\\', '/');
        if (!sourcePath || map.has(sourcePath)) continue;
        const result = run.results?.find((item) => item.identity === record.identity) || null;
        const decision = run.decisions?.find((item) => item.identity === record.identity) || null;
        let pipelineState = run.status;
        if (decision?.outcome === 'accepted') pipelineState = 'written-back';
        else if (decision?.outcome === 'declined') pipelineState = 'declined';
        else if (result) pipelineState = 'response-pending';
        map.set(sourcePath, {
          state: pipelineState,
          run_identity: run.run_identity,
          plan_identity: run.plan_identity || null,
          branch: run.branch,
          created_at: run.created_at || null,
          decision: decision?.outcome || null,
        });
      }
    }
    return map;
  }

  function refreshFiles() {
    try {
      const preserved = new Set(selectedRows().map((row) => row.file.path));
      state.stage = stageInput.value.trim();
      state.status = statusInput.value.trim();
      state.action = actionInput.value.trim();
      state.sort = sortSelect.value;

      const response = helperRequest(root, {
        operation: 'refresh',
        filters: {
          stage: state.stage ? [state.stage] : [],
          status: state.status ? [state.status] : [],
          action: state.action ? [state.action] : [],
        },
        sort: state.sort,
      });

      if (!Array.isArray(response.files)) {
        throw new Error('File State returned no file list.');
      }

      const pipelineByPath = pipelineStatesByPath();
      state.files = response.files.map((file) => ({ ...file, dispatch: pipelineByPath.get(file.path) || null }));

      const previousState = stateSelect.value || 'all';
      const labels = [...new Set(state.files.map(gitState))].sort((a, b) => a.localeCompare(b));
      stateSelect.replaceChildren(el('option', { value: 'all', text: 'All git states' }));
      for (const label of labels) {
        stateSelect.appendChild(el('option', { value: label, text: label }));
      }
      stateSelect.value = labels.includes(previousState) ? previousState : 'all';

      renderTable(preserved);
    } catch (error) {
      console.error(error);
      new Notice(`File State refresh failed: ${error.message}`, 10000);
    }
  }

  function normalizedPath(value) {
    const raw = String(value || '').trim().replaceAll('\\', '/');
    if (!raw) return '';
    const absoluteRoot = String(root).replaceAll('\\', '/').replace(/\/$/, '');
    if (raw === absoluteRoot) return '';
    if (raw.startsWith(`${absoluteRoot}/`)) return raw.slice(absoluteRoot.length + 1);
    return raw.replace(/^\.\//, '').replace(/^\//, '');
  }

  function syncCurrentSelection(force = false, notify = false) {
    try {
      const current = readCurrentSelection(app);
      const selection = current
        ? currentSelectionSummary(app, current, currentSelectionPath(app))
        : null;
      const signature = selectionSignature(selection);
      if (!force && signature === state.lastSelectionSignature) return;

      state.lastSelectionSignature = signature;
      const paths = new Set(
        (selection?.items || [])
          .map((item) => normalizedPath(item.path || item.abspath))
          .filter(Boolean),
      );
      const slugs = new Set(
        (selection?.items || [])
          .map((item) => String(item.slug || '').trim())
          .filter(Boolean),
      );

      for (const row of state.rows) {
        const rowPath = normalizedPath(row.file.path);
        const rowSlug = String(row.file.slug || '').trim();
        row.checkbox.checked = paths.has(rowPath) || Boolean(rowSlug && slugs.has(rowSlug));
      }
      updateSelectionStatus();

      if (notify) {
        if (!selection) {
          new Notice('No current selection exists for this vault session.');
        } else if (!selection.items.length) {
          new Notice('The current selection contains no usable files.');
        } else {
          new Notice(`Loaded ${selectedRows().length} of ${selection.items.length} current item(s).`);
        }
      }
    } catch (error) {
      console.error(error);
      if (notify) new Notice(`Could not load the current selection: ${error.message}`, 10000);
    }
  }

  function loadCurrentSelection() {
    syncCurrentSelection(true, true);
  }

  function saveCurrentSelection() {
    try {
      const rows = selectedRows();
      const result = writeCurrentSelection(app, {
        items: rows.map((row, index) => selectionItem(row.file, index)),
        source: {
          namespace: 'file-state',
          queryPath: '_control/panels/File State.md',
          title: 'File State',
        },
        action: 'save',
      });
      new Notice(`Saved ${result.selection.count} item(s) as the current selection.`);
    } catch (error) {
      console.error(error);
      new Notice(`Could not save the current selection: ${error.message}`, 10000);
    }
  }

  function commitCheckedFiles() {
    try {
      const paths = selectedRows().map((row) => row.file.path);
      if (!paths.length) throw new Error('Check at least one file to commit.');
      if (!amend.checked && !messageInput.value.trim()) {
        throw new Error('Enter a commit message.');
      }

      commitButton.disabled = true;
      const response = helperRequest(root, {
        operation: 'commit',
        paths,
        message: messageInput.value.trim(),
        amend: amend.checked,
      });

      const committedCount = Array.isArray(response.files) ? response.files.length : paths.length;
      const hash = response.commit ? String(response.commit).slice(0, 8) : 'unknown';
      new Notice(`Committed ${committedCount} file(s): ${hash}`);
      messageInput.value = '';
      refreshFiles();
    } catch (error) {
      console.error(error);
      new Notice(`Commit failed: ${error.message}`, 10000);
    } finally {
      commitButton.disabled = false;
    }
  }

  renderActiveFileState();
  refreshFiles();
  syncCurrentSelection(true, false);
  container.__fileStateSelectionTimer = setInterval(
    () => syncCurrentSelection(false, false),
    LIVE_SELECTION_INTERVAL_MS,
  );
}

await renderFileState({ app, dv, container: dv.container });
````
