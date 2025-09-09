extends CharacterBody2D

@export var speed = 100
@export var target: Node2D

@onready var NA := $NavigationAgent2D as NavigationAgent2D
@onready var AP := $AnimatedSprite2D
@onready var server = get_node("/root/Server")
@onready var decision_timer := $DicisionTimer  # Reference to the decision timer

var is_observing := false  # Flag to pause movement during observation
var observation_duration := 3.0  # How long to observe
var observation_timer := 0.0
var is_acting := false  # Flag to indicate if Alice is performing an action
var is_walking := false  # Flag to indicate if Alice is walking to a target
var current_observation_bubble = null  # Reference to current observation bubble


func _ready():
	
	if target:
		makepath()

func _physics_process(_delta: float) -> void:
	# Handle observation timer
	if is_observing:
		observation_timer -= _delta
		if observation_timer <= 0:
			is_observing = false
			print("Alice finished observing")
			# Clear bubble reference when observation ends
			current_observation_bubble = null
			# Resume decision timer after observation
			finish_action()
	
	# Check if walk action is completed
	if is_walking and NA.is_navigation_finished():
		print("Alice reached destination")
		is_walking = false
		finish_action()
	
	# Only move if not observing
	if not is_observing:
		if not NA.is_navigation_finished():
			var next_pos = NA.get_next_path_position()
			var dir = global_position.direction_to(next_pos)
			velocity = dir.normalized() * speed
		else:
			velocity = Vector2.ZERO
		move_and_slide()
	else:
		# Stop movement during observation
		velocity = Vector2.ZERO
		
	update_animation()
	
	# Update observation bubble position to follow Alice
	update_observation_bubble_position()

func finish_action():
	# Resume decision timer after action completes
	if is_acting and decision_timer:
		is_acting = false
		decision_timer.start()
		print("Decision timer resumed")

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
	# Don't make new decisions while acting
	if is_acting:
		return
		
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
	
	# Stop decision timer during action execution
	if decision_timer:
		decision_timer.stop()
		is_acting = true
	
	if action == "walk":
		execute_walk(target_name)
	elif action == "chat":
		execute_chat(target_name)
	elif action == "observe":
		execute_observe(target_name)
		
func execute_walk(target_name: String):
	var target_node = find_target_by_name(target_name)
	if target_node:
		target = target_node
		makepath()
		is_walking = true  # Set walking flag
	else:
		print("Target not found: " + target_name)
		finish_action()  # Finish if target not found
	
func execute_observe(target_name: String):
	var target_node = find_target_by_name(target_name)
	
	# Start observation state
	is_observing = true
	observation_timer = observation_duration
	
	if target_node:
		# Face the target without rotating the sprite
		var direction = target_node.global_position - global_position
		# Update animation to face the target
		if abs(direction.x) > abs(direction.y):
			if direction.x < 0:
				AP.play("idle")  # or "idle_left" if you have directional idle animations
			else:
				AP.play("idle")  # or "idle_right"
		else:
			if direction.y > 0:
				AP.play("idle")  # or "idle_down"
			else:
				AP.play("idle")  # or "idle_up"
		
	# Get observation description
	var description = observations.get(target_name.to_lower(), "Alice observes " + target_name + " carefully.")
	print("Observation: " + description)
	
	# Show observation in thought bubble
	show_observation_bubble(description)

func find_target_by_name(target_name: String) -> Node2D:
	# Check NPCs
	var npcs = get_tree().get_nodes_in_group("npcs")
	for npc in npcs:
		if npc.name.to_lower() == target_name.to_lower():
			return npc
	
	# Check for other observable objects (bar, guitar, etc.)
	var all_nodes = get_tree().get_nodes_in_group("observable")
	for node in all_nodes:
		if node.name.to_lower() == target_name.to_lower():
			return node
	
	return null

