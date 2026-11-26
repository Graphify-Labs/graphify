class_name Creature
extends Node2D

signal hurt(amount: int)

var hp: int = 10


func take_hit(amount: int) -> void:
	hp -= amount
	hurt.emit(amount)
	if hp <= 0:
		die()


func die() -> void:
	Events.enemy_died.emit(position)
	queue_free()
