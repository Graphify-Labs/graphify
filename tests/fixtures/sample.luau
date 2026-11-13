--!strict
-- Luau sample (Roblox): typed Lua superset, parsed with tree-sitter-luau.
-- Every construct below the first function is Luau-only and absent from the
-- plain Lua grammar: if-expressions, `::` casts, generics, string
-- interpolation, compound assignment, `continue`, `export type`.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Signal = require(ReplicatedStorage.Shared.Signal)

export type ServerConfig = {
	port: number,
	name: string?,
}

type Handler<T> = (payload: T) -> ()

local Server = {}
Server.__index = Server

function Server.new(config: ServerConfig): Server
	local self = setmetatable({}, Server)
	self.port = config.port
	self.name = if config.name then config.name else "default"
	self.handlers = {} :: { [string]: Handler<any> }
	self.changed = Signal.new()
	return self
end

function Server:start(): ()
	local label = `listening on :{self.port}`
	print(label)
end

function Server:on<T>(event: string, handler: Handler<T>): ()
	self.handlers[event] = handler
end

function Server:stop(): ()
	print("stopped")
end

local function countReady(servers: { Server }): number
	local ready = 0
	for _, server in servers do
		if server.port == 0 then
			continue
		end
		ready += 1
	end
	return ready
end

local function main()
	local s = Server.new({ port = 8080 })
	s:on("ping", function(payload: string)
		print(payload)
	end)
	s:start()
	print(countReady({ s }))
end

main()

return Server
