
function Pandoc(doc) 
    filename = PANDOC_STATE['output_file'] 
    local f = io.open(filename, "r") 
    if f ~= nil and io.close(f) then 
        print(filename..' already exists') 
        os.exit()
    end
end
