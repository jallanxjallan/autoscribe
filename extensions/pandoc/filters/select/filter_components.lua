local pandoc = require 'pandoc'

-- Map unicode prefix → custom style name
local symbol_refs = {
  ["¶"]  = "running_text",
  ["🖼"] = "caption",          -- normalized (no VS-16)
  ["⧉"]  = "boxout",
  ["▌"]  = "sidebar",
  ["⬖"]  = "standalone_page",
  ["📐"] = "layout_note",
  ["⌘"]  = "page_title",
  ["📖"] = "pdf_page",
}

local valid_components = {}
local errors = {}
local error_log_file = "filter_components_errors.log"

-- helper to capture the first full UTF‑8 character
local function first_utf8_char(s)
  return s:match("^[%z\1-\127\194-\244][\128-\191]*")
end

-- normalize by stripping emoji variation selector (U+FE0F)
local function normalize_symbol(s)
  if not s then return nil end
  -- remove all variation selectors
  return (s:gsub("\239\184\143", ""))  -- UTF-8 for U+FE0F
end

function Pandoc(doc)
  valid_components = {}
  errors = {}

  -- ensure old log is removed at start of each run
  os.remove(error_log_file)

  -- read metadata for active components
  local meta = doc.meta.components
  if meta and meta.t == "MetaList" then
    for _, item in ipairs(meta) do
      local s = pandoc.utils.stringify(item)
      for sym, key in pairs(symbol_refs) do
        if key == s then
          valid_components[sym] = key
        end
      end
    end
  else
    valid_components = symbol_refs -- enable all if none specified
  end

  local walked = doc:walk {
    Para = function (para)
      if #para.content == 0 then
        return nil
      end

      local first = para.content[1]
      if first.t ~= "Str" then
        table.insert(errors, "Para does not start with Str: " ..
                             pandoc.utils.stringify(para))
        return nil
      end

      local symbol = normalize_symbol(first_utf8_char(first.text))
      local style = valid_components[symbol]
      local known_style = symbol_refs[symbol]

      if not known_style then
        table.insert(errors, "Unrecognized symbol prefix '" ..
                             (symbol or "nil") .. "' in para: " ..
                             pandoc.utils.stringify(para))
        return nil
      end

      if not style then
        -- Known symbol but not active in metadata → silently drop
        return nil
      end

      -- Strip prefix symbol + optional space from first inline
      local rest = para.content:clone()
      rest[1].text = rest[1].text:gsub("^[%z\1-\127\194-\244][\128-\191]*%s*", "")
      if rest[1].text == "" then
        table.remove(rest, 1)
      end

      local newpara = pandoc.Para(rest)
      return pandoc.Div(newpara, { ["custom-style"] = style })
    end
  }

  if #errors > 0 then
    io.stderr:write(
      string.format("\27[91m⚠️  %d errors encountered in filter_extract_components. See %s.\27[0m\n",
                    #errors, error_log_file)
    )
    local fh = io.open(error_log_file, "w")
    for i, err in ipairs(errors) do
      fh:write(string.format("%03d. %s\n", i, err))
    end
    fh:close()
  end

  return walked
end

