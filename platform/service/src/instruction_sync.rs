use crate::{ServiceError, ServiceResult, dispatch::sha256_hex};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::{BTreeMap, BTreeSet, HashMap}, fs, path::{Path, PathBuf}, process::Command, time::UNIX_EPOCH};

#[derive(Debug, Clone)]
pub struct LocalInstruction {
    pub slug: String,
    pub title: String,
    pub scope: String,
    pub component: String,
    pub relative_path: String,
    pub body: String,
    pub modified_ns: u128,
    pub size: u64,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncItem { pub slug:String, pub path:String, pub status:String, pub reason:String }
#[derive(Debug)]
pub struct SyncPlan { pub upload:Vec<LocalInstruction>, pub items:Vec<SyncItem>, pub hashes_compared:usize }

/// Vault-wide slug index built once at an explicit refresh boundary.
/// Slugs are durable identity; paths are derived state. Duplicate slugs are rejected
/// before any refresh consumer sees a partial or ambiguous snapshot.
pub type SlugIndex = BTreeMap<String, PathBuf>;

pub fn build_slug_index(root:&Path)->ServiceResult<SlugIndex>{
    let root=root.canonicalize().map_err(io)?;
    let output=Command::new("rg").current_dir(&root)
        .args(["--files-with-matches","--glob","*.md","--glob","!.git/**","--glob","!.obsidian/**","--glob","!_control/**","--glob","!target/**",r"^slug:\s*[^[:space:]]+", "."])
        .output().map_err(io)?;
    if !output.status.success() && output.status.code()!=Some(1){
        return Err(ServiceError::Io(format!("rg slug index failed: {}",String::from_utf8_lossy(&output.stderr).trim())));
    }
    let mut index=SlugIndex::new();
    for line in String::from_utf8_lossy(&output.stdout).lines(){
        let relative=PathBuf::from(line.trim_start_matches("./"));
        let text=fs::read_to_string(root.join(&relative)).map_err(io)?;
        let Some((frontmatter,_))=split_frontmatter(&text) else{continue};
        let slug=frontmatter.get("slug").map(String::as_str).unwrap_or("").trim();
        if slug.is_empty(){continue;}
        if let Some(previous)=index.insert(slug.to_string(),relative.clone()){
            return Err(ServiceError::Conflict(format!(
                "duplicate slug: {slug}: {}, {}",previous.display(),relative.display()
            )));
        }
    }
    Ok(index)
}

pub fn scan_indexed_instructions(root:&Path,index:&SlugIndex)->ServiceResult<Vec<LocalInstruction>>{
    let root=root.canonicalize().map_err(io)?;
    let mut found=Vec::new();
    for (slug,relative) in index{
        let text=fs::read_to_string(root.join(relative)).map_err(io)?;
        let Some((frontmatter,_))=split_frontmatter(&text) else{continue};
        if !is_instruction(&frontmatter){continue;}
        let item=read_instruction(&root,relative)?;
        if item.slug.as_str()!=slug.as_str(){
            return Err(ServiceError::Conflict(format!(
                "slug index changed during refresh: expected {slug}, found {} in {}",item.slug,relative.display()
            )));
        }
        found.push(item);
    }
    Ok(found)
}

/// Resolve Markdown records by authoritative slug using ripgrep. Paths are derived state.
pub fn resolve_slug_paths(root:&Path, requested:&BTreeSet<String>)->ServiceResult<BTreeMap<String,Vec<PathBuf>>>{
    if requested.is_empty(){return Ok(BTreeMap::new());}
    let pattern=format!(r"^slug:\s*({})\s*$",requested.iter().map(|s|regex_escape(s)).collect::<Vec<_>>().join("|"));
    let output=Command::new("rg")
        .current_dir(root)
        .args(["--files-with-matches","--glob","*.md","--glob","!.git/**","--glob","!.obsidian/**","--glob","!_control/**","--glob","!target/**",&pattern,"."])
        .output().map_err(io)?;
    if !output.status.success() && output.status.code()!=Some(1){
        return Err(ServiceError::Io(format!("rg slug lookup failed: {}",String::from_utf8_lossy(&output.stderr).trim())));
    }
    let mut matches=BTreeMap::<String,Vec<PathBuf>>::new();
    for line in String::from_utf8_lossy(&output.stdout).lines(){
        let relative=PathBuf::from(line.trim_start_matches("./"));
        let text=match fs::read_to_string(root.join(&relative)){Ok(v)=>v,Err(_)=>continue};
        let Some((frontmatter,_))=split_frontmatter(&text) else{continue};
        let slug=frontmatter.get("slug").map(String::as_str).unwrap_or("").trim();
        if requested.contains(slug){matches.entry(slug.to_string()).or_default().push(relative);}
    }
    Ok(matches)
}

pub fn scan_slugs(root:&Path, requested:&BTreeSet<String>)->ServiceResult<Vec<LocalInstruction>>{
    let root=root.canonicalize().map_err(io)?;
    let matches=resolve_slug_paths(&root,requested)?;
    let mut found=Vec::new();
    for slug in requested{
        let paths=matches.get(slug).cloned().unwrap_or_default();
        match paths.as_slice(){
            []=>continue,
            [relative]=>found.push(read_instruction(&root,relative)?),
            many=>return Err(ServiceError::Conflict(format!("duplicate instruction slug: {slug}: {}",many.iter().map(|p|p.display().to_string()).collect::<Vec<_>>().join(", ")))),
        }
    }
    Ok(found)
}

/// Compatibility/manual command. Explicit catalogue refreshes build the slug index
/// themselves and hand that single snapshot to their consumers.
pub fn scan(root:&Path)->ServiceResult<Vec<LocalInstruction>>{
    let index=build_slug_index(root)?;
    scan_indexed_instructions(root,&index)
}

fn read_instruction(root:&Path,relative:&Path)->ServiceResult<LocalInstruction>{
    let path=root.join(relative);
    let text=fs::read_to_string(&path).map_err(io)?;
    let Some((frontmatter,body))=split_frontmatter(&text) else{return Err(ServiceError::InvalidInput(format!("instruction has no frontmatter: {}",relative.display())))};
    if !is_instruction(&frontmatter){return Err(ServiceError::InvalidInput(format!("slug does not identify an instruction: {}",relative.display())));}
    let slug=frontmatter.get("slug").map(String::as_str).unwrap_or("").trim();
    if slug.is_empty(){return Err(ServiceError::InvalidInput(format!("instruction has no slug: {}",relative.display())));}
    if body.trim().is_empty(){return Err(ServiceError::InvalidInput(format!("instruction body is blank: {}",relative.display())));}
    let metadata=fs::metadata(&path).map_err(io)?;
    let modified_ns=metadata.modified().map_err(io)?.duration_since(UNIX_EPOCH).map_err(io)?.as_nanos();
    let title=frontmatter.get("title").cloned().unwrap_or_else(||path.file_stem().unwrap_or_default().to_string_lossy().into_owned());
    let component=frontmatter.get("component").or_else(||frontmatter.get("class")).cloned().unwrap_or_default().to_lowercase();
    let scope=frontmatter.get("scope").cloned().filter(|v|!v.trim().is_empty()).unwrap_or_else(||scope_from_slug(slug,&component));
    Ok(LocalInstruction{slug:slug.to_string(),title,scope,component,relative_path:relative.to_string_lossy().replace('\\',"/"),body:body.to_string(),modified_ns,size:metadata.len()})
}

pub fn plan(local:Vec<LocalInstruction>,manifest:&Value)->ServiceResult<SyncPlan>{
    let remote=manifest.get("instructions").and_then(Value::as_object).ok_or_else(||ServiceError::InvalidInput("instruction manifest has no instructions object".into()))?;
    let mut upload=Vec::new();let mut items=Vec::new();let mut hashes_compared=0;
    for item in local{let Some(server)=remote.get(&item.slug) else{items.push(row(&item,"upload","missing remotely"));upload.push(item);continue};
        let remote_mtime=integer(server.get("source_modified_ns"));let remote_size=integer(server.get("source_size"));
        if remote_mtime==Some(item.modified_ns)&&remote_size==Some(item.size as u128){items.push(row(&item,"current","timestamp and size match"));continue;}
        if server.get("title").and_then(Value::as_str).is_some_and(|title|title!=item.title){items.push(row(&item,"upload","instruction title differs"));upload.push(item);continue;}
        hashes_compared+=1;let local_hash=sha256_hex(item.body.trim().as_bytes());let remote_hash=server.get("content_sha256").and_then(Value::as_str).unwrap_or("");
        if local_hash==remote_hash{items.push(row(&item,"current","content hash matches"));}else{items.push(row(&item,"upload","metadata and content differ"));upload.push(item);}
    }
    Ok(SyncPlan{upload,items,hashes_compared})
}

pub fn upload_record(item:&LocalInstruction)->Value{serde_json::json!({"type":"instruction","identity":item.slug,"content":item.body,"extra":{"title":item.title,"scope":item.scope,"component":item.component,"source_path":item.relative_path,"source_modified_ns":item.modified_ns.to_string(),"source_size":item.size}})}
fn row(item:&LocalInstruction,status:&str,reason:&str)->SyncItem{SyncItem{slug:item.slug.clone(),path:item.relative_path.clone(),status:status.into(),reason:reason.into()}}
fn integer(value:Option<&Value>)->Option<u128>{value.and_then(|v|v.as_u64().map(u128::from).or_else(||v.as_str()?.parse().ok()))}
fn is_instruction(frontmatter:&HashMap<String,String>)->bool{["record","type","kind"].into_iter().filter_map(|k|frontmatter.get(k)).any(|v|v.eq_ignore_ascii_case("instruction"))}
fn scope_from_slug(slug:&str,component:&str)->String{match slug.split('.').next().unwrap_or(""){"std"=>"standing","rol"=>"role","ctx"=>"context","tsk"=>"task",_=>component}.to_string()}
fn regex_escape(value:&str)->String{let mut out=String::new();for c in value.chars(){if r".[]{}()*+?^$|\\".contains(c){out.push('\\');}out.push(c);}out}
fn split_frontmatter(text:&str)->Option<(HashMap<String,String>,&str)>{if !text.starts_with("---\n")&&!text.starts_with("---\r\n"){return None;}let mut offset=text.find('\n')?+1;let mut fields=HashMap::new();for line in text[offset..].split_inclusive('\n'){let clean=line.trim_end_matches(['\r','\n']);if clean=="---"{offset+=line.len();return Some((fields,&text[offset..]));}if let Some((key,value))=clean.split_once(':'){fields.insert(key.trim().to_string(),value.trim().trim_matches(['\'','"']).to_string());}offset+=line.len();}None}
fn io(error:impl std::fmt::Display)->ServiceError{ServiceError::Io(error.to_string())}
