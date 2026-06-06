-- Extract one control upload record from an Obsidian Markdown control file.
--
-- Convention:
--   frontmatter.slug  -> durable vault identity
--   first yaml fence  -> machine-readable control spec
--   remaining body    -> human-readable content
--
-- The normal Pandoc writer is suppressed. This filter writes exactly one
-- JSON object to stdout, so callers can stream it as NDJSON.

local function fail(message)
  io.stderr:write("control-spec-to-ndjson: ERROR: " .. message .. "\n")
  os.exit(1)
end

local function trim(value)
  return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function is_list(value)
  if type(value) ~= "table" then
    return false
  end

  local count = 0
  for key, _ in pairs(value) do
    if type(key) ~= "number" then
      return false
    end
    if key > count then
      count = key
    end
  end

  for index = 1, count do
    if value[index] == nil then
      return false
    end
  end

  return true
end

local function meta_to_plain(value)
  local lua_type = type(value)

  if lua_type == "nil" or lua_type == "boolean" or lua_type == "number" or lua_type == "string" then
    return value
  end

  local pandoc_type = pandoc.utils.type(value)

  if pandoc_type == "Inlines" or pandoc_type == "Blocks" or pandoc_type == "Inline" or pandoc_type == "Block" then
    return pandoc.utils.stringify(value)
  end

  if pandoc_type == "List" or is_list(value) then
    local out = {}
    for _, item in ipairs(value) do
      table.insert(out, meta_to_plain(item))
    end
    return out
  end

  if lua_type == "table" then
    local out = {}
    for key, item in pairs(value) do
      out[key] = meta_to_plain(item)
    end
    return out
  end

  return pandoc.utils.stringify(value)
end

local function decode_yaml_block(yaml_text)
  local parsed = pandoc.read("---\n" .. yaml_text .. "\n---\n", "markdown")
  local out = {}

  for key, value in pairs(parsed.meta) do
    out[key] = meta_to_plain(value)
  end

  return out
end

local function has_yaml_class(block)
  if block.t ~= "CodeBlock" then
    return false
  end

  for _, class in ipairs(block.classes) do
    if class == "yaml" or class == "yml" then
      return true
    end
  end

  return false
end

local function markdown_from_blocks(blocks)
  if #blocks == 0 then
    return ""
  end

  local doc = pandoc.Pandoc(blocks, pandoc.Meta({}))
  return trim(pandoc.write(doc, "markdown"))
end

function Pandoc(doc)
  local slug = ""
  if doc.meta.slug ~= nil then
    slug = trim(meta_to_plain(doc.meta.slug))
  end

  if slug == "" then
    fail("missing frontmatter slug")
  end

  local yaml_text = nil
  local body_blocks = {}

  for _, block in ipairs(doc.blocks) do
    if yaml_text == nil and has_yaml_class(block) then
      yaml_text = trim(block.text)
    else
      table.insert(body_blocks, block)
    end
  end

  if yaml_text == nil or yaml_text == "" then
    fail(slug .. ": missing fenced yaml block")
  end

  local record = decode_yaml_block(yaml_text)

  if record.slug ~= nil and trim(record.slug) ~= slug then
    fail(slug .. ": fenced yaml slug differs from frontmatter slug")
  end

  record.slug = slug
  record.content = markdown_from_blocks(body_blocks)

  io.stdout:write(pandoc.json.encode(record) .. "\n")

  return pandoc.Pandoc({}, pandoc.Meta({}))
end
