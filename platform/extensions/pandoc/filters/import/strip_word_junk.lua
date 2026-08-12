-- strip_word_junk.lua
--
-- Removes conservative mechanical Word/Pandoc residue from imported documents.

local stringify = pandoc.utils.stringify

local function trim(text)
  text = tostring(text or "")
  text = text:gsub("\194\160", " ") -- UTF-8 non-breaking space
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  return text
end

local function is_empty_inline_list(inlines)
  return trim(stringify(inlines or {})) == ""
end

local function is_empty_block_list(blocks)
  return trim(stringify(blocks or {})) == ""
end

local function is_junk_raw(text)
  local s = tostring(text or ""):lower()
  return s:match("page%-break")
    or s:match("pagebreak")
    or s:match("sectionbreak")
    or s:match("mso%-")
    or s:match("<w:")
    or s:match("</w:")
    or s:match("toc \\\\o")
end

local function is_probable_toc_line(text)
  local s = trim(text):lower()

  if s == "table of contents" or s == "contents" then
    return true
  end

  -- Examples often left by legacy TOCs:
  --   Chapter title ........................ 17
  --   Chapter title	17
  if s:match("%.%.%.+%d+$") then
    return true
  end

  return false
end

function Span(el)
  if is_empty_inline_list(el.content) then
    return {}
  end
  return el
end

function Div(el)
  if is_empty_block_list(el.content) then
    return {}
  end
  return el
end

function Para(el)
  if is_empty_inline_list(el.content) then
    return {}
  end

  local text = stringify(el.content)
  if is_probable_toc_line(text) then
    return {}
  end

  return el
end

function Plain(el)
  if is_empty_inline_list(el.content) then
    return {}
  end
  return el
end

function Header(el)
  if is_empty_inline_list(el.content) then
    return {}
  end
  return el
end

function RawBlock(el)
  if is_junk_raw(el.text) then
    return {}
  end
  return el
end

function RawInline(el)
  if is_junk_raw(el.text) then
    return {}
  end
  return el
end
