-- emit_ndjson.lua
--
-- Generic AutoScribe NDJSON emitter for Pandoc.
--
-- Contract:
--   record_type, record_identity, and record_plan are routing fields.
--   payload is the object passed to the target artifact ingest handler.
--   The document body is emitted as payload.content.

local stringify = pandoc.utils.stringify

local function trim_right(text)
  return tostring(text or ""):gsub("%s+$", "")
end

local function is_blank_string(value)
  return type(value) == "string" and value:match("^%s*$") ~= nil
end

local function first_non_blank(...)
  for i = 1, select("#", ...) do
    local value = select(i, ...)
    if value ~= nil and not is_blank_string(value) then return value end
  end
  return nil
end

local function pandoc_type(value)
  if value == nil then return nil end
  if pandoc.utils and pandoc.utils.type then
    local ok, result = pcall(pandoc.utils.type, value)
    if ok then return result end
  end
  return type(value)
end

local function is_array_table(value)
  if type(value) ~= "table" then return false end
  local count = 0
  for key, _ in pairs(value) do
    if type(key) ~= "number" then return false end
    count = count + 1
  end
  return count > 0
end

local function meta_to_plain(value)
  if value == nil then return nil end
  local kind = pandoc_type(value)

  if kind == "MetaMap" then
    local out = {}
    for key, item in pairs(value) do out[key] = meta_to_plain(item) end
    return out
  end
  if kind == "MetaList" or kind == "List" then
    local out = {}
    for _, item in ipairs(value) do out[#out + 1] = meta_to_plain(item) end
    return out
  end
  if kind == "MetaBool" then
    if type(value) == "boolean" then return value end
    if type(value) == "table" and value.c ~= nil then return value.c end
    return value
  end
  if kind == "MetaString" then
    if type(value) == "table" then return value.text or value.c or stringify(value) end
    return stringify(value)
  end
  if kind == "MetaInlines" or kind == "Inlines" then return stringify(value) end
  if kind == "MetaBlocks" or kind == "Blocks" then
    return trim_right(pandoc.write(pandoc.Pandoc(value, pandoc.Meta({})), "markdown"))
  end

  local lua_type = type(value)
  if lua_type == "string" or lua_type == "number" or lua_type == "boolean" then return value end
  if lua_type ~= "table" then return tostring(value) end

  if value.t ~= nil then
    if value.t == "MetaBool" then return value.c end
    if value.t == "MetaString" then return value.text or value.c or stringify(value) end
    if value.t == "MetaInlines" then return stringify(value) end
    if value.t == "MetaBlocks" then
      return trim_right(pandoc.write(pandoc.Pandoc(value, pandoc.Meta({})), "markdown"))
    end
  end

  local out = {}
  if is_array_table(value) then
    for i = 1, #value do out[i] = meta_to_plain(value[i]) end
  else
    for key, item in pairs(value) do out[key] = meta_to_plain(item) end
  end
  return out
end

local function markdown_content(blocks)
  return trim_right(pandoc.write(pandoc.Pandoc(blocks, pandoc.Meta({})), "markdown"))
end

local function has_class(block, class_name)
  if block.t ~= "Div" then return false end
  for _, class in ipairs(block.classes or {}) do
    if tostring(class):lower() == class_name then return true end
  end
  return false
end

local function extract_leading_directive(blocks)
  local first = blocks[1]
  if first == nil or not has_class(first, "directive") then return nil end

  local directive = markdown_content(first.content)
  blocks:remove(1)
  if directive == "" then return nil end
  return directive
end

function Pandoc(doc)
  local metadata = {}
  local legacy_identity = nil

  for key, value in pairs(doc.meta or {}) do
    local text_key = tostring(key)
    local plain_value = meta_to_plain(value)
    if text_key == "identity" then
      legacy_identity = plain_value
    else
      metadata[text_key] = plain_value
    end
  end

  local record_identity = first_non_blank(
    metadata.record_identity,
    metadata.identifier,
    metadata.slug,
    legacy_identity
  )
  local record_type = first_non_blank(
    metadata.record_type,
    metadata.control_type,
    metadata.kind,
    metadata.type
  )
  local record_plan = first_non_blank(metadata.record_plan)

  local payload = {}
  for key, value in pairs(metadata) do
    if key ~= "record_type" and key ~= "record_identity" and key ~= "record_plan" then
      payload[key] = value
    end
  end
  payload.identity = nil
  local directive = extract_leading_directive(doc.blocks)
  payload.content = markdown_content(doc.blocks)

  local record = {
    record_type = record_type,
    record_identity = record_identity,
    payload = payload,
  }
  if record_plan ~= nil then record.record_plan = record_plan end
  if directive ~= nil then record.directive = directive end

  io.stdout:write(pandoc.json.encode(record) .. "\n")
  return pandoc.Pandoc({}, pandoc.Meta({}))
end
