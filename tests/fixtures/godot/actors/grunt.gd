extends "res://actors/enemy.gd"


func _ready() -> void:
	take_damage(1)
	super.patrol()
	died.emit()
	add_child(Node.new())


func patrol() -> void:
	super()
