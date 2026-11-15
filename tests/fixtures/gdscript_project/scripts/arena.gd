extends "res://scripts/arena_base.gd"

var _boss: Creature


func _ready() -> void:
	_boss.hurt.connect(_on_boss_hurt)
	Events.enemy_died.connect(_on_enemy_died)
	reset()


func spawn() -> void:
	var s := Slime.new()
	s.take_hit(3)
	for c: Creature in get_children():
		c.die()


func _on_boss_hurt(amount: int) -> void:
	pass


func _on_enemy_died(at: Vector2) -> void:
	spawn()


class Wave:
	extends RefCounted
	var size: int = 0

	func grow() -> void:
		size += 1
		_clamp()

	func _clamp() -> void:
		size = mini(size, 9)
