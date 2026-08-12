-- Pandoc Lua filter to transform headers by prefixing parsed segments
function Header(el)
  -- Convert header content to a string
  local header_text = pandoc.utils.stringify(el.content)

  -- Split the header by dots and store the segments in a table (list)
  local segments = {}
  for segment in header_text:gmatch("([^.]+)") do
    table.insert(segments, segment)
  end
  

  -- Initialize an empty table to store the prefixed segments
  local prefixed_segments = {}

  -- Iterate over the segments and prefix each based on its position
  for i, segment in ipairs(segments) do
    print(segment)
    if i == 1 then
      table.insert(prefixed_segments, "Section " .. segment)
    elseif i == 2 then
      table.insert(prefixed_segments, "Chapter " .. segment)
    elseif i == 3 then
      table.insert(prefixed_segments, "Feature " .. segment)
    else
      -- For any segments after the third, just append them unchanged
      table.insert(prefixed_segments, segment)
    end
  end

  -- Join the prefixed segments with dots to form the final header text
  local new_header_text = table.concat(prefixed_segments, ". ")

  -- Replace the content of the header with the new text
  el.content = {pandoc.Str(new_header_text)}

  -- Return the modified header element
  return el
end
