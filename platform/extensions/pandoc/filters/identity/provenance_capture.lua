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

local function detect_input_file()
  local input_files = (PANDOC_STATE and PANDOC_STATE.input_files) or {}
  local first = input_files[1]
  if first and first ~= "" and first ~= "-" then
    return first
  end
  return nil
end

local function detect_source(meta)
  local direct = as_string(meta.source)
  if direct then
    return direct
  end

  local input_record = meta.input_record
  if is_meta_map(input_record) then
    local nested =
      as_string(input_record.source) or
      as_string(input_record.filepath) or
      as_string(input_record.source_file)
    if nested then
      return nested
    end
  end

  local input_file = detect_input_file()
  if input_file then
    return input_file
  end

  return "unknown"
end

function Meta(meta)
  local origin = meta.origin
  if not is_meta_map(origin) then
    origin = pandoc.MetaMap({})
  end

  for key, value in pairs(meta) do
    if key ~= "origin" and origin[key] == nil then
      origin[key] = value
    end
  end

  meta.origin = origin
  meta.source = pandoc.MetaString(detect_source(meta))
  return meta
end