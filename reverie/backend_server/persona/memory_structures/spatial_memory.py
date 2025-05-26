"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: spatial_memory.py
描述: 定义了 MemoryTree 类，作为代理的空间记忆，
辅助将其行为锚定在游戏世界中。
"""
import json
import sys
sys.path.append('../../')

from utils import *
from global_methods import *

class MemoryTree: 
  def __init__(self, f_saved): 
    self.tree = {}
    if check_if_file_exists(f_saved): 
      self.tree = json.load(open(f_saved))


  def print_tree(self): 
    def _print_tree(tree, depth):
      dash = " >" * depth
      if type(tree) == type(list()): 
        if tree:
          print (dash, tree)
        return 

      for key, val in tree.items(): 
        if key: 
          print (dash, key)
        _print_tree(val, depth+1)
    
    _print_tree(self.tree, 0)
    

  def save(self, out_json):
    with open(out_json, "w") as outfile:
      json.dump(self.tree, outfile) 



  def get_str_accessible_sectors(self, curr_world): 
    """
    返回一个摘要字符串，包含角色在当前世界（world）中可以访问的所有区域（sector）。

    请注意，某些地方特定角色无法进入。此信息在角色表中提供。
    我们在此函数中考虑了这一点。

    输入
      curr_world: 当前世界名称
    输出
      一个摘要字符串，包含角色可以访问的所有区域。
    输出字符串示例
      "bedroom, kitchen, dining room, office, bathroom"
    """
    x = ", ".join(list(self.tree[curr_world].keys()))
    return x


  def get_str_accessible_sector_arenas(self, sector): 
    """
    返回一个摘要字符串，包含角色在当前区域（sector）中可以访问的所有竞技场（arena）。

    请注意，某些地方特定角色无法进入。此信息在角色表中提供。
    我们在此函数中考虑了这一点。

    输入
      sector: 当前区域的字符串表示 (例如 "world_name:sector_name")
    输出
      一个摘要字符串，包含角色可以访问的所有竞技场。
    输出字符串示例
      "bedroom, kitchen, dining room, office, bathroom"
    """
    curr_world, curr_sector = sector.split(":")
    if not curr_sector: 
      return ""
    x = ", ".join(list(self.tree[curr_world][curr_sector].keys()))
    return x


  def get_str_accessible_arena_game_objects(self, arena):
    """
    获取竞技场（arena）中所有可访问游戏对象的字符串列表。如果
    指定了 temp_address，我们返回该竞技场中可用的对象；
    如果没有指定，则返回我们角色当前所在竞技场中的对象。

    输入
      arena: 竞技场地址 (例如 "world:sector:arena")
    输出
      游戏竞技场中所有可访问游戏对象的字符串列表。
    输出字符串示例
      "phone, charger, bed, nightstand"
    """
    curr_world, curr_sector, curr_arena = arena.split(":")

    if not curr_arena: 
      return ""

    try: 
      x = ", ".join(list(self.tree[curr_world][curr_sector][curr_arena]))
    except: 
      x = ", ".join(list(self.tree[curr_world][curr_sector][curr_arena.lower()]))
    return x


if __name__ == '__main__':
  x = f"../../../../environment/frontend_server/storage/the_ville_base_LinFamily/personas/Eddy Lin/bootstrap_memory/spatial_memory.json"
  x = MemoryTree(x)
  x.print_tree()

  print (x.get_str_accessible_sector_arenas("dolores double studio:double studio"))







