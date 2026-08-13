-- Function to set the height of images to 200px
-- Function to set the height of every image to 200px
function Image(el)
  el.attributes = el.attributes or {}
  el.attributes.style = (el.attributes.style or "") .. "height: 150px;"
  return el
end


-- Main function to process Div elements with class "image_row"
function Div(el)
  if el.classes:includes("image_row") then
    -- Add inline styles to align images horizontally
    el.attributes.style = (el.attributes.style or "") .. "display: flex; gap: 10px; align-items: center;"
   end
   return el
end