func show_observation_bubble(text: String):
	# Display observation in a thought bubble
	# Get UI layer - it's a sibling node in the same scene
	var ui_layer = get_parent().get_node_or_null("UILayer")
	
	if not ui_layer:
		print("ERROR: UILayer not found for observation bubble")
		return
	else:
		print("UILayer found successfully")
	
	# Check if there's an existing bubble
	var bubble_name = "ObservationBubble_Alice"
	var existing_bubble = ui_layer.get_node_or_null(bubble_name)
	
	# Remove existing bubble if present
	if existing_bubble:
		print("Removing existing observation bubble")
		existing_bubble.queue_free()
	
	# Create new thought bubble using template or programmatically
	var bubble = null
	
	# Try to duplicate from template first
	var example = ui_layer.get_node_or_null("SpeechBubbleExample")
	if example:
		print("Found SpeechBubbleExample, duplicating...")
		bubble = example.duplicate()
		bubble.name = bubble_name
		bubble.visible = true  # Make sure it's visible
		
		# First add to tree
		ui_layer.add_child(bubble)
		
		# Then attach the streaming_bubble script
		var script = load("res://scripts/streaming_bubble.gd")
		if script:
			bubble.set_script(script)
			print("Attached streaming_bubble script to duplicated bubble")
			
			# Initialize bubble type before _ready
			bubble.bubble_type = "thought"
			
			# Call _ready after script is attached and bubble is in tree
			if bubble.has_method("_ready"):
				bubble._ready()
				print("Called _ready on bubble")
		else:
			print("ERROR: Could not load streaming_bubble.gd")
	else:
		print("No SpeechBubbleExample found, creating programmatically...")
		# Create bubble programmatically
		bubble = Panel.new()
		bubble.name = bubble_name
		bubble.size = Vector2(200, 80)  # Larger bubble for better text visibility
		bubble.visible = true
		
		# Add to tree first
		ui_layer.add_child(bubble)
		
		# Add RichTextLabel for text
		var label = RichTextLabel.new()
		label.name = "Label"
		label.bbcode_enabled = true
		label.fit_content = true
		label.scroll_active = false
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		label.add_theme_font_size_override("normal_font_size", 14)
		label.add_theme_color_override("default_color", Color(0.2, 0.2, 0.3, 1.0))  # Dark blue-gray
		bubble.add_child(label)
		
		# Add the streaming_bubble script after bubble is in tree
		var script = load("res://scripts/streaming_bubble.gd")
		if script:
			bubble.set_script(script)
			bubble.bubble_type = "thought"
			if bubble.has_method("_ready"):
				bubble._ready()
				print("Created programmatic bubble with script")
	
	# Configure as thought bubble
	if bubble.has_method("set_bubble_type"):
		print("Setting bubble type to thought")
		bubble.set_bubble_type("thought")
	else:
		print("WARNING: bubble doesn't have set_bubble_type method")
	
	# Set text
	if bubble.has_method("update_text"):
		print("Updating bubble text: " + text.substr(0, 30) + "...")
		bubble.update_text(text)
	else:
		print("WARNING: bubble doesn't have update_text method")
		# Try to update text directly
		var label = bubble.get_node_or_null("ScrollContainer/BubbleText")
		if not label:
			label = bubble.get_node_or_null("Label")
		if label and label is RichTextLabel:
			label.text = "[center][i][color=#333344]" + text + "[/color][/i][/center]"
			label.bbcode_enabled = true
			print("Updated text directly on RichTextLabel")
	
	# Position above Alice - use same method as dialogue bubbles
	var alice_pos = global_position
	
	# Check if there's a speech bubble and adjust position
	var speech_bubble = ui_layer.get_node_or_null("SpeechBubble_Alice")
	if speech_bubble and is_instance_valid(speech_bubble):
		# Place observation bubble to the left side if dialogue exists
		bubble.position = Vector2(alice_pos.x - 140, alice_pos.y - 100)
		print("Speech bubble exists, positioning observation bubble to the left")
	else:
		# Normal position above character (same as dialogue bubble)
		bubble.position = Vector2(alice_pos.x - 70, alice_pos.y - 90)
		print("No speech bubble, positioning observation bubble above")
	
	print("Final bubble position: " + str(bubble.position))
	
	# Update arrow to point at character - convert to screen coordinates
	if bubble.has_method("point_to_character"):
		var screen_pos: Vector2
		var cam = get_viewport().get_camera_2d()
		if cam:
			# Same conversion as dialogue bubbles
			var viewport_transform = get_viewport().get_canvas_transform()
			var camera_transform = cam.get_canvas_transform()
			screen_pos = viewport_transform * camera_transform * alice_pos
		else:
			# Fallback: use viewport canvas transform directly
			screen_pos = get_viewport().get_canvas_transform() * alice_pos
		bubble.point_to_character(screen_pos)
	else:
		print("WARNING: No camera found!")
	
	# Make sure bubble is visible
	bubble.visible = true
	print("Bubble visibility set to true")
	
	# Auto-fade after 4 seconds
	var tween = get_tree().create_tween()
	tween.tween_interval(4.0)
	tween.tween_property(bubble, "modulate:a", 0.0, 0.5)
	tween.tween_callback(func(): 
		print("Observation bubble fade complete, removing...")
		if is_instance_valid(bubble):
			bubble.queue_free()
	)
	
	print("Observation bubble creation complete!")
	
	# Store reference for position updates
	current_observation_bubble = bubble

func update_observation_bubble_position():
	# Update bubble position if it exists
	if current_observation_bubble and is_instance_valid(current_observation_bubble):
		var ui_layer = get_parent().get_node_or_null("UILayer")
		if not ui_layer:
			return
			
		# Use same positioning as dialogue bubbles
		var alice_pos = global_position
		
		# Check if there's a speech bubble and adjust position
		var speech_bubble = ui_layer.get_node_or_null("SpeechBubble_Alice")
		if speech_bubble and is_instance_valid(speech_bubble):
			# Place observation bubble to the left side if dialogue exists
			current_observation_bubble.position = Vector2(alice_pos.x - 140, alice_pos.y - 100)
		else:
			# Normal position above character
			current_observation_bubble.position = Vector2(alice_pos.x - 70, alice_pos.y - 90)
		
		# Update arrow to point at character
		if current_observation_bubble.has_method("point_to_character"):
			var screen_pos: Vector2
			var cam = get_viewport().get_camera_2d()
			if cam:
				var viewport_transform = get_viewport().get_canvas_transform()
				var camera_transform = cam.get_canvas_transform()
				screen_pos = viewport_transform * camera_transform * alice_pos
			else:
				screen_pos = get_viewport().get_canvas_transform() * alice_pos
			current_observation_bubble.point_to_character(screen_pos)
