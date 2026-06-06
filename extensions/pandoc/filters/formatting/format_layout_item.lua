-- format_layout_item.lua
--
-- Traps any fenced div whose first class matches "layout-*" and emits
-- the contained text as a paragraph using that class name as the
-- paragraph style.
--
-- Usage in markdown:
--
--   ::: {.layout-component}
--   Chapter 12: The Jakarta Negotiations
--   :::
--
--   ::: {.layout-heading}
--   ## Part Three
--   :::

local function find_layout_class(classes)
  for _, class in ipairs(classes) do
    if class:match("^layout%-") then
      return class
    end
  end
  return nil
end

local function xml_escape(s)
  return s:gsub("&", "&amp;")
          :gsub("<", "&lt;")
          :gsub(">", "&gt;")
          :gsub('"', "&quot;")
end

function Div(el)
  local style = find_layout_class(el.classes)

  if not style then
    return nil
  end

  local text = pandoc.utils.stringify(el):match("^%s*(.-)%s*$")

  if text == "" then
    return nil
  end

  local xml = string.format(
    '<w:p><w:pPr><w:pStyle w:val="%s"/></w:pPr><w:r><w:t>%s</w:t></w:r></w:p>',
    style,
    xml_escape(text)
  )

  return pandoc.RawBlock("openxml", xml)
end