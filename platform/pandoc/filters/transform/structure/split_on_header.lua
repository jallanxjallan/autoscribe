-- split_on_header.lua
-- Splits a document on a chosen header level and writes each chunk as JSON AST.
-- Each chunk inherits the parent doc's metadata and adds provenance fields.

local function str(v) return pandoc.utils.stringify(v or "") end
local function kebab(s)
  s = str(s):lower():gsub("[^%w]+","-"):gsub("^%-+",""):gsub("%-+$",""):gsub("%-+","-")
  if s == "" then return "section" end
  return s
end
local function mget(meta, key, default)
  local v = meta[key]
  if not v then return default end
  return pandoc.utils.stringify(v)
end

function Pandoc(doc)
  local meta = doc.meta or {}
  local level     = tonumber(mget(meta, "split-level", "1")) or 1
  local outdir    = mget(meta, "split-outdir", "./")
  local prefix    = mget(meta, "split-prefix", "")
  local drop_title= mget(meta, "split-drop-title", "true") == "true"
  local zeropad   = tonumber(mget(meta, "split-zeropad", "2")) or 2

  -- determine input filename
  local src = PANDOC_STATE.input_files and PANDOC_STATE.input_files[1] or "unknown"
  local src_base = src:match("([^/\\]+)$") or src
  local src_base_noext = src_base:gsub("%.[%w%._-]+$", "")

  os.execute(string.format('mkdir -p %q', outdir))

  local chunks, current = {}, nil
  local function start_chunk(h)
    if current then table.insert(chunks, current) end
    current = { title = h.content, blocks = {} }
  end

  for _, b in ipairs(doc.blocks) do
    if b.t == "Header" and b.level == level then
      start_chunk(b)
    else
      if not current then start_chunk(pandoc.Str("Untitled")) end
      table.insert(current.blocks, b)
    end
  end
  if current then table.insert(chunks, current) end

  local function clone_meta(m) return pandoc.Meta(m) end

  for i, ch in ipairs(chunks) do
    local title_text = str(ch.title)
    local base = kebab(title_text)
    local idx  = string.format("%0" .. zeropad .. "d", i)
    local fname = (prefix ~= "" and (prefix .. "-" .. idx .. "-" .. base)
                   or (idx .. "-" .. base)) .. ".json"
    local path = outdir .. "/" .. fname

    local blocks = ch.blocks
    if drop_title and blocks[1] and blocks[1].t == "Header" and blocks[1].level == level then
      table.remove(blocks, 1)
    end

    -- Build metadata for this chunk
    local meta_out = clone_meta(meta)
    meta_out.title           = pandoc.MetaString(title_text)
    meta_out.source_relpath  = pandoc.MetaString(src)
    meta_out.source_basename = pandoc.MetaString(src_base_noext)
    meta_out.sequence        = pandoc.MetaString(idx)
    meta_out.split_level     = pandoc.MetaString(tostring(level))
    meta_out.start_slug      = pandoc.MetaString(base)
    meta_out.start_title     = pandoc.MetaString(title_text)

    -- Optional: capture approximate source position if available
    if blocks[1] and blocks[1].attr and blocks[1].attr.attributes then
      local pos = blocks[1].attr.attributes["data-pos"]
        or blocks[1].attr.attributes["sourcepos"]
      if pos then meta_out.source_pos = pandoc.MetaString(pos) end
    end

    local doc_out = pandoc.Pandoc(blocks, meta_out)
    local json = pandoc.write(doc_out, "json")

    local f = assert(io.open(path, "w"))
    f:write(json)
    f:close()
  end

  -- suppress normal output; this run just splits
  return pandoc.Pandoc({}, doc.meta)
end
