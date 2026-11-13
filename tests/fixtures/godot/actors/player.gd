class_name Player
extends Actor

const Movement := preload("res://actors/movement.gd")
const Bullet := preload("../scenes/bullet.tscn")
const MAX_JUMPS: int = 2

@export var weapon: Weapon

signal jumped(height: float)
signal landed

enum State { IDLE, WALKING, JUMPING }

class Stats extends RefCounted:
	func speed_for(state: int) -> float:
		return base_speed()

	func base_speed() -> float:
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
	take_damage(2)
	Movement.walk_vector(1.0)
	Weapon.new()
	Stats.new()
	weapon.fire()
	$Sprite.play("idle")
	print("ready")


func _on_jumped(height: float) -> void:
	pass


func _on_landed() -> void:
	pass
