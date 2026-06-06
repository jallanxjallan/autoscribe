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
        meta['header'] = header_value 
    end 
    return meta 
end


 