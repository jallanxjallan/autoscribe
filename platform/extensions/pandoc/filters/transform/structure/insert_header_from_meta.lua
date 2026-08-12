local header_specs = {
  { key = "header", strong = true },
  { key = "title", strong = false },
  { key = "chapter", strong = false },
  { key = "image", strong = true },
}

local function build_header(text, strong)
  if strong then
    return pandoc.Header(1, { pandoc.Strong({ pandoc.Str(text) }) })
  end
  return pandoc.Header(1, { pandoc.Str(text) })
end

function Pandoc(doc)
  for _, spec in ipairs(header_specs) do
    local value = doc.meta[spec.key]
    if value then
      local text = pandoc.utils.stringify(value)
      if text and text ~= "" then
        table.insert(doc.blocks, 1, build_header(text, spec.strong))
        break
      end
    end
  end
  return doc
end
