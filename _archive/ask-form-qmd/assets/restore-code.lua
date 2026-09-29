-- Original code is data until after Quarto's include/execution preprocessing.
-- This renderer-owned filter runs after Quarto's filters; author filters are rejected.
local file = assert(io.open("literal-code.json", "r"))
local values = pandoc.json.decode(file:read("*a"))
file:close()

local function restore(element)
  local original = values.code[element.text]
  if original ~= nil then element.text = original end
  return element
end

local function restore_block(element)
  local html = values.html[element.text]
  if html ~= nil then return pandoc.RawBlock("html", html) end
  local source = values.diagrams[element.text]
  if source ~= nil then
    -- Only renderer-owned markup. Escape source as text, never HTML or JS.
    local escaped = source:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;")
    return pandoc.RawBlock("html", '<div class="rd-diagram" data-rd-state="pending"><pre class="rd-mermaid-source">'
      .. escaped .. '</pre></div>')
  end
  return restore(element)
end

return {{ CodeBlock = restore_block, Code = restore }}
