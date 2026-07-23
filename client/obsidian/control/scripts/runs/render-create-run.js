const path = require('path');
const { spawnSync } = require('child_process');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { loadControlSnapshot, snapshotList } = require('../lib/control-loader.js');

const PYTHON_EXECUTABLE = '/home/jeremy/Python3.13Env/bin/python';
const DISPATCH_HELPER = path.join(__dirname, 'dispatch_run.py');

function helperRequest(root, request) {
  const result = spawnSync(PYTHON_EXECUTABLE, [DISPATCH_HELPER], {
    input: JSON.stringify({ ...request, vault_root: root }),
    encoding: 'utf8',
    cwd: root,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 120000,
  });
  let response;
  try {
    response = JSON.parse(result.stdout || '{}');
  } catch {
    const detail = (result.stderr || result.stdout || `exit status ${result.status}`).trim();
    throw new Error(`Dispatch helper returned invalid JSON: ${detail || '(empty output)'}`);
  }
  if (result.error) throw new Error(`Dispatch helper could not start: ${result.error.message}`);
  if (result.status !== 0 || response?.ok === false) {
    throw new Error(String(response?.error || result.stderr || result.stdout || `exit status ${result.status}`).trim());
  }
  return response;
}

function loadPlans() {
  const snapshot = loadControlSnapshot();
  if (snapshot.error) {
    const detail = snapshot.stderr ? `; ${snapshot.stderr}` : '';
    throw new Error(`Could not load AutoScribe control snapshot: ${snapshot.error}${detail}`);
  }
  return snapshotList(snapshot.data, 'plans')
    .map((record) => ({
      ...record,
      ttl: Number.isFinite(Number(record.ttl)) ? Number(record.ttl) : -2,
      label: record.label || record.slug,
    }))
    .filter((record) => record.ttl !== -2)
    .sort((a, b) => b.ttl - a.ttl || String(a.label).localeCompare(String(b.label)));
}

function planOptionText(plan) {
  const ttl = plan.ttl < 0 ? 'persistent' : `${plan.ttl}s TTL`;
  return `${plan.label} — ${plan.slug} (${ttl})`;
}

function commitOptionText(commit) {
  const date = new Date(Number(commit.timestamp || 0) * 1000).toLocaleString();
  return `${commit.short_hash} — ${commit.subject} (${commit.count} file${commit.count === 1 ? '' : 's'}, ${date})`;
}

function renderCommitFiles(container, state) {
  container.innerHTML = '';
  const files = state?.files || [];
  if (!files.length) {
    container.appendChild(el('p', { text: 'The selected commit contains no dispatchable files.' }));
    return;
  }
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'File', 'State', 'Current version'].map((heading) => el('th', { text: heading }))));
  files.forEach((item, index) => {
    const version = item.at_selected_commit ? 'selected commit' : 'changed later';
    table.appendChild(el('tr', {}, [
      el('td', { text: index + 1 }),
      el('td', { text: item.path }),
      el('td', { text: item.git_status || item.repo_state || 'unknown' }),
      el('td', { text: version }),
    ]));
  });
  container.appendChild(table);
  container.appendChild(el('p', {
    text: 'Dispatch uses the file contents stored in the selected commit, regardless of current working-tree state.',
  }));
}

function readableMessage(response) {
  const result = response?.result || {};
  const lines = [];
  if (response?.message) lines.push(String(response.message));
  if (result.tag?.name) lines.push(`Inflight tag: ${result.tag.name}`);
  if (result.pipeline_output) lines.push(String(result.pipeline_output));
  return lines.join('\n') || JSON.stringify(response, null, 2);
}

