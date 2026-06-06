function Doc(doc)
  local meta = doc.meta
  local thumbnail_inline = nil

  -- Check for thumbnail metadata
  if meta.thumbnail and meta.thumbnail.url and meta.thumbnail.alt then
    local attr = pandoc.Attr("", {"thumbnail"})
    thumbnail_inline = pandoc.Image(meta.thumbnail.alt, meta.thumbnail.url, "", attr)
  end

  if thumbnail_inline then
    local inserted = false
    for i, block in ipairs(doc.blocks) do
      if block.t == "Para" then
        -- Insert inline thumbnail at start of first paragraph
        table.insert(block.content, 1, pandoc.Space())
        table.insert(block.content, 1, thumbnail_inline)
        inserted = true
        break
      end
    end

    if not inserted then
      -- Fallback: insert as its own paragraph at the top
      table.insert(doc.blocks, 1, pandoc.Para{thumbnail_inline})
    end
  end

  return doc
end
