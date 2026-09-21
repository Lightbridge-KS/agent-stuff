-- Original code is data until after Quarto's include/execution preprocessing.
-- This renderer-owned filter runs after Quarto's filters; author filters are rejected.
local file = assert(io.open("literal-code.json", "r"))
local values = pandoc.json.decode(file:read("*a"))
file:close()

local function restore(element)
  local original = values[element.text]
  if original ~= nil then element.text = original end
  return element
end

return {{ CodeBlock = restore, Code = restore }}
