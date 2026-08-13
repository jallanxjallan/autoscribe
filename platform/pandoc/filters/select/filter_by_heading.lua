-- Pandoc Lua filter to retain only headings of levels specified in metadata "heading_filter"
function Meta(meta)
	-- Retrieve the list of heading levels to be filtered from metadata
	if meta.heading_filter then
	  -- Convert the list to numbers, since heading levels are numeric
	  heading_levels = {}
	  for _, level in ipairs(meta.heading_filter) do
		table.insert(heading_levels, tonumber(level))
	  end
	else
	  -- Default: If no filter is specified, pass all content
	  heading_levels = nil
	end
  end
  
  -- Helper function to check if a value is in a list
  function contains(list, value)
	for _, v in ipairs(list) do
	  if v == value then
		return true
	  end
	end
	return false
  end
  
  function keep_content(blocks, start_idx, end_idx)
	-- Helper function to keep the content between two heading indices
	local kept = {}
	for i = start_idx, end_idx do
	  table.insert(kept, blocks[i])
	end
	return kept
  end
  
  function Pandoc(doc)
	-- If no heading_filter is specified, return the document unchanged
	if not heading_levels then
	  return doc
	end
  
	local result = {}
	local in_section = false
	local start_idx = 0
  
	for i, blk in ipairs(doc.blocks) do
	  if blk.t == 'Header' then
		local level = blk.level
		if in_section then
		  -- If we encounter a new heading, finalize the previous section
		  for _, block in ipairs(keep_content(doc.blocks, start_idx, i - 1)) do
			table.insert(result, block)
		  end
		  in_section = false
		end
		-- Check if this heading level is in the filter list
		if contains(heading_levels, level) then
		  table.insert(result, blk)
		  start_idx = i + 1
		  in_section = true
		end
	  end
	end
  
	-- Capture the last section if we're in one
	if in_section then
	  for _, block in ipairs(keep_content(doc.blocks, start_idx, #doc.blocks)) do
		table.insert(result, block)
	  end
	end
  
	return pandoc.Pandoc(result, doc.meta)
  end
  