class_name Actor
extends CharacterBody2D

signal died


func take_damage(amount: int) -> void:
	died.emit()
