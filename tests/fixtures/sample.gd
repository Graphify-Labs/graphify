@tool
class_name Player
extends CharacterBody2D

signal health_changed(value: int)
@export var weapon: Weapon
const MAX_HEALTH: int = 100
enum State { IDLE, RUNNING }

func _ready() -> void:
    _setup()
    self.reset()
    var copy := Weapon.new()

func _setup() -> void:
    pass

func reset() -> void:
    pass

class Inventory:
    var count: int

    func clear() -> void:
        count = 0
