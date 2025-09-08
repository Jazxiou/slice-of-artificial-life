extends Node

var socket = WebSocketPeer.new()
var url = "ws://127.0.0.1:9999"
var connected = false
var decision_callbacks = {}

var pending_decisions = {}

var action_duration = 5.0
var wait_after_action = 10.0
var timer = 0.0
var current_state = "waiting"

func request_decision(npc_name: String, context: String):
	var request = {
		"type": "decision",
		"npc": npc_name,
		"context": context
	}
	send_message(request)

func _ready():
	print("initial decision system")
	connect_to_websocket_server()

func connect_to_websocket_server():
	print("[Server] Attempting to connect to: " + url)
	var err = socket.connect_to_url(url)
	if err !=OK:
		set_process(false)
		print("[Server] Unable to connect, error: " + str(err))
	else:
		print("[Server] Connection initiated...")
	
func _process(delta):
	socket.poll()
	var state = socket.get_ready_state()
	
	match state:
		WebSocketPeer.STATE_OPEN:
			if not connected:
				connected = true
				print("[Server] WebSocket connected successfully!")
			while socket.get_available_packet_count() > 0:
				receive_message()
				
			update_decision_timer(delta)
				
		WebSocketPeer.STATE_CLOSED:
			if connected:
				connected = false
				print("Disconnected")
				
				await get_tree().create_timer(3.0).timeout
				connect_to_websocket_server()

func update_decision_timer(delta):
	timer += delta
	
	match current_state:
		"waiting":
			if timer >= 1.0:
				current_state = "acting"
				timer = 0.0
				
		"acting":
			if timer >= action_duration:
				current_state = "cooldown"
				timer = 0.0
				
		"cooldown":
			if timer >= wait_after_action:
				current_state = "waiting"
				timer = 0.0

func receive_message():
	var packet = socket.get_packet()
	var message = packet.get_string_from_utf8()
	
	var json = JSON.new()
	var result = json.parse(message)
	if result == OK:
		if json.data.type == "decision_result":
			handle_decision_response(json.data)
			
func request_decision_with_callback(npc_name: String, context: String, callback: Callable):
	decision_callbacks[npc_name] = callback
	request_decision(npc_name, context)

func handle_decision_response(data):
	var npc_name = data.npc
	var action = data.action
	var target = data.target
	if npc_name in decision_callbacks:
		decision_callbacks[npc_name].call(action, target)
		decision_callbacks.erase(npc_name)


func send_message(data):
	if not connected:
		print("not connected")
		return
	var json_str = JSON.stringify(data)
	socket.send_text(json_str)

func _exit_tree():
	if socket:
		socket.close()

	
	
