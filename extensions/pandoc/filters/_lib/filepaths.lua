filepaths = {}

function filepaths.parse_filepath(filepath) 
    dir = filepath:match("(.-)([^\\/]-%.?([^%.\\/]*))$") 
    filename = filepath:match( "([^/]+)$") 
    extention = filename:match("[^.]+$") 
    stem = filename:gsub("."..extention, '') 
    return {dir=dir, filename=filename, stem=stem, ext=extension}
end
return filepaths

 