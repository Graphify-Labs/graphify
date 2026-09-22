## A player character for a small platformer, exercising every shape the GDScript
## extractor reads. Movement rules are described in movement.md §2.1; the jump arc in §2.3.
extends CharacterBody2D
class_name PlayerController

## No class_name on the movement helper: preload it (conventions.md §1.2).
const Movement := preload("res://actors/movement.gd")
const Inventory = load("res://actors/inventory.gd")
const DustPuff := preload("res://effects/dust_puff.tscn")
const MAX_JUMPS: int = 2

signal jumped(height: float)
signal landed

enum State { IDLE, WALKING, JUMPING }

class Stats extends RefCounted:
	func speed_for(state: int) -> float:
		return 120.0


static func clamp_speed(value: float) -> float:
	return minf(value, 300.0)


func _ready() -> void:
	jumped.connect(_on_jumped)
	landed.connect(self._on_landed)
	GameState.paused.connect(_on_jumped)
	jumped.emit(48.0)
	emit_signal("landed")
	GameState.add_score(10)
	GameState.unknown_method()
	clamp_speed(3.0)
	self.clamp_speed(4.0)
	apply_gravity()
	var vector := Movement.walk_vector(1.0)
	var bag := Inventory.new()
	Stats.new()
	$Sprite.play("idle")
	unknown_free_call()


func walk(direction: float) -> void:
	# The run speed follows physics.md §3.4; the slide (§3.5) belongs to the enemy script.
	pass


func jump() -> void:
	pass


func _on_jumped(height: float) -> void:
	pass


func _on_landed() -> void:
	pass
