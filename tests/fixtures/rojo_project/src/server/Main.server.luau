--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Logger = require(game:GetService("ReplicatedStorage"):WaitForChild("Shared").Util.Logger)
local Other = require(script.Parent.Other)
local Signal = require(ReplicatedStorage.Shared.Signal)
local ServerRef = require(script.Parent.ServerRef)
local Thing = require(ServerRef.Systems.Thing)
local Promise = require(ReplicatedStorage.Packages.Promise)

local module = script.Parent.Other

local function load(module: ModuleScript)
	return require(module)
end

local function loadConfig()
	return (require :: any)(script.Parent.Config)
end

Logger.info(Thing.name)
print(Other, Signal, Promise, module, load, loadConfig)
