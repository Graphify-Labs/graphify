class_name Player
extends CharacterBody2D

signal died(cause)
signal health_changed(old_value, new_value)

const Enemy = preload("res://enemies/enemy.gd")

@export var speed: int = 300
@onready var sprite = $Sprite2D

var health: int = 100

class Inventory:
	var items: Array = []

	func add_item(item) -> void:
		items.append(item)

static func create() -> Player:
	return Player.new()

func take_damage(amount: int) -> void:
	var old = health
	health -= amount
	health_changed.emit(old, health)
	if health <= 0:
		_die("damage")

func heal(amount: int) -> void:
	health += amount

func _die(cause: String) -> void:
	emit_signal("died", cause)
	queue_free()
