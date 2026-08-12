-- format_reviewer_notes.lua
--
-- Converts Obsidian highlight spans (==LABEL: body==) into raw OpenXML
-- character runs: bold label + normal body, both wrapped in the
-- "reviewer-note" character style.
--
-- Falls back gracefully if the style is absent from styles.xml —
-- the bold on the label still renders via <w:b/>.

local stringify = pandoc.utils.stringify

local REVIEWER_NOTE_STYLE = "reviewer-note"

local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function normalize_space(s)
  return trim(s:gsub("%s+", " "))
end

local function is_mark_span(el)
  return el.classes:includes("mark")
    or el.classes:includes("highlight")
    or el.classes:includes("obsidian-highlight")
end

local function xml_escape(s)
  return s:gsub("&", "&amp;")
          :gsub("<", "&lt;")
          :gsub(">", "&gt;")
          :gsub('"', "&quot;")
end

local function make_run(text, bold)
  local rpr_parts = {
    string.format('<w:rStyle w:val="%s"/>', REVIEWER_NOTE_STYLE)
  }
  if bold then
    rpr_parts[#rpr_parts + 1] = "<w:b/>"
    rpr_parts[#rpr_parts + 1] = "<w:bCs/>"
  end
  return string.format(
    "<w:r><w:rPr>%s</w:rPr><w:t xml:space=\"preserve\">%s</w:t></w:r>",
    table.concat(rpr_parts),
    xml_escape(text)
  )
end

local function make_reviewer_note(inlines)
  local text = normalize_space(stringify(inlines))

  if text == "" then
    return nil
  end

  local raw_label, body = text:match("^([^:]+):%s*(.*)$")

  local label, runs
  if raw_label then
    label = normalize_space(raw_label):upper() .. ":"
    body  = normalize_space(body or "")
    if body ~= "" then
      runs = make_run(label, true) .. make_run(" " .. body, false)
    else
      runs = make_run(label, true)
    end
  else
    runs = make_run("NOTE: " .. text, false)
  end

  return pandoc.RawInline("openxml", runs)
end

function Span(el)
  if not is_mark_span(el) then
    return nil
  end

  return make_reviewer_note(el.content)
end