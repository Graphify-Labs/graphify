class_name Enemy
extends CharacterBody2D

signal died(reason)

func _ready():
	died.connect(_on_died)
	sprite.play("idle")

func take_damage(amount):
	if amount > 0:
		emit_signal("died", "killed")
		die()

func die():
	var fx = preload("res://audio.gd")
	queue_free()

func _on_died(reason):
	print(reason)
