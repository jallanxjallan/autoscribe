
local words = 0
local name

wordcount = {
  Str = function(el)
    -- we don't count a word if it's entirely punctuation:
    if el.text:match("%P") then
        words = words + 1
    end
  end
}

function Meta(meta) 
  for k,v in pairs(meta) do 
    if k == 'name' then 
      name = pandoc.utils.stringify(v) 
    end
  end 
end

function Pandoc(el)

    -- skip metadata, just count body:
    pandoc.walk_block(pandoc.Div(el.blocks), wordcount) 
    if name == nil then 
        name = pandoc.path.filename(PANDOC_STATE['output_file']) 
    end
    print(name..': words: '..words)
    os.exit()
    
end
