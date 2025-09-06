extends EditorPlugin
func _enter_tree():
    add_custom_type("ComicBubble", "Control", preload("res://addons/comic_bubble/comic_bubble.gd"), preload("res://addons/comic_bubble/icon.svg"))
func _exit_tree():
    remove_custom_type("ComicBubble")
