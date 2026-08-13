-- build_hint_from_inputfile.lua
--
-- Fallback-only Pandoc Lua filter.
--
-- If no filename hint is already present, derive one from
-- PANDOC_STATE.input_files[1] and write it to:
--   meta.filename_hint
--   meta.input_record.filename_hint
--
-- Intended to run before build_file_slug.lua.

local stringify = pandoc.utils.stringify

local function trim(s)
  return (s or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function is_meta_map(v)
  return type(v) == "table" and v.t == nil
end

local function as_string(v)
  if v == nil then
    return nil
  end
  if type(v) == "string" then
    v = trim(v)
    return v ~= "" and v or nil
  end
  local ok, s = pcall(stringify, v)
  if not ok then
    return nil
  end
  s = trim(s)
  return s ~= "" and s or nil
end

local function meta_get(map, key)
  if not is_meta_map(map) then
    return nil
  end
  return map[key]
end

local function meta_get_string(map, key)
  return as_string(meta_get(map, key))
end

local function ensure_meta_map(map, key)
  if not is_meta_map(map[key]) then
    map[key] = pandoc.MetaMap({})
  end
  return map[key]
end

local function slugify_stem(s)
  s = (s or ""):lower()
  s = s:gsub("[%s_]+", "-")
  s = s:gsub("[^a-z0-9%-]", "-")
  s = s:gsub("%-+", "-")
  s = s:gsub("^%-+", ""):gsub("%-+$", "")
  return s
end

local function basename_stem(path)
  if not path then
    return nil
  end

  local normalized = trim(path):gsub("\\", "/"):gsub("/+$", "")
  if normalized == "" then
    return nil
  end

  local leaf = normalized:match("([^/]+)$") or normalized
  if leaf == "" or leaf == "." or leaf == ".." then
    return nil
  end

  local stem = leaf:gsub("%.[^.]+$", "")
  return stem ~= "" and stem or leaf
end

local function existing_hint(meta)
  local direct = meta_get_string(meta, "filename_hint")
  if direct then
    return direct
  end

  local input_record = meta_get(meta, "input_record")
  local nested = meta_get_string(input_record, "filename_hint")
  if nested then
    return nested
  end

  return nil
end

local function inputfile_hint()
  local files = PANDOC_STATE and PANDOC_STATE.input_files or nil
  if not files or not files[1] then
    return nil
  end

  local stem = basename_stem(files[1])
  if not stem then
    return nil
  end

  local hint = slugify_stem(stem)
  return hint ~= "" and hint or nil
end

function Meta(meta)
  if existing_hint(meta) then
    return meta
  end

  local hint = inputfile_hint()
  if not hint then
    return meta
  end

  meta.filename_hint = pandoc.MetaString(hint)

  local input_record = ensure_meta_map(meta, "input_record")
  input_record.filename_hint = pandoc.MetaString(hint)

  return meta
end