"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: perceive.py
描述: 此文件定义了生成式代理的“感知”模块。
"""
import sys
sys.path.append('../../')

from operator import itemgetter
from global_methods import *
from persona.prompt_template.gpt_structure import *
from persona.prompt_template.run_gpt_prompt import *

def generate_poig_score(persona, event_type, description): 
  if "处于空闲状态" in description: 
    return 1

  if event_type == "event": 
    return run_gpt_prompt_event_poignancy(persona, description)[0]
  elif event_type == "chat": 
    return run_gpt_prompt_chat_poignancy(persona, 
                           persona.scratch.act_description)[0]

def perceive(persona, maze): 
  """
  感知角色周围发生的事件，并将事件和空间信息保存到记忆中。

  我们首先感知角色附近的事件，范围由其 <vision_r> (视觉半径) 决定。
  如果该半径内发生大量事件，我们将选取 <att_bandwidth> (注意力带宽) 数量的最近事件。
  最后，我们根据 <retention> (记忆保留度) 检查是否有新事件。
  如果是新事件，我们将保存这些事件并返回这些事件的 <ConceptNode> (概念节点) 实例。

  输入:
    persona: 代表当前角色的 <Persona> 实例。
    maze: 代表角色当前所在迷宫的 <Maze> 实例。
  输出:
    ret_events: 一个 <ConceptNode> 列表，包含感知到的新事件。
  """
  # 感知空间
  # 我们根据当前瓦片和角色的视觉
  # 半径获取附近的瓦片。
  nearby_tiles = maze.get_nearby_tiles(persona.scratch.curr_tile, 
                                       persona.scratch.vision_r)

  # 然后我们存储感知到的空间。注意角色的 s_mem (空间记忆)
  # 是以使用字典构建的树的形式存在的。
  for i in nearby_tiles: 
    i = maze.access_tile(i)
    if i["world"]: 
      if (i["world"] not in persona.s_mem.tree): 
        persona.s_mem.tree[i["world"]] = {}
    if i["sector"]: 
      if (i["sector"] not in persona.s_mem.tree[i["world"]]): 
        persona.s_mem.tree[i["world"]][i["sector"]] = {}
    if i["arena"]: 
      if (i["arena"] not in persona.s_mem.tree[i["world"]]
                                              [i["sector"]]): 
        persona.s_mem.tree[i["world"]][i["sector"]][i["arena"]] = []
    if i["game_object"]: 
      if (i["game_object"] not in persona.s_mem.tree[i["world"]]
                                                    [i["sector"]]
                                                    [i["arena"]]): 
        persona.s_mem.tree[i["world"]][i["sector"]][i["arena"]] += [
                                                             i["game_object"]]

  # 感知事件。
  # 我们将感知与角色当前所在竞技场
  # 相同的竞技场中发生的事件。
  curr_arena_path = maze.get_tile_path(persona.scratch.curr_tile, "arena")
  # 我们不会重复感知同一个事件（如果一个物体
  # 跨越多个瓦片，可能会发生这种情况）。
  percept_events_set = set()
  # 我们将根据距离对感知进行排序，最近的
  # 优先处理。
  percept_events_list = []
  # 首先，我们将附近瓦片中发生的所有事件放入
  # percept_events_list (感知事件列表)
  for tile in nearby_tiles: 
    tile_details = maze.access_tile(tile)
    if tile_details["events"]: 
      if maze.get_tile_path(tile, "arena") == curr_arena_path:  
        # 这计算了角色的当前瓦片
        # 与目标瓦片之间的距离。
        dist = math.dist([tile[0], tile[1]], 
                         [persona.scratch.curr_tile[0], 
                          persona.scratch.curr_tile[1]])
        # 将任何相关事件及其距离信息添加到我们的临时集合/列表中。
        for event in tile_details["events"]: 
          if event not in percept_events_set: 
            percept_events_list += [[dist, event]]
            percept_events_set.add(event)

  # 我们进行排序，并且只感知最近的 persona.scratch.att_bandwidth (注意力带宽) 个
  # 事件。如果带宽较大，则表示角色可以在
  # 较小区域内感知更多元素。
  percept_events_list = sorted(percept_events_list, key=itemgetter(0))
  perceived_events = []
  for dist, event in percept_events_list[:persona.scratch.att_bandwidth]: 
    perceived_events += [event]

  # 存储事件。
  # <ret_events> 是来自角色
  # 联想记忆的 <ConceptNode> (概念节点) 实例列表。
  ret_events = []
  for p_event in perceived_events: 
    s, p, o, desc = p_event
    if not p: 
      # 如果对象不存在，则我们将事件默认为 "idle" (空闲)。
      p = "is"
      o = "空闲"
      desc = "空闲"
    desc = f"{s.split(':')[-1]} 是 {desc}"
    p_event = (s, p, o)

    # 我们检索最新的 persona.scratch.retention (记忆保留度) 个事件。如果有
    # 新的事件发生（即 p_event 不在 latest_events 中），
    # 那么我们就将该事件添加到 a_mem (联想记忆) 并返回它。
    latest_events = persona.a_mem.get_summarized_latest_events(
                                    persona.scratch.retention)
    if p_event not in latest_events:
      # 我们首先管理关键词。
      keywords = set()
      sub = p_event[0]
      obj = p_event[2]
      if ":" in p_event[0]: 
        sub = p_event[0].split(":")[-1]
      if ":" in p_event[2]: 
        obj = p_event[2].split(":")[-1]
      keywords.update([sub, obj])

      # 获取事件嵌入
      desc_embedding_in = desc
      if "(" in desc: 
        desc_embedding_in = (desc_embedding_in.split("(")[1]
                                              .split(")")[0]
                                              .strip())
      if desc_embedding_in in persona.a_mem.embeddings: 
        event_embedding = persona.a_mem.embeddings[desc_embedding_in]
      else: 
        event_embedding = get_embedding(desc_embedding_in)
      event_embedding_pair = (desc_embedding_in, event_embedding)
      
      # 获取事件重要性（poignancy）。
      event_poignancy = generate_poig_score(persona, 
                                            "event", 
                                            desc_embedding_in)

      # 如果我们观察到角色的自言自语，我们在此将其包含在角色的记忆中。
      chat_node_ids = []
      if p_event[0] == f"{persona.name}" and p_event[1] == "chat with": 
        curr_event = persona.scratch.act_event
        if persona.scratch.act_description in persona.a_mem.embeddings: 
          chat_embedding = persona.a_mem.embeddings[
                             persona.scratch.act_description]
        else: 
          chat_embedding = get_embedding(persona.scratch
                                                .act_description)
        chat_embedding_pair = (persona.scratch.act_description, 
                               chat_embedding)
        chat_poignancy = generate_poig_score(persona, "chat", 
                                             persona.scratch.act_description)
        chat_node = persona.a_mem.add_chat(persona.scratch.curr_time, None,
                      curr_event[0], curr_event[1], curr_event[2], 
                      persona.scratch.act_description, keywords, 
                      chat_poignancy, chat_embedding_pair, 
                      persona.scratch.chat)
        chat_node_ids = [chat_node.node_id]

      # 最后，我们将当前事件添加到代理的记忆中。
      ret_events += [persona.a_mem.add_event(persona.scratch.curr_time, None,
                           s, p, o, desc, keywords, event_poignancy, 
                           event_embedding_pair, chat_node_ids)]
      persona.scratch.importance_trigger_curr -= event_poignancy
      persona.scratch.importance_ele_n += 1

  return ret_events




  











