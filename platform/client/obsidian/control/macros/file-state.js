"use strict";
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const root = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const load = (p) => nodeRequire(pathMod.join(root, "_control", ...p.split("/")));
const { el, clear, button } = load("scripts/lib/dom.js");
const { getFileManifest, appendClipboardCandidates } = load("scripts/lib/file-manifest.js");
const { liveState } = load("scripts/lib/file-git-history.js");
const { gitFiles } = load("scripts/lib/git-service.js");
const { notify } = load("scripts/lib/notify.js");
const { loadConfig } = load("scripts/lib/config-loader.js");
const ui = () => loadConfig("ui");
const workflow = () => loadConfig("workflow");

async function renderFileState({ app, container }) {
  clear(container);
  const manifest = getFileManifest(app);
  const state = { rows: [], busy: false };
  const title = el("h2", { text: "File State" });
  const status = el("p", { text: "Reading Git…" });
  const toolbar = el("div"); toolbar.style.display="flex"; toolbar.style.gap=".5rem"; toolbar.style.flexWrap="wrap";
  const add = button("Reload clipboard", async()=>{ notify("Reloading clipboard…"); try { const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText()); await refresh(n ? `${n} added from clipboard` : "clipboard contained no new files"); notify(n ? `Clipboard reloaded: ${n} file(s) added.` : "Clipboard reloaded: no new files."); } catch(e){ notify(e.message,10000); } });
  const clearBtn = button("Clear Clipboard List", async()=>{ notify("Clearing clipboard list…"); manifest.candidates.clear(); await refresh("clipboard list cleared"); notify("Clipboard list cleared."); });
  const refreshBtn = button("Refresh Git state", async()=>{ notify("Refreshing Git state…"); await refresh(); notify(`Git state refreshed: ${state.rows.length} file(s).`); });
  toolbar.append(add, clearBtn, refreshBtn);
  const host=el("div");
  const commit=el("div"); commit.style.display="grid"; commit.style.gap=".6rem"; commit.style.marginTop="1rem";
  const msg=el("input", { placeholder:"Commit description" });
  const type=el("select"); for (const [value, mode] of Object.entries(workflow().commit?.modes || {})) type.append(el("option",{value,text:String(mode.label || value)}));
  const commitBtn=button("Commit selected files", doCommit); commitBtn.classList.add("mod-cta");
  commit.append(msg,type,commitBtn); container.append(title,toolbar,status,host,commit);

  function selected(){ return state.rows.filter(r=>r.checkbox.checked).map(r=>r.item); }
  function render(){ host.replaceChildren(); const table=el("table"); table.style.width="100%"; const h=el("tr"); for(const x of (ui().file_state_columns || [])) h.append(el("th",{text:x})); table.append(h);
    for(const row of state.rows){ const tr=el("tr"); const link=el("a",{href:row.item.path,text:row.item.title}); link.onclick=async e=>{e.preventDefault(); const file=app.vault.getAbstractFileByPath(row.item.path); if(!file)return; const leaf=app.workspace.getLeaf("tab"); await leaf.openFile(file,{active:true}); app.workspace.revealLeaf(leaf);};
      tr.append(el("td",{},row.checkbox),el("td",{},link),el("td",{text:row.git.status}),el("td",{text:row.git.latest_commit?`${row.git.latest_commit.hash.slice(0,8)} · ${row.git.latest_commit.subject}`:String(ui().missing_value || "—")})); table.append(tr); }
    host.append(table); commitBtn.disabled=!selected().length;
  }
  async function refresh(note="") { state.rows=[]; for(const item of manifest.candidates.values()){ try{ state.rows.push({item,git:await liveState(app,item.path),checkbox:el("input",{type:"checkbox"})}); }catch(e){ state.rows.push({item,git:{status:`ERROR: ${e.message}`,latest_commit:null},checkbox:el("input",{type:"checkbox"})}); } }
    for(const r of state.rows){ r.checkbox.checked=Boolean(r.item.selected); r.checkbox.onchange=()=>{r.item.selected=r.checkbox.checked;render();}; }
    status.textContent=state.rows.length?`${state.rows.length} manifest file(s); Git read live${note?` · ${note}`:""}.`:`The Dispatch Run manifest is empty.`; render(); }
  async function doCommit(){ try{ const items=selected(); if(!items.length) throw new Error("Select at least one file."); if(!msg.value.trim()) throw new Error("Enter a commit description."); notify(`Committing ${items.length} file(s)…`); state.busy=true; commitBtn.disabled=true;
      const resolved=await gitFiles(app,"inspect",{items}); const rows=resolved.items||[]; const blocked=rows.filter(x=>x.error||x.problem||x.committable===false); if(blocked.length) throw new Error("One or more selected files cannot be committed.");
      const kind=type.value; const result=await gitFiles(app,"commit",{message:msg.value.trim(),purpose:kind,paths:rows.map(row=>row.path)});
      notify(`Committed ${result.count||rows.length} file(s): ${String(result.commit?.hash||result.commit||"").slice(0,8)}`); msg.value=""; await refresh();
    }catch(e){notify(`Commit failed: ${e.message}`,10000);}finally{state.busy=false;commitBtn.disabled=!selected().length;} }
  try { const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText()); await refresh(n ? `${n} added from clipboard` : "clipboard loaded"); } catch(e) { await refresh(`clipboard unavailable: ${e.message}`); }
}

module.exports = async function file_state(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relativePath) => nodeRequire(path.join(base, "_control", ...relativePath.split("/")));
  const { openWorkflowModal } = load("scripts/lib/workflow-modal.js");
  return openWorkflowModal({
    app,
    title: "File State",
    render: (container) => renderFileState({ app, container }),
  });
};
