use crate::{ServiceError, ServiceResult, dispatch::sha256_hex};
use serde::Serialize;
use serde_json::Value;
use std::{collections::{BTreeMap, HashMap}, fs, path::{Path, PathBuf}, time::UNIX_EPOCH};

#[derive(Debug, Clone)]
pub struct LocalInstruction {
    pub slug: String,
    pub title: String,
    pub relative_path: String,
    pub body: String,
    pub modified_ns: u128,
    pub size: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct SyncItem { pub slug:String, pub path:String, pub status:String, pub reason:String }

pub struct SyncPlan { pub upload:Vec<LocalInstruction>, pub items:Vec<SyncItem>, pub hashes_compared:usize }

pub fn scan(root:&Path)->ServiceResult<Vec<LocalInstruction>> {
    let root=root.canonicalize().map_err(io)?;
    let mut files=Vec::new();collect_markdown(&root,&mut files)?;files.sort();
    let mut found=BTreeMap::new();
    for path in files {
        let text=fs::read_to_string(&path).map_err(io)?;
        let Some((frontmatter,body))=split_frontmatter(&text) else {continue};
        if frontmatter.get("type").map(String::as_str)!=Some("instruction"){continue;}
        let slug=frontmatter.get("slug").map(String::as_str).unwrap_or("").trim();
        if slug.is_empty(){return Err(ServiceError::InvalidInput(format!("instruction has no slug: {}",path.display())));}
        if found.contains_key(slug){return Err(ServiceError::Conflict(format!("duplicate instruction slug: {slug}")));}
        if body.trim().is_empty(){return Err(ServiceError::InvalidInput(format!("instruction body is blank: {}",path.display())));}
        let metadata=fs::metadata(&path).map_err(io)?;
        let modified_ns=metadata.modified().map_err(io)?.duration_since(UNIX_EPOCH).map_err(io)?.as_nanos();
        let relative=path.strip_prefix(&root).map_err(io)?.to_string_lossy().replace('\\',"/");
        let title=frontmatter.get("title").cloned().unwrap_or_else(||path.file_stem().unwrap_or_default().to_string_lossy().into_owned());
        found.insert(slug.to_string(),LocalInstruction{slug:slug.to_string(),title,relative_path:relative,body:body.to_string(),modified_ns,size:metadata.len()});
    }
    Ok(found.into_values().collect())
}

pub fn plan(local:Vec<LocalInstruction>,manifest:&Value)->ServiceResult<SyncPlan>{
    let remote=manifest.get("instructions").and_then(Value::as_object).ok_or_else(||ServiceError::InvalidInput("instruction manifest has no instructions object".into()))?;
    let mut upload=Vec::new();let mut items=Vec::new();let mut hashes_compared=0;
    for item in local {let Some(server)=remote.get(&item.slug) else {items.push(row(&item,"upload","missing remotely"));upload.push(item);continue};
        let remote_mtime=integer(server.get("source_modified_ns"));let remote_size=integer(server.get("source_size"));
        if remote_mtime==Some(item.modified_ns)&&remote_size==Some(item.size as u128){items.push(row(&item,"current","timestamp and size match"));continue;}
        if server.get("title").and_then(Value::as_str).is_some_and(|title|title!=item.title){items.push(row(&item,"upload","instruction title differs"));upload.push(item);continue;}
        hashes_compared+=1;let local_hash=sha256_hex(item.body.trim().as_bytes());let remote_hash=server.get("content_sha256").and_then(Value::as_str).unwrap_or("");
        if local_hash==remote_hash{items.push(row(&item,"current","content hash matches"));}else{items.push(row(&item,"upload","metadata and content differ"));upload.push(item);}
    }
    Ok(SyncPlan{upload,items,hashes_compared})
}

pub fn upload_record(item:&LocalInstruction)->Value{serde_json::json!({"type":"instruction","identity":item.slug,"content":item.body,"extra":{"title":item.title,"source_path":item.relative_path,"source_modified_ns":item.modified_ns.to_string(),"source_size":item.size}})}
fn row(item:&LocalInstruction,status:&str,reason:&str)->SyncItem{SyncItem{slug:item.slug.clone(),path:item.relative_path.clone(),status:status.into(),reason:reason.into()}}
fn integer(value:Option<&Value>)->Option<u128>{value.and_then(|v|v.as_u64().map(u128::from).or_else(||v.as_str()?.parse().ok()))}
fn collect_markdown(root:&Path,output:&mut Vec<PathBuf>)->ServiceResult<()>{for entry in fs::read_dir(root).map_err(io)?{let path=entry.map_err(io)?.path();if path.is_dir(){collect_markdown(&path,output)?;}else if path.extension().and_then(|x|x.to_str()).is_some_and(|x|x.eq_ignore_ascii_case("md")){output.push(path);}}Ok(())}
fn split_frontmatter(text:&str)->Option<(HashMap<String,String>,&str)>{if !text.starts_with("---\n")&&!text.starts_with("---\r\n"){return None;}let mut offset=text.find('\n')?+1;let mut fields=HashMap::new();for line in text[offset..].split_inclusive('\n'){let clean=line.trim_end_matches(['\r','\n']);if clean=="---"{offset+=line.len();return Some((fields,&text[offset..]));}if let Some((key,value))=clean.split_once(':'){fields.insert(key.trim().to_string(),value.trim().trim_matches(['\'','"']).to_string());}offset+=line.len();}None}
fn io(error:impl std::fmt::Display)->ServiceError{ServiceError::Io(error.to_string())}
