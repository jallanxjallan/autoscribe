"use strict";
const nodeRequire=typeof require==="function"?require:window.require;
const pathMod=nodeRequire("node:path"); const runtimeApp=globalThis.app;
const root=runtimeApp.vault.adapter.getBasePath?.()||runtimeApp.vault.adapter.basePath;
const load=p=>nodeRequire(pathMod.join(root,"_control",...p.split("/")));
const {el,clear,button}=load("scripts/lib/dom.js");
const {getFileManifest,appendClipboardCandidates}=load("scripts/lib/file-manifest.js");
const {history,restoreVersion,listFileStashes,stashCurrent,restoreFileStash,dropFileStash}=load("scripts/lib/file-git-history.js");
const {notify}=load("scripts/lib/notify.js");
const {loadConfig}=load("scripts/lib/config-loader.js");
const ui=()=>loadConfig("ui");

function refSummary(item){
 const exact=item.refs||[]; const transport=item.transport_refs||[]; const parts=[];
 if(exact.length) parts.push(`Points here: ${exact.join(", ")}`);
 if(transport.length) parts.push(`Transport branches containing it: ${transport.join(", ")}`);
 return parts.join("\n")||"No branch or tag points directly to this commit.";
}
function formatStashDate(value){try{const raw=String(value||"");const date=/^\d+$/.test(raw)?new Date(Number(raw)*1000):new Date(raw);return date.toLocaleString();}catch(_){return value;}}
async function renderFileHistory({app,container}){
 clear(container); const manifest=getFileManifest(app); let rows=[];
 const select=el("select");
 const add=button("Reload clipboard",async()=>{notify("Reloading clipboard…");try{const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText());populate();await loadHistory(n?`${n} added from clipboard`:"clipboard contained no new files");notify(n?`Clipboard reloaded: ${n} file(s) added.`:"Clipboard reloaded: no new files.");}catch(e){notify(e.message,10000);}});
 const clearBtn=button("Clear Clipboard List",async()=>{notify("Clearing clipboard list…");manifest.candidates.clear();populate();await loadHistory("clipboard list cleared");notify("Clipboard list cleared.");});
 const refresh=button("Refresh history",async()=>{notify("Refreshing file history…");await loadHistory("",true);});
 const stashBtn=button("Stash Current",async()=>stashSelected());
 const reminder=el("div"); const status=el("p"); const stashHost=el("div"); const host=el("div");
 const bar=el("div"); bar.style.display="flex";bar.style.gap=".5rem";bar.style.flexWrap="wrap";bar.append(select,add,clearBtn,refresh,stashBtn);
 container.append(el("h2",{text:"File History"}),reminder,bar,status,stashHost,host);
 function populate(){const chosen=select.value;select.replaceChildren();for(const item of manifest.candidates.values())select.append(el("option",{value:item.path,text:`${item.title} — ${item.path}`}));if([...select.options].some(o=>o.value===chosen))select.value=chosen;}
 async function renderReminder(){
   const all=await listFileStashes(app); reminder.replaceChildren();
   if(!all.length)return;
   reminder.style.padding=".65rem";reminder.style.marginBottom=".75rem";reminder.style.border="1px solid var(--color-orange)";reminder.style.borderRadius="6px";
   reminder.append(el("strong",{text:`Reminder: ${all.length} AutoScribe file stash${all.length===1?" is":"es are"} still saved.`}),el("div",{text:"Restore or drop them when finished so they are not forgotten."}));
 }
 async function renderStashes(file){
   stashHost.replaceChildren(); const items=file?await listFileStashes(app,file):[]; if(!items.length)return;
   stashHost.append(el("h3",{text:"Saved current versions"}));
   for(const item of items){
     const row=el("div");row.style.display="flex";row.style.gap=".5rem";row.style.alignItems="center";row.style.marginBottom=".4rem";row.style.flexWrap="wrap";
     row.append(el("code",{text:item.blob.slice(0,10)}),el("span",{text:formatStashDate(item.created_at)}));
     row.append(button("Restore stash",async()=>restoreStash(file,item)),button("Drop stash",async()=>dropStash(file,item)));
     stashHost.append(row);
   }
 }
 async function loadHistory(note="",notifyUser=false){
   host.replaceChildren();await renderReminder();const file=select.value;await renderStashes(file);
   if(!file){status.textContent=`The clipboard file list is empty${note?` · ${note}`:""}.`;stashBtn.disabled=true;return;} stashBtn.disabled=false;
   status.textContent="Reading this file’s complete Git history across all refs…";
   try{rows=await history(app,file);status.textContent=`${rows.length} distinct file version${rows.length===1?"":"s"} found for ${file}${note?` · ${note}`:""}.`;if(notifyUser)notify(`File history refreshed: ${rows.length} version(s).`);}catch(e){status.textContent=e.message;if(notifyUser)notify(`History refresh failed: ${e.message}`,10000);return;}
   if(!rows.length){host.append(el("p",{text:"Git has no recorded version of this file."}));return;}
   const table=el("table");table.style.width="100%";const h=el("tr");for(const x of (ui().file_history_columns || []))h.append(el("th",{text:x}));table.append(h);
   for(const item of rows){
     const b=button(item.is_current_file_version?"Current version":"Replace HEAD file",async()=>restore(item,file));b.disabled=item.is_current_file_version;
     const version=el("div");version.append(el("strong",{text:item.kind}),el("br"),el("code",{text:item.hash.slice(0,10)}));if(item.is_current_file_version)version.append(el("br"),el("span",{text:"Current file version"}));
     const when=el("div");when.append(el("span",{text:item.date}),el("br"),el("small",{text:item.author}));const what=el("div");what.append(el("strong",{text:item.subject}));
     const delta=item.added||item.deleted?`${item.change} · +${item.added} / −${item.deleted}`:item.change;
     const context=el("details");const exact=(item.refs||[]).length;const trans=(item.transport_refs||[]).length;context.append(el("summary",{text:exact||trans?`${exact} direct ref${exact===1?"":"s"}; ${trans} transport branch${trans===1?"":"es"}`:"No direct refs"}),el("pre",{text:refSummary(item)}));
     const tr=el("tr");tr.append(el("td",{},version),el("td",{},when),el("td",{},what),el("td",{text:delta}),el("td",{},context),el("td",{},b));if(item.is_current_file_version)tr.style.fontWeight="600";table.append(tr);
   }
   host.append(table);
 }
 async function stashSelected(){const file=select.value;if(!file)return;notify("Stashing current file contents…");try{const item=await stashCurrent(app,file);notify(`Current contents stashed as ${item.blob.slice(0,8)}. The reminder will remain until you restore or drop it.`,10000);await loadHistory("current contents stashed");}catch(e){notify(`Stash failed: ${e.message}`,12000);}}
 async function restoreStash(file,item){if(!window.confirm(`Restore the saved current contents from ${formatStashDate(item.created_at)}?\n\nThis will replace and stage the file. The stash will remain available until you drop it.`))return;notify("Restoring stashed contents…");try{await restoreFileStash(app,file,item.id);notify("Stashed contents restored and staged. The stash remains saved.",10000);await loadHistory("stash restored");}catch(e){notify(`Stash restore failed: ${e.message}`,12000);}}
 async function dropStash(file,item){const short=item.blob.slice(0,8);const typed=window.prompt(`Permanently drop stash ${short}? Type ${short} to confirm.`);if(typed!==short){notify("Drop cancelled.");return;}notify(`Dropping stash ${short}…`);try{await dropFileStash(app,file,item.id);notify(`Dropped stash ${short}.`);await loadHistory("stash dropped");}catch(e){notify(`Drop failed: ${e.message}`,12000);}}
 async function restore(item,file){const short=item.hash.slice(0,8);if(!window.confirm(`Replace the current contents of ${file} with the version from ${item.date}?\n\nCommit: ${short}\n${item.subject}\n\nConsider using Stash Current first. The file must be clean. A safety tag will preserve the current HEAD.`))return;const typed=window.prompt(`Guardrail: type ${short} to confirm the replacement.`);if(typed!==short){notify("Replacement cancelled: confirmation did not match.");return;}notify(`Restoring ${short} into the working file…`);try{const result=await restoreVersion(app,file,item.hash);notify(`Restored ${short}. Safety tag: ${result.safety_tag}. Commit the staged replacement in File State.`,12000);await loadHistory();}catch(e){notify(`Restore failed: ${e.message}`,12000);}}
 select.onchange=async()=>loadHistory();
 try{const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText());populate();await loadHistory(n?`${n} added from clipboard`:"clipboard loaded");}catch(e){populate();await loadHistory(`clipboard unavailable: ${e.message}`);}
}
module.exports={renderFileHistory};
