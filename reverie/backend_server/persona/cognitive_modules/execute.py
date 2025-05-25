"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: execute.py
描述: 此文件定义了生成式代理的“行动”模块。
"""
import sys
import random
sys.path.append('../../')

from global_methods import *
from path_finder import *
from utils import *

def execute(persona, maze, personas, plan): 
  """
  给定一个计划（动作的字符串地址），我们执行该计划（实际
  输出角色的瓦片坐标路径和下一个坐标）。

  输入:
    persona: 当前的 <Persona> 实例。
    maze: 当前 <Maze> 的实例。
    personas: 世界中所有角色的字典。
    plan: 这是我们需要执行的动作的字符串地址。
       格式为 "{世界}:{区域}:{竞技场}:{游戏对象}"。
       重要的是，访问此地址时不要使用负索引（例如 [-1]），
       因为在某些情况下，末尾的地址元素可能不存在。
       例如："dolores double studio:double studio:bedroom 1:bed"
  
  输出:
    执行结果 (下一个瓦片坐标, 表情符号, 描述文字)
  """
  if "<random>" in plan and persona.scratch.planned_path == []: 
    persona.scratch.act_path_set = False

  # <act_path_set> 如果当前动作的路径已设置，则为 True。
  # 否则为 False，表示我们需要构建一条新路径。
  if not persona.scratch.act_path_set: 
    # <target_tiles> 是角色可能前往执行当前动作的瓦片坐标列表。
    # 目标是选择其中一个。
    target_tiles = None

    print ('aldhfoaf/????') # DEBUG
    print (plan) # DEBUG

    if "<persona>" in plan: 
      # 执行角色间互动。
      target_p_tile = (personas[plan.split("<persona>")[-1].strip()]
                       .scratch.curr_tile)
      potential_path = path_finder(maze.collision_maze, 
                                   persona.scratch.curr_tile, 
                                   target_p_tile, 
                                   collision_block_id)
      if len(potential_path) <= 2: 
        target_tiles = [potential_path[0]]
      else: 
        potential_1 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)], 
                                collision_block_id)
        potential_2 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)+1], 
                                collision_block_id)
        if len(potential_1) <= len(potential_2): 
          target_tiles = [potential_path[int(len(potential_path)/2)]]
        else: 
          target_tiles = [potential_path[int(len(potential_path)/2+1)]]
    
    elif "<waiting>" in plan: 
      # 执行角色在执行其动作前决定等待的互动。
      x = int(plan.split()[1])
      y = int(plan.split()[2])
      target_tiles = [[x, y]]

    elif "<random>" in plan: 
      # 执行随机位置动作。
      plan = ":".join(plan.split(":")[:-1])
      target_tiles = maze.address_tiles[plan]
      target_tiles = random.sample(list(target_tiles), 1)

    else: 
      # 这是我们的默认执行方式。我们简单地将角色带到
      # 当前动作发生的地点。
      # 检索目标地址。再次说明，plan 是字符串形式的动作地址。
      # <maze.address_tiles> 接收此地址并返回候选
      # 坐标。
      if plan not in maze.address_tiles: 
        maze.address_tiles["Johnson Park:park:park garden"] #错误ERRRRRRRR
      else: 
        target_tiles = maze.address_tiles[plan]

    # 有时会返回多个瓦片（例如，一张桌子
    # 可能跨越多个坐标）。因此，我们在这里采样一些。然后从
    # 随机样本中，我们将选择最近的那些。
    if len(target_tiles) < 4: 
      target_tiles = random.sample(list(target_tiles), len(target_tiles))
    else:
      target_tiles = random.sample(list(target_tiles), 4)
    # 如果可能，我们希望角色在前往迷宫中相同位置时占据不同的瓦片。
    # 他们最终在同一瓦片上也可以，但我们尝试降低这种可能性。
    # 我们在这里处理重叠问题。
    persona_name_set = set(personas.keys())
    new_target_tiles = []
    for i in target_tiles: 
      curr_event_set = maze.access_tile(i)["events"]
      pass_curr_tile = False
      for j in curr_event_set: 
        if j[0] in persona_name_set: 
          pass_curr_tile = True
      if not pass_curr_tile: 
        new_target_tiles += [i]
    if len(new_target_tiles) == 0: 
      new_target_tiles = target_tiles
    target_tiles = new_target_tiles

    # 既然我们已经确定了目标瓦片，我们就找到
    # 到其中一个目标瓦片的最短路径。
    curr_tile = persona.scratch.curr_tile
    collision_maze = maze.collision_maze
    closest_target_tile = None
    path = None
    for i in target_tiles: 
      # path_finder 接收一个 collision_mze（碰撞迷宫）和 curr_tile 坐标作为
      # 输入，并返回一个坐标元组列表，该列表成为
      # 路径。
      # 例如：[(0, 1), (1, 1), (1, 2), (1, 3), (1, 4)...]
      curr_path = path_finder(maze.collision_maze, 
                              curr_tile, 
                              i, 
                              collision_block_id)
      if not closest_target_tile: 
        closest_target_tile = i
        path = curr_path
      elif len(curr_path) < len(path): 
        closest_target_tile = i
        path = curr_path

    # 实际设置 <planned_path> 和 <act_path_set>。我们删除了
    # planned_path 中的第一个元素，因为它包含了 curr_tile。
    persona.scratch.planned_path = path[1:]
    persona.scratch.act_path_set = True
  
  # 设置下一个即时步骤。如果没有剩余的 <planned_path>，
  # 我们将停留在当前瓦片，否则，我们将移动到路径中的下一个瓦片。
  ret = persona.scratch.curr_tile
  if persona.scratch.planned_path: 
    ret = persona.scratch.planned_path[0]
    persona.scratch.planned_path = persona.scratch.planned_path[1:]

  description = f"{persona.scratch.act_description}"
  description += f" @ {persona.scratch.act_address}"

  execution = ret, persona.scratch.act_pronunciatio, description
  return execution















