-- emit_ndjson.lua
--
-- Generic AutoScribe NDJSON emitter for Pandoc.
--
-- Responsibility:
--   Convert the final Pandoc document into exactly one NDJSON record.
--
-- Contract:
--   - Every metadata key becomes a top-level JSON field, except legacy
--     top-level `identity`, which is used only as a fallback source for the
--     canonical upload `identifier`.
--   - Nested metadata maps/lists remain nested JSON objects/arrays.
--   - If top-level `identifier` is absent, it is derived from top-level
--     `slug`, then legacy top-level `identity`.
--   - The document body becomes the top-level `content` field, serialized as
--     markdown from doc.blocks.
--   - Upstream filters/defaults are responsible for injecting/normalizing all
--     metadata and content before this emitter runs.
--   - Downstream Python models validate required fields such as type,
--     identifier, job_slug, control shape, etc.
--
-- Intended use:
--   Place this last in the Pandoc filter chain.
--   Use an output target such as /dev/null, or rely on this filter returning an
--   empty document to prevent normal writer output from contaminating stdout.

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

    if value ~= nil and not is_blank_string(value) then
      return value
    end
  end

  return nil
end

local function pandoc_type(value)
  if value == nil then
    return nil
  end

  if pandoc.utils and pandoc.utils.type then
    local ok, result = pcall(pandoc.utils.type, value)
    if ok then
      return result
    end
  end

  return type(value)
end

local function is_array_table(value)
  if type(value) ~= "table" then
    return false
  end

  local count = 0

  for key, _ in pairs(value) do
    if type(key) ~= "number" then
      return false
    end

    count = count + 1
  end

  return count > 0
end

local function meta_to_plain(value)
  if value == nil then
    return nil
  end

  local kind = pandoc_type(value)

  if kind == "MetaMap" then
    local out = {}

    for key, item in pairs(value) do
      out[key] = meta_to_plain(item)
    end

    return out
  end

  if kind == "MetaList" then
    local out = {}

    for _, item in ipairs(value) do
      out[#out + 1] = meta_to_plain(item)
    end

    return out
  end

  if kind == "MetaBool" then
    if type(value) == "boolean" then
      return value
    end

    if type(value) == "table" and value.c ~= nil then
      return value.c
    end

    return value
  end

  if kind == "MetaString" then
    if type(value) == "table" then
      return value.text or value.c or stringify(value)
    end

    return stringify(value)
  end

  if kind == "MetaInlines" or kind == "Inlines" then
    return stringify(value)
  end

  if kind == "MetaBlocks" or kind == "Blocks" then
    return trim_right(pandoc.write(pandoc.Pandoc(value, pandoc.Meta({})), "markdown"))
  end

  if kind == "List" then
    local out = {}

    for _, item in ipairs(value) do
      out[#out + 1] = meta_to_plain(item)
    end

    return out
  end

  local lua_type = type(value)

  if lua_type == "string" or lua_type == "number" or lua_type == "boolean" then
    return value
  end

  if lua_type ~= "table" then
    return tostring(value)
  end

  -- Fallback for older Pandoc shapes or plain Lua tables injected by filters.
  if value.t ~= nil then
    if value.t == "MetaMap" then
      local out = {}

      for key, item in pairs(value) do
        out[key] = meta_to_plain(item)
      end

      return out
    end

    if value.t == "MetaList" then
      local out = {}

      for _, item in ipairs(value) do
        out[#out + 1] = meta_to_plain(item)
      end

      return out
    end

    if value.t == "MetaBool" then
      return value.c
    end

    if value.t == "MetaString" then
      return value.text or value.c or stringify(value)
    end

    if value.t == "MetaInlines" then
      return stringify(value)
    end

    if value.t == "MetaBlocks" then
      return trim_right(pandoc.write(pandoc.Pandoc(value, pandoc.Meta({})), "markdown"))
    end

    return stringify(value)
  end

  local out = {}

  if is_array_table(value) then
    for i = 1, #value do
      out[i] = meta_to_plain(value[i])
    end
  else
    for key, item in pairs(value) do
      out[key] = meta_to_plain(item)
    end
  end

  return out
end

local function meta_to_record(meta)
  local record = {}
  local legacy_identity = nil

  for key, value in pairs(meta or {}) do
    local text_key = tostring(key)
    local plain_value = meta_to_plain(value)

    if text_key == "identity" then
      legacy_identity = plain_value
    else
      record[text_key] = plain_value
    end
  end

  record.identifier = first_non_blank(record.identifier, record.slug, legacy_identity)

  return record
end

local function markdown_content(blocks)
  return trim_right(pandoc.write(pandoc.Pandoc(blocks, pandoc.Meta({})), "markdown"))
end

function Pandoc(doc)
  local record = meta_to_record(doc.meta)

  record.type = first_non_blank(record.type, record.control_type, record.kind)
  record.identifier = first_non_blank(record.identifier, record.slug)

  record.content = markdown_content(doc.blocks)

  -- Never emit server/runtime identity from upload records.
  record.identity = nil

  io.stdout:write(pandoc.json.encode(record) .. "\n")

  return pandoc.Pandoc({}, pandoc.Meta({}))
end