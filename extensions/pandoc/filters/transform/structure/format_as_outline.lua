-- Function to process ordered lists
--function OrderedList(el)
--  -- Iterate through each item in the ordered list
--  local ordered_list_items = {}
--  for _, item in ipairs(el.content) do
--      local content = item[1].content
--      content[1].text = "IMAGE: "..content[1].text
--	    table.insert(ordered_list_items, content)
--  end
--  return ordered_list_items
--end

-- Function to format sidebars
-- Lua filter to replace headers with text "Sidebar" to "Marginal Note"
-- and insert a paragraph after it.

function Header(el)
  -- Check if the header text matches "Sidebar"
  if el.content[1] and el.content[1].text == "Sidebar" then
    
    -- Create a new paragraph element
    local caption = pandoc.Para({pandoc.Str("This content appears in a box outside of the main text")})
    local caption_div = pandoc.Div(caption.content, {["custom-style"] = "Sidebar Caption"})

    -- Return both the modified header and the new paragraph
    return caption_div
  end

  return el
end

function OrderedList(el)
  -- Create a new heading "Suggested Images"
  local caption = pandoc.Para(pandoc.Strong("Suggested Images"))
  local caption_div = pandoc.Div(caption.content, {["custom-style"] = "Image Title"})
  
  
  -- Convert the ordered list to an unordered list
  local unordered_list = pandoc.BulletList(el.content)
  local image_div = pandoc.Div(unordered_list, {["custom-style"] = "List Indent"})
--  unordered_list.attr.attributes = unordered_list.attr.attributes or {}
--  unordered_list.attributes["custom-style"] = "List 1"
  
  -- Return the heading followed by the converted list
  return {caption_div, image_div}
end


-- apply-styles.lua
--function Para(el)
--  -- Apply a custom style to paragraphs
--  -- Replace "CustomParagraphStyle" with the desired style name
--  el.attr = el.attr or {}
--  el.attr.attributes = el.attr.attributes or {}
--  el.attr.attributes["custom-style"] = "CustomParagraphStyle"
--  return el
--end
--
--function BulletList(el)
--  -- Apply a custom style to bullet lists
--  -- Replace "CustomBulletListStyle" with the desired style name
--  el.attr = el.attr or {}
--  el.attr.attributes = el.attr.attributes or {}
--  el.attr.attributes["custom-style"] = "CustomBulletListStyle"
--  return el
--end
--
--function OrderedList(el)
--  -- Apply a custom style to ordered lists
--  -- Replace "CustomOrderedListStyle" with the desired style name
--  el.attr = el.attr or {}
--  el.attr.attributes = el.attr.attributes or {}
--  el.attr.attributes["custom-style"] = "CustomOrderedListStyle"
--  return el


