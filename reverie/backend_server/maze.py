"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: maze.py
描述: 定义了 Maze 类，该类以二维矩阵表示模拟世界的地图。
"""
import json
import numpy
import datetime
import pickle
import time
import math

from global_methods import *
from utils import *

class Maze: 
  def __init__(self, maze_name): 
    # 读取地图的基本元信息
    self.maze_name = maze_name
    # 读取关于世界的元信息。如果你想查看示例变量，请查阅 maze_meta_info.json 文件。
    meta_info = json.load(open(f"{env_matrix}/maze_meta_info.json"))
    # <maze_width> 和 <maze_height> 表示构成地图高度和宽度的瓦片数量。
    self.maze_width = int(meta_info["maze_width"])
    self.maze_height = int(meta_info["maze_height"])
    # <sq_tile_size> 表示一个瓦片的像素高度/宽度。
    self.sq_tile_size = int(meta_info["sq_tile_size"])
    # <special_constraint> 是对世界可能具有的任何相关特殊约束的字符串描述。
    # 例如："planning to stay at home all day and never go out of her home" (计划整天呆在家里，永不迈出家门)
    self.special_constraint = meta_info["special_constraint"]

    # 读取特殊区块
    # 特殊区块是指在 Tiled 地图中着色的那些区块。

    # 这是竞技场区块文件的示例行：
    # 例如："25335, Double Studio, Studio, Common Room"
    # 这是游戏对象区块文件的另一个示例行：
    # 例如："25331, Double Studio, Studio, Bedroom 2, Painting"

    # 注意，这里的第一个元素是来自 Tiled 导出的颜色标记数字。然后我们基本上就有了区块路径：
    # 世界, 区域, 竞技场, 游戏对象 —— 再次强调，这些路径在 Reverie 的一个实例中必须是唯一的。
    blocks_folder = f"{env_matrix}/special_blocks"

    _wb = blocks_folder + "/world_blocks.csv"
    wb_rows = read_file_to_list(_wb, header=False)
    wb = wb_rows[0][-1]
   
    _sb = blocks_folder + "/sector_blocks.csv"
    sb_rows = read_file_to_list(_sb, header=False)
    sb_dict = dict()
    for i in sb_rows: sb_dict[i[0]] = i[-1]
    
    _ab = blocks_folder + "/arena_blocks.csv"
    ab_rows = read_file_to_list(_ab, header=False)
    ab_dict = dict()
    for i in ab_rows: ab_dict[i[0]] = i[-1]
    
    _gob = blocks_folder + "/game_object_blocks.csv"
    gob_rows = read_file_to_list(_gob, header=False)
    gob_dict = dict()
    for i in gob_rows: gob_dict[i[0]] = i[-1]
    
    _slb = blocks_folder + "/spawning_location_blocks.csv"
    slb_rows = read_file_to_list(_slb, header=False)
    slb_dict = dict()
    for i in slb_rows: slb_dict[i[0]] = i[-1]

    # [第 3 节] 读取矩阵
    # 这是典型的二维矩阵。它由 0 和代表区块文件夹中颜色区块的数字组成。
    maze_folder = f"{env_matrix}/maze"

    _cm = maze_folder + "/collision_maze.csv"
    collision_maze_raw = read_file_to_list(_cm, header=False)[0]
    _sm = maze_folder + "/sector_maze.csv"
    sector_maze_raw = read_file_to_list(_sm, header=False)[0]
    _am = maze_folder + "/arena_maze.csv"
    arena_maze_raw = read_file_to_list(_am, header=False)[0]
    _gom = maze_folder + "/game_object_maze.csv"
    game_object_maze_raw = read_file_to_list(_gom, header=False)[0]
    _slm = maze_folder + "/spawning_location_maze.csv"
    spawning_location_maze_raw = read_file_to_list(_slm, header=False)[0]

    # 加载迷宫。迷宫直接取自 Tiled 地图的 json 导出文件。它们应该是 csv 格式。
    # 重要的是，它们“不是”二维矩阵格式——它们是单行矩阵，
    # 长度为迷宫的宽度 x 高度。所以我们需要在这里进行转换。
    # 我们可以一次性完成所有这些操作，因为所有这些矩阵的维度都相同（例如，70 x 40）。
    # 示例格式: [['0', '0', ... '25309', '0',...], ['0',...]...]
    # 25309 当前是碰撞条的编号。
    self.collision_maze = []
    sector_maze = []
    arena_maze = []
    game_object_maze = []
    spawning_location_maze = []
    for i in range(0, len(collision_maze_raw), meta_info["maze_width"]): 
      tw = meta_info["maze_width"]
      self.collision_maze += [collision_maze_raw[i:i+tw]]
      sector_maze += [sector_maze_raw[i:i+tw]]
      arena_maze += [arena_maze_raw[i:i+tw]]
      game_object_maze += [game_object_maze_raw[i:i+tw]]
      spawning_location_maze += [spawning_location_maze_raw[i:i+tw]]

    # 加载完迷宫后，我们现在设置 self.tiles。这是一个通过 行:列 访问的矩阵，
    # 其中每个访问点都是一个字典，包含该瓦片中发生的所有事情。
    # 更具体地说，它包含有关其 "world" (世界)、"sector" (区域)、
    # "arena" (竞技场)、"game_object" (游戏对象)、"spawning_location" (出生点位置) 的信息，
    # 以及它是否是碰撞块，和其中发生的所有事件的集合。
    # 例如，self.tiles[32][59] = {'world': 'double studio', 
    #            'sector': '', 'arena': '', 'game_object': '', 
    #            'spawning_location': '', 'collision': False, 'events': set()}
    # 例如，self.tiles[9][58] = {'world': 'double studio', 
    #         'sector': 'double studio', 'arena': 'bedroom 2', 
    #         'game_object': 'bed', 'spawning_location': 'bedroom-2-a', 
    #         'collision': False,
    #         'events': {('double studio:double studio:bedroom 2:bed',
    #                    None, None)}} 
    self.tiles = []
    for i in range(self.maze_height): 
      row = []
      for j in range(self.maze_width):
        tile_details = dict()
        tile_details["world"] = wb
        
        tile_details["sector"] = ""
        if sector_maze[i][j] in sb_dict: 
          tile_details["sector"] = sb_dict[sector_maze[i][j]]
        
        tile_details["arena"] = ""
        if arena_maze[i][j] in ab_dict: 
          tile_details["arena"] = ab_dict[arena_maze[i][j]]
        
        tile_details["game_object"] = ""
        if game_object_maze[i][j] in gob_dict: 
          tile_details["game_object"] = gob_dict[game_object_maze[i][j]]
        
        tile_details["spawning_location"] = ""
        if spawning_location_maze[i][j] in slb_dict: 
          tile_details["spawning_location"] = slb_dict[spawning_location_maze[i][j]]
        
        tile_details["collision"] = False
        if self.collision_maze[i][j] != "0": # "0" is a data value
          tile_details["collision"] = True

        tile_details["events"] = set()
        
        row += [tile_details]
      self.tiles += [row]
    # 每个游戏对象在瓦片中占据一个事件。我们在这里设置默认事件值。
    for i in range(self.maze_height):
      for j in range(self.maze_width): 
        if self.tiles[i][j]["game_object"]:
          object_name = ":".join([self.tiles[i][j]["world"], 
                                  self.tiles[i][j]["sector"], 
                                  self.tiles[i][j]["arena"], 
                                  self.tiles[i][j]["game_object"]])
          go_event = (object_name, None, None, None)
          self.tiles[i][j]["events"].add(go_event)

    # 反向瓦片访问。
    # <self.address_tiles> -- 给定一个字符串地址，我们返回属于该地址的所有瓦片坐标集合
    # （这与 self.tiles 相反，后者是给定坐标返回字符串地址）。
    # 这是用于查找角色移动路径的优化组件。
    # self.address_tiles['<spawn_loc>bedroom-2-a'] == {(58, 9)}
    # self.address_tiles['double studio:recreation:pool table'] 
    #   == {(29, 14), (31, 11), (30, 14), (32, 11), ...}, 
    self.address_tiles = dict()
    for i in range(self.maze_height):
      for j in range(self.maze_width): 
        addresses = []
        if self.tiles[i][j]["sector"]: 
          add = f'{self.tiles[i][j]["world"]}:'
          add += f'{self.tiles[i][j]["sector"]}'
          addresses += [add]
        if self.tiles[i][j]["arena"]: 
          add = f'{self.tiles[i][j]["world"]}:'
          add += f'{self.tiles[i][j]["sector"]}:'
          add += f'{self.tiles[i][j]["arena"]}'
          addresses += [add]
        if self.tiles[i][j]["game_object"]: 
          add = f'{self.tiles[i][j]["world"]}:'
          add += f'{self.tiles[i][j]["sector"]}:'
          add += f'{self.tiles[i][j]["arena"]}:'
          add += f'{self.tiles[i][j]["game_object"]}'
          addresses += [add]
        if self.tiles[i][j]["spawning_location"]: 
          add = f'<spawn_loc>{self.tiles[i][j]["spawning_location"]}'
          addresses += [add]

        for add in addresses: 
          if add in self.address_tiles: 
            self.address_tiles[add].add((j, i))
          else: 
            self.address_tiles[add] = set([(j, i)])


  def turn_coordinate_to_tile(self, px_coordinate): 
    """
    将像素坐标转换为瓦片坐标。

    输入
      px_coordinate: 我们感兴趣的像素坐标。格式为 x, y。
    输出
      瓦片坐标 (x, y): 对应于像素坐标的瓦片坐标。
    输出示例
      给定 (1600, 384)，输出 (50, 12)
    """
    x = math.ceil(px_coordinate[0]/self.sq_tile_size)
    y = math.ceil(px_coordinate[1]/self.sq_tile_size)
    return (x, y)


  def access_tile(self, tile): 
    """
    返回存储在 self.tiles 中指定 x, y 位置的瓦片详细信息字典。

    输入
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
    输出
      指定瓦片的详细信息字典。
    输出示例
      给定 (58, 9),
      self.tiles[9][58] = {'world': 'double studio', 
            'sector': 'double studio', 'arena': 'bedroom 2', 
            'game_object': 'bed', 'spawning_location': 'bedroom-2-a', 
            'collision': False,
            'events': {('double studio:double studio:bedroom 2:bed',
                       None, None)}} 
    """
    x = tile[0]
    y = tile[1]
    return self.tiles[y][x]


  def get_tile_path(self, tile, level): 
    """
    根据坐标获取瓦片的字符串地址。通过提供字符串级别的描述来指定级别。

    输入:
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
      level: world (世界), sector (区域), arena (竞技场), 或 game object (游戏对象)
    输出
      瓦片的字符串地址。
    输出示例
      给定 tile=(58, 9) 且 level=arena,
      "double studio:double studio:bedroom 2"
    """
    x = tile[0]
    y = tile[1]
    tile = self.tiles[y][x]

    path = f"{tile['world']}"
    if level == "world": 
      return path
    else: 
      path += f":{tile['sector']}"
    
    if level == "sector": 
      return path
    else: 
      path += f":{tile['arena']}"

    if level == "arena": 
      return path
    else: 
      path += f":{tile['game_object']}"

    return path


  def get_nearby_tiles(self, tile, vision_r): 
    """
    给定当前瓦片和 vision_r (视觉半径)，返回半径范围内的瓦片列表。
    请注意，此实现在确定半径范围时查看的是方形边界。
    即，对于 vision_r，返回 x 标记的瓦片。
    x x x x x 
    x x x x x
    x x P x x 
    x x x x x
    x x x x x

    输入:
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
      vision_r: 角色的视觉半径。
    输出:
      nearby_tiles: 半径范围内的瓦片列表。
    """
    left_end = 0
    if tile[0] - vision_r > left_end: 
      left_end = tile[0] - vision_r

    right_end = self.maze_width - 1
    if tile[0] + vision_r + 1 < right_end: 
      right_end = tile[0] + vision_r + 1

    bottom_end = self.maze_height - 1
    if tile[1] + vision_r + 1 < bottom_end: 
      bottom_end = tile[1] + vision_r + 1

    top_end = 0
    if tile[1] - vision_r > top_end: 
      top_end = tile[1] - vision_r 

    nearby_tiles = []
    for i in range(left_end, right_end): 
      for j in range(top_end, bottom_end): 
        nearby_tiles += [(i, j)]
    return nearby_tiles


  def add_event_from_tile(self, curr_event, tile): 
    """
    将事件三元组添加到瓦片。

    输入:
      curr_event: 当前事件三元组。
        例如：('double studio:double studio:bedroom 2:bed', None, None)
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
    输出:
      无
    """
    self.tiles[tile[1]][tile[0]]["events"].add(curr_event)


  def remove_event_from_tile(self, curr_event, tile):
    """
    从瓦片中移除事件三元组。

    输入:
      curr_event: 当前事件三元组。
        例如：('double studio:double studio:bedroom 2:bed', None, None)
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
    输出:
      无
    """
    curr_tile_ev_cp = self.tiles[tile[1]][tile[0]]["events"].copy()
    for event in curr_tile_ev_cp: 
      if event == curr_event:  
        self.tiles[tile[1]][tile[0]]["events"].remove(event)


  def turn_event_from_tile_idle(self, curr_event, tile):
    curr_tile_ev_cp = self.tiles[tile[1]][tile[0]]["events"].copy()
    for event in curr_tile_ev_cp: 
      if event == curr_event:  
        self.tiles[tile[1]][tile[0]]["events"].remove(event)
        new_event = (event[0], None, None, None)
        self.tiles[tile[1]][tile[0]]["events"].add(new_event)


  def remove_subject_events_from_tile(self, subject, tile):
    """
    从瓦片中移除具有输入主体的事件三元组。

    输入:
      subject: "Isabella Rodriguez" (伊莎贝拉·罗德里格斯)
      tile: 我们感兴趣的瓦片坐标，格式为 (x, y)。
    输出:
      无
    """
    curr_tile_ev_cp = self.tiles[tile[1]][tile[0]]["events"].copy()
    for event in curr_tile_ev_cp: 
      if event[0] == subject:  
        self.tiles[tile[1]][tile[0]]["events"].remove(event)


































