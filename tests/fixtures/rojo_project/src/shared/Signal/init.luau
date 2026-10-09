--!strict
local Signal = {}

function Signal.new()
	return setmetatable({}, Signal)
end

return Signal
