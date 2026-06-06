local codeblock_mode = "paragraph"

function Meta(meta)
  if meta["codeblock-mode"] then
    local requested = pandoc.utils.stringify(meta["codeblock-mode"]):lower()
    if requested == "strip" or requested == "list" or requested == "paragraph" then
      codeblock_mode = requested
    end
  end
  return meta
end

local function codeblock_to_list(text)
  local items = {}
  for line in text:gmatch("([^\n]+)") do
    table.insert(items, pandoc.Plain({ pandoc.Str(line) }))
  end
  return pandoc.BulletList(items)
end

function CodeBlock(el)
  if codeblock_mode == "strip" then
    return {}
  end
  if codeblock_mode == "list" then
    return codeblock_to_list(el.text)
  end
  return pandoc.Para({ pandoc.Str(el.text) })
end

return {
  { Meta = Meta, CodeBlock = CodeBlock }
}
