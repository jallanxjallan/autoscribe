-- document_wrapper.lua
-- Normalize required transport metadata for internal emission.
-- Reads kind and slug from doc.meta, validates them,
-- and rewrites them as plain MetaString values.

local stringify = pandoc.utils.stringify

local function fail(message)
  io.stderr:write("document_wrapper: " .. message .. "\n")
  os.exit(1)
end

local function trim(text)
  return text:gsub("^%s+", ""):gsub("%s+$", "")
end

local function require_meta_text(meta, key)
  local value = meta[key]
  if value == nil then
    fail("missing required metadata field: " .. key)
  end

  local text = trim(stringify(value))
  if text == "" then
    fail("metadata field must be a non-empty string: " .. key)
  end

  return text
end

function Pandoc(doc)
  local meta = doc.meta or {}

  local kind = require_meta_text(meta, "kind")
  local slug = require_meta_text(meta, "slug")

  doc.meta.kind = pandoc.MetaString(kind)
  doc.meta.slug = pandoc.MetaString(slug)

  return doc
end
