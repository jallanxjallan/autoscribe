-- normalize_headings.lua
--
-- Repairs common legacy heading problems:
--   - removes empty headings
--   - promotes a leading Word Title/Subtitle style into metadata
--   - promotes heading levels when a document starts at H2/H3
--   - optionally converts short bold-only paragraphs into H2 headings

local stringify = pandoc.utils.stringify

local function trim(text)
  text = tostring(text or "")
  text = text:gsub("\194\160", " ")
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  return text
end

local function canonical(text)
  local s = tostring(text or ""):lower()
  s = s:gsub("[^%w]+", " ")
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  s = s:gsub("%s+", " ")
  return s
end

local function custom_style(el)
  if el and el.attributes then
    return el.attributes["custom-style"] or el.attributes["data-custom-style"] or ""
  end
  return ""
end

local function block_text(block)
  return trim(stringify(block))
end

local function div_has_style(block, style_name)
  if block.t ~= "Div" then
    return false
  end
  return canonical(custom_style(block)) == style_name
end

local function first_para_inlines_from_div(div)
  if div.t ~= "Div" then
    return nil
  end

  if #div.content == 1 and (div.content[1].t == "Para" or div.content[1].t == "Plain") then
    return div.content[1].content
  end

  return nil
end

local function meta_missing(value)
  return value == nil or trim(stringify(value)) == ""
end

local function all_heading_like_inlines(inlines)
  if #inlines == 0 then
    return false
  end

  for _, inline in ipairs(inlines) do
    if inline.t == "Space" or inline.t == "SoftBreak" then
      -- ok
    elseif inline.t == "Strong" or inline.t == "Emph" or inline.t == "SmallCaps" then
      -- ok
    else
      return false
    end
  end

  local text = trim(stringify(inlines))
  if text == "" then
    return false
  end

  if #text > 90 then
    return false
  end

  -- Avoid converting complete prose sentences into headings.
  if text:match("[%.%!%?;:]$") then
    return false
  end

  return true
end

local function flatten_heading_like_inlines(inlines)
  local out = pandoc.List({})

  for _, inline in ipairs(inlines) do
    if inline.t == "Strong" or inline.t == "Emph" or inline.t == "SmallCaps" then
      for _, child in ipairs(inline.content) do
        table.insert(out, child)
      end
    else
      table.insert(out, inline)
    end
  end

  return out
end

local function normalize_headers(blocks)
  local min_level = nil

  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      if min_level == nil or block.level < min_level then
        min_level = block.level
      end
    end
  end

  if min_level ~= nil and min_level > 1 then
    local delta = min_level - 1
    for _, block in ipairs(blocks) do
      if block.t == "Header" then
        block.level = math.max(1, block.level - delta)
      end
    end
  end

  return blocks
end

function Pandoc(doc)
  local blocks = pandoc.List({})
  local i = 1

  -- Promote a leading Word Title style into title metadata.
  if doc.blocks[1] and div_has_style(doc.blocks[1], "title") then
    local title_inlines = first_para_inlines_from_div(doc.blocks[1])
    if title_inlines and meta_missing(doc.meta.title) then
      doc.meta.title = pandoc.MetaInlines(title_inlines)
      i = 2
    end
  end

  -- Promote a following Subtitle style into subtitle metadata.
  if doc.blocks[i] and div_has_style(doc.blocks[i], "subtitle") then
    local subtitle_inlines = first_para_inlines_from_div(doc.blocks[i])
    if subtitle_inlines and meta_missing(doc.meta.subtitle) then
      doc.meta.subtitle = pandoc.MetaInlines(subtitle_inlines)
      i = i + 1
    end
  end

  while i <= #doc.blocks do
    local block = doc.blocks[i]

    if block.t == "Header" then
      if block_text(block) ~= "" then
        table.insert(blocks, block)
      end
    elseif block.t == "Para" and all_heading_like_inlines(block.content) then
      table.insert(blocks, pandoc.Header(2, flatten_heading_like_inlines(block.content)))
    else
      table.insert(blocks, block)
    end

    i = i + 1
  end

  doc.blocks = normalize_headers(blocks)
  return doc
end
