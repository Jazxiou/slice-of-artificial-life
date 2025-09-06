extends Control
class_name ComicBubble

@export_group("Style")
@export var bg_color: Color = Color(0.05,0.05,0.05,0.82)
@export var border_color: Color = Color(0,0,0,0.82)
@export var border_width: int = 2
@export var corner_radius: int = 14
@export var padding: int = 8

@export_group("Tail")
@export var tail_base_width: float = 18.0
@export var tail_outline_px: float = 2.0
@export var tail_curve_amt: float = 10.0
@export var tail_max_len: float = 52.0
@export_enum("auto","top","bottom","left","right")
var attach_mode: String = "auto"

@export_group("Target Space")
@export var target_is_screen_space: bool = true
@export var camera_path: NodePath

var tail_fill: Line2D
var tail_outline: Line2D
var _style: StyleBoxFlat
var _label: RichTextLabel
var _target_screen: Vector2 = Vector2.ZERO

func _ready() -> void:
	_label = RichTextLabel.new()
	add_child(_label)
	_label.fit_content = true
	_label.bbcode_enabled = false
	_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_label.add_theme_color_override("default_color", Color(1,1,1,1))
	_update_label_rect()

	tail_outline = Line2D.new()
	tail_outline.show_behind_parent = true
	tail_outline.z_index = -1
	_config_line(tail_outline, tail_base_width + 2.0*tail_outline_px, border_color)
	add_child(tail_outline)

	tail_fill = Line2D.new()
	tail_fill.show_behind_parent = true
	tail_fill.z_index = -1
	_config_line(tail_fill, tail_base_width, bg_color)
	_set_fill_gradient(tail_fill, bg_color)
	add_child(tail_fill)

	_refresh_style()
	set_process(true)

func _notification(what):
	if what == NOTIFICATION_RESIZED:
		_update_label_rect()
		queue_redraw()
	if what == NOTIFICATION_DRAW:
		_draw_bubble()

func _draw_bubble():
	if _style == null:
		_refresh_style()
	draw_style_box(_style, Rect2(Vector2.ZERO, size))

func _refresh_style():
	_style = StyleBoxFlat.new()
	_style.bg_color = bg_color
	_style.border_color = border_color
	_style.border_width_top = border_width
	_style.border_width_bottom = border_width
	_style.border_width_left = border_width
	_style.border_width_right = border_width
	_style.corner_radius_top_left = corner_radius
	_style.corner_radius_top_right = corner_radius
	_style.corner_radius_bottom_left = corner_radius
	_style.corner_radius_bottom_right = corner_radius
	_style.content_margin_left = padding
	_style.content_margin_right = padding
	_style.content_margin_top = padding
	_style.content_margin_bottom = padding

func _update_label_rect():
	_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT, Control.PRESET_MODE_KEEP_SIZE, padding)

func set_text(t: String) -> void:
	_label.text = t

func set_target_world(pos_world: Vector2) -> void:
	var cam := _get_camera()
	if cam:
		_target_screen = cam.world_to_screen(pos_world)
	else:
		_target_screen = get_viewport().get_canvas_transform() * pos_world

func set_target_screen(pos_screen: Vector2) -> void:
	_target_screen = pos_screen

func _process(_dt: float) -> void:
	_update_tail()

func _update_tail() -> void:
	if _target_screen == Vector2.ZERO:
		return

	var xform_inv := get_global_transform_with_canvas().affine_inverse()
	var end := xform_inv.xform(_target_screen)

	var edge := _pick_edge(end)
	var start := _edge_point(edge)

	start += _edge_normal(edge) * ((tail_base_width + 2.0*tail_outline_px) * 0.5 - 1.0)

	var v := end - start
	var d := v.length()
	if d > tail_max_len and d > 0.0001:
		end = start + v * (tail_max_len / d)

	var mid := (start + end) * 0.5
	var dir := (end - start).normalized()
	var n := Vector2(-dir.y, dir.x)
	var control := mid + n * tail_curve_amt

	var pts := PackedVector2Array()
	var steps := 16
	for i in range(steps + 1):
		var t := float(i) / float(steps)
		pts.append(_quad_bezier(start, control, end, t))

	tail_outline.points = pts
	tail_fill.points = pts
	tail_outline.visible = true
	tail_fill.visible = true

func _config_line(l: Line2D, width: float, col: Color) -> void:
	l.width = width
	l.default_color = col
	l.joint_mode = Line2D.LINE_JOINT_ROUND
	l.begin_cap_mode = Line2D.LINE_CAP_ROUND
	l.end_cap_mode = Line2D.LINE_CAP_ROUND
	l.antialiased = true
	var c := Curve.new()
	c.add_point(Vector2(0.0, 1.0))
	c.add_point(Vector2(0.65, 0.45))
	c.add_point(Vector2(1.0, 0.0))
	l.width_curve = c

func _set_fill_gradient(l: Line2D, base: Color) -> void:
	var g := Gradient.new()
	g.set_offsets(PackedFloat32Array([0.0, 0.85, 1.0]))
	g.set_colors(PackedColorArray([
		base,
		Color(base.r, base.g, base.b, base.a * 0.8),
		Color(base.r, base.g, base.b, base.a * 0.65),
	]))
	var tex := GradientTexture1D.new()
	tex.gradient = g
	l.gradient = tex

func _get_camera() -> Camera2D:
	if camera_path != NodePath():
		var c := get_node_or_null(camera_path) as Camera2D
		if c: return c
	return get_viewport().get_camera_2d()

func _pick_edge(end_local: Vector2) -> String:
	if attach_mode != "auto":
		return attach_mode
	var c := size * 0.5
	var v := end_local - c
	return "right" if abs(v.x) > abs(v.y) and v.x > 0.0 		else "left"  if abs(v.x) > abs(v.y) 		else "bottom" if v.y > 0.0 else "top"

func _edge_point(mode: String) -> Vector2:
	var r := Rect2(Vector2.ZERO, size)
	var c := r.get_center()
	match mode:
		"right":  return Vector2(r.size.x, c.y)
		"left":   return Vector2(0.0,      c.y)
		"top":    return Vector2(c.x,      0.0)
		"bottom": return Vector2(c.x,      r.size.y)
		_:        return c

func _edge_normal(mode: String) -> Vector2:
	match mode:
		"right":  return Vector2( 1, 0)
		"left":   return Vector2(-1, 0)
		"top":    return Vector2( 0,-1)
		"bottom": return Vector2( 0, 1)
		_:        return Vector2(0,0)

func _quad_bezier(p0: Vector2, p1: Vector2, p2: Vector2, t: float) -> Vector2:
	var u := 1.0 - t
	return u*u*p0 + 2.0*u*t*p1 + t*t*p2
