-- obsidian-links.lua
-- Convert Obsidian wikilinks to ordinary Pandoc links.

local function slugify(s)
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  s = s:gsub("%s+", "-")
  s = s:gsub("[^%w%-%._#]", "")
  return s
end

local function parse_wikilink(raw)
  local target, label = raw:match("^([^|]+)|(.+)$")

  if not target then
    target = raw
    label = raw
  end

  target = target:gsub("^%s+", ""):gsub("%s+$", "")
  label = label:gsub("^%s+", ""):gsub("%s+$", "")

  local file, heading = target:match("^([^#]+)#(.+)$")

  if heading then
    local anchor = "#" .. slugify(heading):lower()
    return label, anchor
  end

  -- For DOCX, this creates a clickable relative link.
  -- Spaces are acceptable in Word links, but encode them lightly.
  local href = target:gsub(" ", "%%20")

  if not href:match("%.md$") then
    href = href .. ".md"
  end

  return label, href
end

local function split_wikilinks(text)
  local result = {}
  local pos = 1

  while true do
    local start_pos, end_pos, raw = text:find("%[%[([^%]]+)%]%]", pos)

    if not start_pos then
      local rest = text:sub(pos)
      if rest ~= "" then
        table.insert(result, pandoc.Str(rest))
      end
      break
    end

    local before = text:sub(pos, start_pos - 1)
    if before ~= "" then
      table.insert(result, pandoc.Str(before))
    end

    local label, href = parse_wikilink(raw)
    table.insert(result, pandoc.Link(label, href))

    pos = end_pos + 1
  end

  return result
end

function Str(el)
  local text = el.text

  if not text:match("%[%[") then
    return nil
  end

  return split_wikilinks(text)
end