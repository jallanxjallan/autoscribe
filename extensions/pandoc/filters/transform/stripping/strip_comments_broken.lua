-- Filter to remove HTML comments from Pandoc AST.

local function walk_blocks(blocks)
  local new_blocks = {}
  for _, block in ipairs(blocks) do
    if block.t == "RawBlock" and block.format == "html" then
      -- Use a regex to remove HTML comments.
      local content = block.text:gsub("", "", 1)
        if content ~= "" then
            table.insert(new_blocks, {t="RawBlock", format = "html", text = content})
        end
    elseif block.t == "Para" then
        local inlines = block.c
        local new_inlines = {}
        for _, inline in ipairs(inlines) do
            if inline.t == "RawInline" and inline.format == "html" then
                local content = inline.text:gsub("", "", 1)
                if content ~= "" then
                    table.insert(new_inlines, {t="RawInline", format = "html", text = content})
                end
            else
                table.insert(new_inlines, inline)
            end
        end
        block.c = new_inlines
        table.insert(new_blocks, block)
    elseif block.t == "Div" then
        block.c = walk_blocks(block.c)
        table.insert(new_blocks, block)
    elseif block.t == "BlockQuote" then
        block.c = walk_blocks(block.c)
        table.insert(new_blocks, block)
    elseif block.t == "OrderedList" or block.t == "BulletList" then
        for i, item in ipairs(block.c) do
            block.c[i] = walk_blocks(item)
        end
        table.insert(new_blocks, block)
    elseif block.t == "DefinitionList" then
        for i, item in ipairs(block.c) do
            for j, def in ipairs(item[2]) do
                item[2][j] = walk_blocks(def)
            end
        end
        table.insert(new_blocks, block)
    else
        table.insert(new_blocks, block)
    end
  end
  return new_blocks
end

return {
  {
    Block = function(block)
        if block.t == "RawBlock" and block.format == "html" then
            local content = block.text:gsub("", "", 1)
            if content ~= "" then
                return {t="RawBlock", format = "html", text = content}
            else
                return {} -- Remove the block entirely if it's just a comment
            end
        elseif block.t == "Div" then
            block.c = walk_blocks(block.c)
            return block
        elseif block.t == "BlockQuote" then
            block.c = walk_blocks(block.c)
            return block
        elseif block.t == "OrderedList" or block.t == "BulletList" then
            for i, item in ipairs(block.c) do
                block.c[i] = walk_blocks(item)
            end
            return block
        elseif block.t == "DefinitionList" then
            for i, item in ipairs(block.c) do
                for j, def in ipairs(item[2]) do
                    item[2][j] = walk_blocks(def)
                end
            end
            return block
        else
            return block
        end
    end,
    Inline = function(inline)
        if inline.t == "RawInline" and inline.format == "html" then
          local content = inline.text:gsub("", "", 1)
            if content ~= "" then
                return {t="RawInline", format = "html", text = content}
            else
                return {}
            end
        else
            return inline
        end
    end
  }
}