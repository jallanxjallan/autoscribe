-- track_changes_to_notes.lua
--
-- Use only with a defaults file that sets:
--   track-changes: all
--
-- Pandoc represents tracked insertions/deletions and comments as spans.
-- This filter makes that output more legible in Markdown:
--   - deletion spans become strikeout
--   - insertion spans keep their text and receive an insertion class
--   - comment spans become inline footnotes when comment text/metadata is available

local stringify = pandoc.utils.stringify

local function has_class(el, class)
  for _, c in ipairs(el.classes or {}) do
    if c == class then
      return true
    end
  end
  return false
end

local function trim(text)
  text = tostring(text or "")
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  return text
end

local function attr_value(el, names)
  for _, name in ipairs(names) do
    if el.attributes and el.attributes[name] and el.attributes[name] ~= "" then
      return el.attributes[name]
    end
  end
  return nil
end

local function make_note(label, el)
  local parts = pandoc.List({})
  local author = attr_value(el, {"author", "data-author"})
  local date = attr_value(el, {"date", "time", "data-date"})
  local text = trim(stringify(el.content))

  table.insert(parts, pandoc.Str(label))

  if author then
    table.insert(parts, pandoc.Space())
    table.insert(parts, pandoc.Str("author:"))
    table.insert(parts, pandoc.Space())
    table.insert(parts, pandoc.Str(author))
  end

  if date then
    table.insert(parts, pandoc.Space())
    table.insert(parts, pandoc.Str("date:"))
    table.insert(parts, pandoc.Space())
    table.insert(parts, pandoc.Str(date))
  end

  if text ~= "" then
    table.insert(parts, pandoc.Space())
    table.insert(parts, pandoc.Str("text:"))
    table.insert(parts, pandoc.Space())
    for word in text:gmatch("%S+") do
      table.insert(parts, pandoc.Str(word))
      table.insert(parts, pandoc.Space())
    end
  end

  return pandoc.Note({pandoc.Para(parts)})
end

function Span(el)
  if has_class(el, "deletion") then
    return pandoc.Strikeout(el.content)
  end

  if has_class(el, "insertion") then
    return el
  end

  if has_class(el, "comment-start") or has_class(el, "comment") then
    return make_note("Word comment", el)
  end

  if has_class(el, "comment-end") then
    return {}
  end

  return el
end
