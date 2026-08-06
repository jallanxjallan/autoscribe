"use strict";
const nodeRequire=typeof require==="function"?require:window.require;
const pathMod=nodeRequire("node:path"); const runtimeApp=globalThis.app;
const root=runtimeApp.vault.adapter.getBasePath?.()||runtimeApp.vault.adapter.basePath;
const load=p=>nodeRequire(pathMod.join(root,"_control",...p.split("/")));
const {el,clear,button}=load("scripts/lib/dom.js");
const {getFileManifest,appendClipboardCandidates}=load("scripts/lib/file-manifest.js");
const {history,restoreVersion,listFileStashes,stashCurrent,restoreFileStash,dropFileStash}=load("scripts/lib/file-git-history.js");

function refSummary(item){
 const exact=item.refs||[]; const transport=item.transport_refs||[]; const parts=[];
 if(exact.length) parts.push(`Points here: ${exact.join(", ")}`);
 if(transport.length) parts.push(`Transport branches containing it: ${transport.join(", ")}`);
 return parts.join("\n")||"No branch or tag points directly to this commit.";
}
function formatStashDate(value){try{return new Date(value).toLocaleString();}catch(_){return value;}}
async function renderFileHistory({app,container}){
 clear(container); const manifest=getFileManifest(app); let rows=[];
 const select=el("select");
 const add=button("Reload clipboard",async()=>{try{const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText());populate();loadHistory(n?`${n} added from clipboard`:"clipboard contained no new files");}catch(e){new Notice(e.message,10000);}});
 const clearBtn=button("Clear Clipboard List",()=>{manifest.candidates.clear();populate();loadHistory("clipboard list cleared");});
 const refresh=button("Refresh history",()=>loadHistory());
 const stashBtn=button("Stash Current",()=>stashSelected());
 const reminder=el("div"); const status=el("p"); const stashHost=el("div"); const host=el("div");
 const bar=el("div"); bar.style.display="flex";bar.style.gap=".5rem";bar.style.flexWrap="wrap";bar.append(select,add,clearBtn,refresh,stashBtn);
 container.append(el("h2",{text:"File History"}),reminder,bar,status,stashHost,host);
 function populate(){const chosen=select.value;select.replaceChildren();for(const item of manifest.candidates.values())select.append(el("option",{value:item.path,text:`${item.title} — ${item.path}`}));if([...select.options].some(o=>o.value===chosen))select.value=chosen;}
 function renderReminder(){
   const all=listFileStashes(app); reminder.replaceChildren();
   if(!all.length)return;
   reminder.style.padding=".65rem";reminder.style.marginBottom=".75rem";reminder.style.border="1px solid var(--color-orange)";reminder.style.borderRadius="6px";
   reminder.append(el("strong",{text:`Reminder: ${all.length} AutoScribe file stash${all.length===1?" is":"es are"} still saved.`}),el("div",{text:"Restore or drop them when finished so they are not forgotten."}));
 }
 function renderStashes(file){
   stashHost.replaceChildren(); const items=file?listFileStashes(app,file):[]; if(!items.length)return;
   stashHost.append(el("h3",{text:"Saved current versions"}));
   for(const item of items){
     const row=el("div");row.style.display="flex";row.style.gap=".5rem";row.style.alignItems="center";row.style.marginBottom=".4rem";row.style.flexWrap="wrap";
     row.append(el("code",{text:item.blob.slice(0,10)}),el("span",{text:formatStashDate(item.created_at)}));
     row.append(button("Restore stash",()=>restoreStash(file,item)),button("Drop stash",()=>dropStash(file,item)));
     stashHost.append(row);
   }
 }
 function loadHistory(note=""){
   host.replaceChildren();renderReminder();const file=select.value;renderStashes(file);
   if(!file){status.textContent=`The clipboard file list is empty${note?` · ${note}`:""}.`;stashBtn.disabled=true;return;} stashBtn.disabled=false;
   status.textContent="Reading this file’s complete Git history across all refs…";
   try{rows=history(app,file);status.textContent=`${rows.length} distinct file version${rows.length===1?"":"s"} found for ${file}${note?` · ${note}`:""}.`;}catch(e){status.textContent=e.message;return;}
   if(!rows.length){host.append(el("p",{text:"Git has no recorded version of this file."}));return;}
   const table=el("table");table.style.width="100%";const h=el("tr");for(const x of ["Version","When / who","What happened","Change","Git context","Action"])h.append(el("th",{text:x}));table.append(h);
   for(const item of rows){
     const b=button(item.is_current_file_version?"Current version":"Replace HEAD file",()=>restore(item,file));b.disabled=item.is_current_file_version;
     const version=el("div");version.append(el("strong",{text:item.kind}),el("br"),el("code",{text:item.hash.slice(0,10)}));if(item.is_current_file_version)version.append(el("br"),el("span",{text:"Current file version"}));
     const when=el("div");when.append(el("span",{text:item.date}),el("br"),el("small",{text:item.author}));const what=el("div");what.append(el("strong",{text:item.subject}));
     const delta=item.added||item.deleted?`${item.change} · +${item.added} / −${item.deleted}`:item.change;
     const context=el("details");const exact=(item.refs||[]).length;const trans=(item.transport_refs||[]).length;context.append(el("summary",{text:exact||trans?`${exact} direct ref${exact===1?"":"s"}; ${trans} transport branch${trans===1?"":"es"}`:"No direct refs"}),el("pre",{text:refSummary(item)}));
     const tr=el("tr");tr.append(el("td",{},version),el("td",{},when),el("td",{},what),el("td",{text:delta}),el("td",{},context),el("td",{},b));if(item.is_current_file_version)tr.style.fontWeight="600";table.append(tr);
   }
   host.append(table);
 }
 function stashSelected(){const file=select.value;if(!file)return;try{const item=stashCurrent(app,file);new Notice(`Current contents stashed as ${item.blob.slice(0,8)}. The reminder will remain until you restore or drop it.`,10000);loadHistory("current contents stashed");}catch(e){new Notice(`Stash failed: ${e.message}`,12000);}}
 function restoreStash(file,item){if(!window.confirm(`Restore the saved current contents from ${formatStashDate(item.created_at)}?\n\nThis will replace and stage the file. The stash will remain available until you drop it.`))return;try{restoreFileStash(app,file,item.id);new Notice("Stashed contents restored and staged. The stash remains saved.",10000);loadHistory("stash restored");}catch(e){new Notice(`Stash restore failed: ${e.message}`,12000);}}
 function dropStash(file,item){const short=item.blob.slice(0,8);const typed=window.prompt(`Permanently drop stash ${short}? Type ${short} to confirm.`);if(typed!==short){new Notice("Drop cancelled.");return;}try{dropFileStash(app,file,item.id);new Notice(`Dropped stash ${short}.`);loadHistory("stash dropped");}catch(e){new Notice(`Drop failed: ${e.message}`,12000);}}
 function restore(item,file){const short=item.hash.slice(0,8);if(!window.confirm(`Replace the current contents of ${file} with the version from ${item.date}?\n\nCommit: ${short}\n${item.subject}\n\nConsider using Stash Current first. The file must be clean. A safety tag will preserve the current HEAD.`))return;const typed=window.prompt(`Guardrail: type ${short} to confirm the replacement.`);if(typed!==short){new Notice("Replacement cancelled: confirmation did not match.");return;}try{const result=restoreVersion(app,file,item.hash);new Notice(`Restored ${short}. Safety tag: ${result.safety_tag}. Commit the staged replacement in File State.`,12000);loadHistory();}catch(e){new Notice(`Restore failed: ${e.message}`,12000);}}
 select.onchange=()=>loadHistory();
 try{const n=appendClipboardCandidates(app,manifest,await navigator.clipboard.readText());populate();loadHistory(n?`${n} added from clipboard`:"clipboard loaded");}catch(e){populate();loadHistory(`clipboard unavailable: ${e.message}`);}
}
module.exports={renderFileHistory};
