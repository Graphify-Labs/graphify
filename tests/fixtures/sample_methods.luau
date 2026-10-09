--!strict
-- Lua-family paths on a .luau file: a bare `require` statement, a `self:` call
-- to a sibling method and a colon call on an unknown receiver, next to an
-- unrelated bare function with the same name as the method.

require(script.Parent.Bootstrap)

local function stop(): ()
	print("module stop")
end

local Server = {}

function Server:stop(): ()
	print("server stop")
end

function Server:restart(): ()
	self:stop()
end

function Server:relay(peer: any): ()
	peer:stop()
end

return Server
