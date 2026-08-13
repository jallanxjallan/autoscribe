-- obsidian_callouts.lua

local function extract_type(text)
  local t = text:match("^%[!([%w%-_]+)%]")
  if t then
    return string.lower(t)
  end
  return nil
end

function BlockQuote(el)
  if #el.content == 0 then
    return nil
  end

  local first = el.content[1]
  if first.t ~= "Para" then
    return nil
  end

  local first_text = pandoc.utils.stringify(first)
  local callout_type = extract_type(first_text)

  if not callout_type then
    return nil
  end

  -- Strip marker from first paragraph only
  local cleaned = pandoc.utils.stringify(first)
  cleaned = cleaned:gsub("^%[!([%w%-_]+)%]%s*", "")

  local new_blocks = {}

  if cleaned ~= "" then
    table.insert(new_blocks, pandoc.Para({ pandoc.Str(cleaned) }))
  end

  -- Append remaining blocks untouched
  for i = 2, #el.content do
    table.insert(new_blocks, el.content[i])
  end

  return pandoc.Div(
    new_blocks,
    pandoc.Attr(
      "",                       -- id
      { "callout", callout_type }, -- classes
      {}                        -- attributes
    )
  )
end
