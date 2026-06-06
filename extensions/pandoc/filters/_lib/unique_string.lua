-- Function to generate a random string of a given length
function unique_string(length)
    local characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    local str = ""
    
    for i = 1, length do
        local randomIndex = math.random(1, #characters)
        str = str .. string.sub(characters, randomIndex, randomIndex)
    end
    
    return str
end

-- Usage example: Generate a random string of length 10
return unique_string(16)

