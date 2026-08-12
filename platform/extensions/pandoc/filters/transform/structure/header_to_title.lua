--!/usr/local/bin/lua
local header_value


function Header(el)  
    if el.level == 1 then 
        header_value = el.content
        return {}
    end
end

function Meta(meta) 
    if header_value ~= nil then 
        a = pandoc.utils.stringify(header_value)
        b = string.gsub(a, '_', ' ')
        c = string.gsub(b, "[^%w%s]", "")
        meta['title'] = c
    end 
    return meta 
end


