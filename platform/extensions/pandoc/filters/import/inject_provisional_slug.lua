-- inject_provisional_slug.lua
--
-- Injects a provisional slug into document metadata during legacy import.
--
-- Slug shape:
--   prv.<kebab-case-input-file-stem>.<timestamp>
--
-- Example:
--   Warehouse Delay Notes.docx -> prv.warehouse-delay-notes.20260504143217

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

local function kebab_case(text)
  local s = tostring(text or ""):lower()

  -- Remove apostrophes before replacing other punctuation.
  s = s:gsub("[’']", "")

  -- Replace runs of non-alphanumeric characters with hyphens.
  s = s:gsub("[^%w]+", "-")

  -- Collapse repeated hyphens and trim.
  s = s:gsub("%-+", "-")
  s = s:gsub("^%-", ""):gsub("%-$", "")

  if s == "" then
    return "untitled"
  end

  return s
end

local function meta_string_is_empty(value)
  if value == nil then
    return true
  end
  local text = pandoc.utils.stringify(value)
  return text == nil or text:match("^%s*$") ~= nil
end

function Pandoc(doc)
  -- Guardrail: do not overwrite an existing slug.
  if not meta_string_is_empty(doc.meta.slug) then
    return doc
  end

  local input_file = first_input_file()
  local hint = "untitled"

  if input_file then
    hint = kebab_case(stem_from_path(input_file))
  end

  -- Local sortable timestamp. Useful for judging age/staleness by eye.
  local timestamp = os.date("%Y%m%d%H%M%S")
  doc.meta.slug = pandoc.MetaString("prv." .. hint .. "." .. timestamp)

  return doc
end
