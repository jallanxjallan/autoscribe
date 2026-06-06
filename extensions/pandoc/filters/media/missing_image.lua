local function Image(el)
  if el.src == "" then
    local replacement_text = pandoc.Strong{ pandoc.Str("Image Needed: ") }
    if el.title and el.title ~= "" then
      table.insert(replacement_text, pandoc.Str(el.title)) -- Add title if present
    end
    return replacement_text
  end
  return el
end

return {
  { Image = Image }
}