async function renderCreateRun({ app, container }) {
  clear(container);
  const root = vaultRoot(app);
  let plans = loadPlans();
  let commits = [];
  let selectedState = null;

  container.appendChild(el('h2', { text: 'Dispatch Files' }));

  const planSelect = el('select');
  planSelect.style.flex = '1';
  const commitSelect = el('select');
  commitSelect.style.flex = '1';
  const filesBox = el('div');
  const output = el('pre', { text: '' });
  output.style.whiteSpace = 'pre-wrap';

  function fillPlans(preferred = '') {
    planSelect.innerHTML = '';
    for (const plan of plans) planSelect.appendChild(el('option', { value: plan.slug, text: planOptionText(plan) }));
    planSelect.disabled = !plans.length;
    if (!plans.length) planSelect.appendChild(el('option', { text: 'No uploaded plans found.' }));
    if (preferred && plans.some((plan) => plan.slug === preferred)) planSelect.value = preferred;
  }

  function fillCommits(preferred = '') {
    commitSelect.innerHTML = '';
    for (const commit of commits) commitSelect.appendChild(el('option', { value: commit.hash, text: commitOptionText(commit) }));
    commitSelect.disabled = !commits.length;
    if (!commits.length) commitSelect.appendChild(el('option', { text: 'No untagged user commits found.' }));
    if (preferred && commits.some((commit) => commit.hash === preferred)) commitSelect.value = preferred;
  }

  function loadCommitState() {
    const commit = commitSelect.value;
    selectedState = null;
    filesBox.innerHTML = '';
    if (!commit) return;
    const response = helperRequest(root, { operation: 'commit_state', commit });
    selectedState = response.result;
    renderCommitFiles(filesBox, selectedState);
  }

  function refreshAll() {
    const previousPlan = planSelect.value;
    const previousCommit = commitSelect.value;
    plans = loadPlans();
    commits = helperRequest(root, { operation: 'list_commits', limit: 100 }).result || [];
    fillPlans(previousPlan);
    fillCommits(previousCommit);
    loadCommitState();
  }

  const planRefresh = button('Refresh plans', () => {
    try {
      const selected = planSelect.value;
      plans = loadPlans();
      fillPlans(selected);
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Plan refresh failed: ${error.message}`, 10000);
    }
  });
  const commitRefresh = button('Refresh commits', () => {
    try {
      const selected = commitSelect.value;
      commits = helperRequest(root, { operation: 'list_commits', limit: 100 }).result || [];
      fillCommits(selected);
      loadCommitState();
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Commit refresh failed: ${error.message}`, 10000);
    }
  });

  const planRow = el('div');
  planRow.style.display = 'flex';
  planRow.style.gap = '0.5rem';
  planRow.style.alignItems = 'center';
  planRow.append(el('label', {}, ['Plan ', planSelect]), planRefresh);

  const commitRow = el('div');
  commitRow.style.display = 'flex';
  commitRow.style.gap = '0.5rem';
  commitRow.style.alignItems = 'center';
  commitRow.append(el('label', {}, ['Commit ', commitSelect]), commitRefresh);

  commitSelect.addEventListener('change', () => {
    try {
      loadCommitState();
      output.textContent = '';
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Could not load commit: ${error.message}`, 10000);
    }
  });

  const dispatchBtn = button('Dispatch Run', () => {
    try {
      const planSlug = planSelect.value;
      const commit = commitSelect.value;
      if (!planSlug) throw new Error('Select an uploaded plan.');
      if (!commit) throw new Error('Select a commit.');
      if (!selectedState?.files?.length) throw new Error('The selected commit contains no files.');

      dispatchBtn.disabled = true;
      output.textContent = 'Dispatching…';
      const response = helperRequest(root, { operation: 'dispatch', plan_slug: planSlug, commit });
      output.textContent = readableMessage(response);
      new Notice('Dispatch complete.');
      refreshAll();
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Dispatch failed: ${error.message}`, 10000);
      console.error(error);
    } finally {
      dispatchBtn.disabled = false;
    }
  });

  container.append(planRow, commitRow, filesBox, dispatchBtn, output);
  try {
    refreshAll();
  } catch (error) {
    output.textContent = error.message;
    new Notice(`Dispatch panel failed: ${error.message}`, 10000);
  }
}

module.exports = { renderCreateRun };
