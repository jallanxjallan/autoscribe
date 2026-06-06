function Para(el)
  -- Get the first character of the paragraph
  local first_char = pandoc.utils.stringify(el.content[1]):sub(1, 1)

  -- Check if the first character is non-alphabetic (not A-Z or a-z)
  if first_char:match("[^%a]") then
    -- Do something with the paragraph if it starts with a non-alphabetic character
    -- For example, you could add some styling or modify it in some way.
    -- This example wraps the paragraph in brackets.
    table.insert(el.content, 1, pandoc.Str("["))
    table.insert(el.content, pandoc.Str("]"))
  end

  return el
end
