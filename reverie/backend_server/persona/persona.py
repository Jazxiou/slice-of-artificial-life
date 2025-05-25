"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: persona.py
描述: 定义了为 Reverie 中的代理提供支持的 Persona 类。

注意 (2023年5月1日) -- 这实际上就是 GenerativeAgent 类。Persona 是
我们在2022年内部使用的术语，源于我们的 Social Simulacra 论文。
"""
import math
import sys
import datetime
import random
sys.path.append('../')

from global_methods import *

from persona.memory_structures.spatial_memory import *
from persona.memory_structures.associative_memory import *
from persona.memory_structures.scratch import *

from persona.cognitive_modules.perceive import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.plan import *
from persona.cognitive_modules.reflect import *
from persona.cognitive_modules.execute import *
from persona.cognitive_modules.converse import *

class Persona: 
  def __init__(self, name, folder_mem_saved=False):
    # 角色基本状态
    # <name> 是角色的全名。这是 Reverie 中角色的唯一标识符。
    self.name = name

    # 角色记忆
    # 如果 folder_mem_saved 中已有记忆，则加载它。否则，我们创建新的记忆实例。
    # <s_mem> 是角色的空间记忆。
    f_s_mem_saved = f"{folder_mem_saved}/bootstrap_memory/spatial_memory.json"
    self.s_mem = MemoryTree(f_s_mem_saved)
    # <a_mem> 是角色的联想记忆。
    f_a_mem_saved = f"{folder_mem_saved}/bootstrap_memory/associative_memory"
    self.a_mem = AssociativeMemory(f_a_mem_saved)
    # <scratch> 是角色的暂存（短期记忆）空间。
    scratch_saved = f"{folder_mem_saved}/bootstrap_memory/scratch.json"
    self.scratch = Scratch(scratch_saved)


  def save(self, save_folder): 
    """
    保存角色的当前状态（即记忆）。

    输入:
      save_folder: 我们将保存角色状态的文件夹。
    输出:
      无
    """
    # 空间记忆包含一个 JSON 格式的树。
    # e.g., {"double studio": 
    #         {"double studio": 
    #           {"bedroom 2": 
    #             ["painting", "easel", "closet", "bed"]}}}
    f_s_mem = f"{save_folder}/spatial_memory.json"
    self.s_mem.save(f_s_mem)
    
    # 联想记忆包含一个 CSV 文件，包含以下行：
    # [event.type, event.created, event.expiration, s, p, o]
    # e.g., event,2022-10-23 00:00:00,,Isabella Rodriguez,is,idle
    f_a_mem = f"{save_folder}/associative_memory"
    self.a_mem.save(f_a_mem)

    # 暂存空间包含与角色相关的非永久性数据。当它被保存时，它采用 JSON 格式。当我们加载它时，我们将值移动到 Python 变量中。
    f_scratch = f"{save_folder}/scratch.json"
    self.scratch.save(f_scratch)


  def perceive(self, maze):
    """
    此函数接收当前迷宫，并返回角色周围发生的事件。重要的是，感知由角色的两个关键超参数引导：
    1) att_bandwidth (注意力带宽)，以及 2) retention (记忆保留度)。

    首先，<att_bandwidth> 决定了角色可以感知的附近事件的数量。
    假设在角色的视觉半径内有10个事件——感知所有10个可能太多了。
    因此，如果事件过多，角色会感知最近的 att_bandwidth 个事件。

    其次，角色不希望在每个时间步都感知和思考相同的事件。
    这就是 <retention> 发挥作用的地方——角色记忆的内容有时间顺序。
    因此，如果角色的记忆中包含了在最近的 retention 时间内发生的当前周围事件，
    则无需再次感知。xx

    输入:
      maze: 世界的当前 <Maze> 实例。
    输出:
      一个 <ConceptNode> (概念节点) 列表，包含感知到的新事件。
        参见 associative_memory.py —— 但为了让你了解它接收的输入内容： "s, p, o, desc, persona.scratch.curr_time"
    """
    return perceive(self, maze)


  def retrieve(self, perceived):
    """
    此函数将角色感知到的事件作为输入，
    并返回一组相关的事件和想法，角色在规划时需要将这些作为上下文来考虑。

    输入:
      perceive: 一个 <ConceptNode> (概念节点) 列表，包含感知到的新事件。
    输出:
      retrieved: 字典的字典。第一层指定一个事件，
                 而后者层指定相关的 "curr_event" (当前事件), "events" (事件),
                 和 "thoughts" (想法)。
    """
    return retrieve(self, perceived)


  def plan(self, maze, personas, new_day, retrieved):
    """
    认知链的主要功能。它接收检索到的记忆和感知，
    以及迷宫和第一天的状态，以便为角色进行长期和短期规划。

    输入:
      maze: 世界的当前 <Maze> 实例。
      personas: 一个字典，其中包含所有角色名称作为键，Persona 实例作为值。
      new_day: 可以是以下三个值之一。
        1) <布尔值> False -- 不是 "新的一天" 周期（如果是，我们需要
           为角色调用长期规划序列）。
        2) <字符串> "First day" -- 这确实是模拟的开始，
           所以它不仅是新的一天，也是第一天。
        3) <字符串> "New day" -- 这是新的一天。 
      retrieved: 字典的字典。第一层指定一个事件，
                 而后者层指定相关的 "curr_event" (当前事件), "events" (事件),
                 和 "thoughts" (想法)。
    输出
      角色的目标动作地址 (persona.scratch.act_address)。
    """
    return plan(self, maze, personas, new_day, retrieved)


  def execute(self, maze, personas, plan):
    """
    此函数接收代理的当前计划并输出一个具体的执行方案
    （使用什么对象，以及移动到哪个瓦片）。

    输入:
      maze: 世界的当前 <Maze> 实例。
      personas: 一个字典，其中包含所有角色名称作为键，Persona 实例作为值。
      plan: 角色的目标动作地址
            (persona.scratch.act_address)。
    输出:
      execution: 一个包含以下组件的三元组：
        <next_tile> 是一个 x,y 坐标。例如：(58, 9)
        <pronunciatio> 是一个表情符号。
        <description> 是动作的字符串描述。例如：
        writing her next novel (editing her novel) 
        @ double studio:double studio:common room:sofa
    """
    return execute(self, maze, personas, plan)


  def reflect(self):
    """
    回顾角色的记忆并基于此产生新的想法。

    输入:
      无
    输出:
      无
    """
    reflect(self)


  def move(self, maze, personas, curr_tile, curr_time):
    """
    这是调用我们主序列的主要认知功能。

    输入:
      maze: 当前世界的 Maze 类。
      personas: 一个字典，其中包含所有角色名称作为键，Persona 实例作为值。
      curr_tile: 一个元组，以 (行, 列) 形式指定角色的当前瓦片位置。例如：(58, 39)
      curr_time: 表示游戏当前时间的 datetime 实例。
    输出:
      execution: 一个包含以下组件的三元组：
        <next_tile> 是一个 x,y 坐标。例如：(58, 9)
        <pronunciatio> 是一个表情符号。
        <description> 是动作的字符串描述。例如：
        writing her next novel (editing her novel) 
        @ double studio:double studio:common room:sofa
    """
    # 用 <curr_tile> 更新角色的暂存记忆。
    self.scratch.curr_tile = curr_tile

    # 我们判断角色是否开始了新的一天，如果是新的一天，是否是模拟的第一天。这很重要，因为我们在新的一天开始时为角色设定长期计划。
    new_day = False
    if not self.scratch.curr_time: 
      new_day = "First day" # Do not translate
    elif (self.scratch.curr_time.strftime('%A %B %d')
          != curr_time.strftime('%A %B %d')):
      new_day = "New day" # Do not translate
    self.scratch.curr_time = curr_time

    # 主要认知序列从这里开始。
    perceived = self.perceive(maze)
    retrieved = self.retrieve(perceived)
    plan = self.plan(maze, personas, new_day, retrieved)
    self.reflect()

    # <execution> 是一个包含以下组件的三元组：
    # <next_tile> 是一个 x,y 坐标。例如：(58, 9)
    # <pronunciatio> 是一个表情符号。例如："\ud83d\udca4"
    # <description> 是动作的字符串描述。例如：
    #   writing her next novel (editing her novel) 
    #   @ double studio:double studio:common room:sofa
    return self.execute(maze, personas, plan)


  def open_convo_session(self, convo_mode): 
    open_convo_session(self, convo_mode)
    




































