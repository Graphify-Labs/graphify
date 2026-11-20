class_name Slime
extends Creature

const SPLIT := preload("res://scripts/split_rules.gd")


func die() -> void:
	SPLIT.spawn_children(self)
	super.die()
