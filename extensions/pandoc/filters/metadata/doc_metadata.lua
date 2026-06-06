
local words = 0
local metadata = {}


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
    metadata[k] = pandoc.utils.stringify(v)
  end 
end

function Pandoc(el)
  document_key = 'document:metadata:'..pandoc.path.filename(PANDOC_STATE['input_files'][1])
  pandoc.walk_block(pandoc.Div(el.blocks), wordcount) 
  pandoc.pipe("redis-cli", {'hset', document_key, 'wordcount', words}, '')
  for k,v in pairs(metadata) do 
    pandoc.pipe("redis-cli", {'hset', document_key, k, v}, '')
  end
  pandoc.pipe("redis-cli", {'expire', document_key, 60}, '')
  print(document_key)
  os.exit()
end
