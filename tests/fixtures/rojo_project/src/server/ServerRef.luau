--!strict
local ServerScriptService = game:GetService("ServerScriptService")
local Server = ServerScriptService:WaitForChild("Server")

return {
	Systems = Server:WaitForChild("Systems"),
}
