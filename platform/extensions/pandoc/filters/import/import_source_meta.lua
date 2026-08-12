-- import_source_meta.lua
--
-- Adds import provenance metadata for legacy documents.
-- Intended for provisional vault imports.

local function first_input_file()
  if PANDOC_STATE and PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    return PANDOC_STATE.input_files[1]
  end
  return nil
end

local function basename(path)
  return path:match("([^/\\]+)$") or path
end

local function stem_from_path(path)
  local name = basename(path)
  return name:gsub("%.[^.]+$", "")
end

local function extension_from_path(path)
  local ext = path:match("%.([^.]+)$")
  if ext then
    return ext:lower()
  end
  return ""
end

local function ensure_meta_map(value)
  if type(value) == "table" and value.t == "MetaMap" then
    return value
  end

  -- If the user already has a non-map source field, do not destroy it.
  -- The caller will place import details under import_source instead.
  return pandoc.MetaMap({})
end

local function set_missing(map, key, value)
  if map[key] == nil then
    map[key] = pandoc.MetaString(value)
  end
end

function Pandoc(doc)
  local input_file = first_input_file() or ""
  local source_key = "source"

  -- If source already exists but is not a map, avoid clobbering it.
  if doc.meta.source ~= nil and not (type(doc.meta.source) == "table" and doc.meta.source.t == "MetaMap") then
    source_key = "import_source"
  end

  local source = ensure_meta_map(doc.meta[source_key])

  set_missing(source, "imported_at", os.date("%Y-%m-%dT%H:%M:%S%z"))
  set_missing(source, "original_path", input_file)
  set_missing(source, "original_filename", basename(input_file))
  set_missing(source, "original_stem", stem_from_path(input_file))
  set_missing(source, "original_format", extension_from_path(input_file))
  set_missing(source, "import_method", "pandoc-import-vault")

  doc.meta[source_key] = source

  return doc
end
