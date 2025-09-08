extends CharacterBody2D

@export var speed = 100
@export var target: Node2D

@onready var NA := $NavigationAgent2D as NavigationAgent2D
@onready var AP := $AnimatedSprite2D
@onready var server = get_node("/root/Server")


func _ready():
	
	if target:
		makepath()

func _physics_process(_delta: float) -> void:

	if not NA.is_navigation_finished():
		var next_pos = NA.get_next_path_position()
		var dir = global_position.direction_to(next_pos)
		velocity = dir.normalized() * speed
	else:
		velocity = Vector2.ZERO
	move_and_slide()
	update_animation()

func update_animation() -> void:
	if velocity.length() < 0.1:
		AP.play("idle")
	elif abs(velocity.x) > abs(velocity.y):
		if velocity.x < 0:
			AP.play("walk left")
		else:
			AP.play("walk right")
	else:
		if velocity.y > 0:
			AP.play("walk down")
		else:
			AP.play("walk up")

func makepath() -> void:
	if target:
		NA.target_position = target.global_position


func _on_dicision_timer_timeout() -> void:
	if not server:
		server = get_node_or_null("/root/Server")
		if not server:
			print("Server node not found")
			return
	
	if not server.connected:
		print("Server not connected yet, waiting...")
		return
		
	var context = generate_context()
	print("Alice sending decision request: " + context)
	server.request_decision_with_callback("Alice", context, on_decision_received)
	

func generate_context() -> String:
	var context_parts = []
	var npcs = get_tree().get_nodes_in_group("npcs")
	for npc in npcs:
		if npc == self:
			continue
		var distance = global_position.distance_to(npc.global_position)
		if distance < 150:
			context_parts.append(npc.name + " is nearby")
		elif distance < 300:
			context_parts.append(npc.name + " is in sight")
	
	if context_parts.is_empty():
		return "Nothing special happening"
	else:
		return ". ".join(context_parts)
	

func _on_path_finding_timer_timeout() -> void:
	makepath()

var observations = {
	"bob": "Bob the bartender, always with a friendly smile, polishing glasses behind the bar.",
	"sam": "Sam the musician, looking thoughtful with his guitar nearby.",
	"dog": "A friendly little dog, tail wagging, looking for someone to play with.",
	"bar": "A well-kept bar counter with various bottles neatly arranged.",
	"customer": "A mysterious patron, quietly observing the surroundings.",
	"alice": "Alice, a regular customer, lost in thought.",
	"guitar": "Sam's guitar, well-worn but carefully maintained."
}

func on_decision_received(action: String, target_name: String):
	print("Alice received decision: " + action + "|" + target_name)
	
	if action == "walk":
		execute_walk(target_name)
	elif action == "chat":
		print("Chat with " + target_name + " (还没实现)")
	elif action == "observe":
		execute_observe(target_name)
		
func execute_walk(target_name: String):
	var target_node = find_target_by_name(target_name)
	if target_node:
		target = target_node
		makepath()
	else:
		print("Target not found: " + target_name)
	
func execute_observe(target_name: String):
	var target_node = find_target_by_name(target_name)
	
	if target_node:
		# Face the target (need to handle rotation correctly)
		var direction = target_node.global_position - global_position
		rotation = direction.angle()
		
	# Get observation description
	var description = observations.get(target_name.to_lower(), "Alice observes " + target_name + " carefully.")
	print("Observation: " + description)
	# TODO: Later add visual bubble to show the observation

func find_target_by_name(target_name: String) -> Node2D:
	# Check NPCs
	var npcs = get_tree().get_nodes_in_group("npcs")
	for npc in npcs:
		if npc.name.to_lower() == target_name.to_lower():
			return npc
	
	return null
