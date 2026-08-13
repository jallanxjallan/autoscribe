-- normalize_whitespace.lua
--
-- Normalizes whitespace inside prose-heavy imports.
-- Converts soft line breaks to spaces, NBSPs/tabs to normal spaces,
-- collapses repeated spaces, and trims leading/trailing inline spaces.

local function clean_text(text)
  local s = tostring(text or "")
  s = s:gsub("\194\160", " ") -- UTF-8 non-breaking space
  s = s:gsub("\226\128\175", " ") -- UTF-8 narrow non-breaking space
  s = s:gsub("\t", " ")
  s = s:gsub("%s+", " ")
  return s
end

local function append_space(out)
  if #out > 0 and out[#out].t ~= "Space" then
    table.insert(out, pandoc.Space())
  end
end

local function append_text(out, text)
  local s = clean_text(text)
  if s == "" then
    return
  end

  local leading = s:match("^%s") ~= nil
  local trailing = s:match("%s$") ~= nil

  s = s:gsub("^%s+", ""):gsub("%s+$", "")

  if leading then
    append_space(out)
  end

  for word in s:gmatch("%S+") do
    if #out > 0 and out[#out].t ~= "Space" then
      table.insert(out, pandoc.Space())
    end
    table.insert(out, pandoc.Str(word))
  end

  if trailing then
    append_space(out)
  end
end

local function normalize_inlines(inlines)
  local out = pandoc.List({})
  local pending_space = false

  for _, inline in ipairs(inlines) do
    if inline.t == "Str" then
      if pending_space then
        append_space(out)
        pending_space = false
      end
      append_text(out, inline.text)
    elseif inline.t == "Space" or inline.t == "SoftBreak" then
      pending_space = #out > 0
    else
      if pending_space then
        append_space(out)
        pending_space = false
      end
      table.insert(out, inline)
    end
  end

  -- Trim trailing spaces.
  while #out > 0 and out[#out].t == "Space" do
    table.remove(out)
  end

  return out
end

function SoftBreak()
  return pandoc.Space()
end

function Para(el)
  el.content = normalize_inlines(el.content)
  return el
end

function Plain(el)
  el.content = normalize_inlines(el.content)
  return el
end

function Header(el)
  el.content = normalize_inlines(el.content)
  return el
end
