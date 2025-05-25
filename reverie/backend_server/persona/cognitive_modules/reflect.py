"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: reflect.py
描述: 此文件定义了生成式代理的“反思”模块。
"""
import sys
sys.path.append('../../')

import datetime
import random

from numpy import dot
from numpy.linalg import norm

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.prompt_template.gpt_structure import *
from persona.cognitive_modules.retrieve import *

def generate_focal_points(persona, n=3): 
  if debug: print ("GNS FUNCTION: <generate_focal_points>")
  
  nodes = [[i.last_accessed, i]
            for i in persona.a_mem.seq_event + persona.a_mem.seq_thought
            if "idle" not in i.embedding_key] # "idle" is a keyword, do not translate

  nodes = sorted(nodes, key=lambda x: x[0])
  nodes = [i for created, i in nodes]

  statements = ""
  for node in nodes[-1*persona.scratch.importance_ele_n:]: 
    statements += node.embedding_key + "\n"

  return run_gpt_prompt_focal_pt(persona, statements, n)[0]


def generate_insights_and_evidence(persona, nodes, n=5): 
  if debug: print ("GNS FUNCTION: <generate_insights_and_evidence>")

  statements = ""
  for count, node in enumerate(nodes): 
    statements += f'{str(count)}. {node.embedding_key}\n'

  ret = run_gpt_prompt_insight_and_guidance(persona, statements, n)[0]

  print (ret)
  try: 

    for thought, evi_raw in ret.items(): 
      evidence_node_id = [nodes[i].node_id for i in evi_raw]
      ret[thought] = evidence_node_id
    return ret
  except: 
    return {"这里是空的": "node_1"} # "node_1" is an ID, do not translate.


def generate_action_event_triple(act_desp, persona): 
  """待办

  输入:
    act_desp: 动作的描述 (例如："sleeping" - 睡觉)
    persona: Persona 类实例
  输出:
    一个用于翻译动作描述的表情符号字符串。 (注意：此描述似乎与pronunciatio重复，事件三元组应为SPO)
  输出示例:
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_event_triple>")
  return run_gpt_prompt_event_triple(act_desp, persona)[0]


def generate_poig_score(persona, event_type, description): 
  if debug: print ("GNS FUNCTION: <generate_poig_score>")

  if "处于空闲状态" in description: 
    return 1

  if event_type == "event" or event_type == "thought": 
    return run_gpt_prompt_event_poignancy(persona, description)[0]
  elif event_type == "chat": 
    return run_gpt_prompt_chat_poignancy(persona, 
                           persona.scratch.act_description)[0]



def generate_planning_thought_on_convo(persona, all_utt):
  if debug: print ("GNS FUNCTION: <generate_planning_thought_on_convo>")
  return run_gpt_prompt_planning_thought_on_convo(persona, all_utt)[0]


def generate_memo_on_convo(persona, all_utt):
  if debug: print ("GNS FUNCTION: <generate_memo_on_convo>")
  return run_gpt_prompt_memo_on_convo(persona, all_utt)[0]




def run_reflect(persona):
  """
  运行实际的反思过程。我们生成焦点，检索任何相关节点，并生成想法和见解。

  输入:
    persona: 当前的 Persona 对象
  输出:
    无
  """
  # 反思需要特定的焦点。首先生成这些焦点。
  focal_points = generate_focal_points(persona, 3)
  # 检索每个焦点的相关 Nodes 对象。
  # <retrieved> 的键是焦点，值是相关的 Nodes。
  retrieved = new_retrieve(persona, focal_points)

  # 对于每个焦点，生成想法并将其保存在
  # 代理的记忆中。
  for focal_pt, nodes in retrieved.items(): 
    xx = [i.embedding_key for i in nodes]
    for xxx in xx: print (xxx) # DEBUG

    thoughts = generate_insights_and_evidence(persona, nodes, 5)
    for thought, evidence in thoughts.items(): 
      created = persona.scratch.curr_time
      expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
      s, p, o = generate_action_event_triple(thought, persona)
      keywords = set([s, p, o])
      thought_poignancy = generate_poig_score(persona, "thought", thought)
      thought_embedding_pair = (thought, get_embedding(thought))

      persona.a_mem.add_thought(created, expiration, s, p, o, 
                                thought, keywords, thought_poignancy, 
                                thought_embedding_pair, evidence)


def reflection_trigger(persona): 
  """
  给定当前角色，判断该角色是否应该进行反思。
  
  我们目前的实现是检查新的重要性指标总和是否已达到设定的（超参数）阈值。

  输入:
    persona: 当前的 Persona 对象
  输出:
    如果运行新的反思，则为 True。
    否则为 False。
  """
  print (persona.scratch.name, "persona.scratch.importance_trigger_curr::", persona.scratch.importance_trigger_curr) # DEBUG
  print (persona.scratch.importance_trigger_max) # DEBUG

  if (persona.scratch.importance_trigger_curr <= 0 and 
      [] != persona.a_mem.seq_event + persona.a_mem.seq_thought): 
    return True 
  return False


def reset_reflection_counter(persona): 
  """
  我们重置用于反思触发器的计数器。

  输入:
    persona: 当前的 Persona 对象
  输出:
    无
  """
  persona_imt_max = persona.scratch.importance_trigger_max
  persona.scratch.importance_trigger_curr = persona_imt_max
  persona.scratch.importance_ele_n = 0


def reflect(persona):
  """
  角色的主要反思模块。我们首先检查是否满足触发条件，
  如果满足，则运行反思并重置任何相关的计数器。

  输入:
    persona: 当前的 Persona 对象
  输出:
    无
  """
  if reflection_trigger(persona): 
    run_reflect(persona)
    reset_reflection_counter(persona)



  # print (persona.scratch.name, "al;sdhfjlsad", persona.scratch.chatting_end_time)
  if persona.scratch.chatting_end_time: 
    # print("DEBUG", persona.scratch.curr_time + datetime.timedelta(0,10))
    if persona.scratch.curr_time + datetime.timedelta(0,10) == persona.scratch.chatting_end_time: 
      # print ("KABOOOOOMMMMMMM") # DEBUG
      all_utt = ""
      if persona.scratch.chat: 
        for row in persona.scratch.chat:  
          all_utt += f"{row[0]}: {row[1]}\n"

      # planning_thought = generate_planning_thought_on_convo(persona, all_utt)
      # print ("init planning: aosdhfpaoisdh90m     ::", f"For {persona.scratch.name}'s planning: {planning_thought}")
      # planning_thought = generate_planning_thought_on_convo(target_persona, all_utt)
      # print ("target planning: aosdhfpaodish90m     ::", f"For {target_persona.scratch.name}'s planning: {planning_thought}")

      # memo_thought = generate_memo_on_convo(persona, all_utt)
      # print ("init memo: aosdhfpaoisdh90m     ::", f"For {persona.scratch.name} {memo_thought}")
      # memo_thought = generate_memo_on_convo(target_persona, all_utt)
      # print ("target memo: aosdhfpsaoish90m     ::", f"For {target_persona.scratch.name} {memo_thought}")
      
      # 确保你也设置了填充内容 (make sure you set the fillings as well)

      # print (persona.a_mem.get_last_chat(persona.scratch.chatting_with).node_id)

      evidence = [persona.a_mem.get_last_chat(persona.scratch.chatting_with).node_id]

      planning_thought = generate_planning_thought_on_convo(persona, all_utt)
      planning_thought = f"关于 {persona.scratch.name} 的计划: {planning_thought}"

      created = persona.scratch.curr_time
      expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
      s, p, o = generate_action_event_triple(planning_thought, persona)
      keywords = set([s, p, o])
      thought_poignancy = generate_poig_score(persona, "thought", planning_thought)
      thought_embedding_pair = (planning_thought, get_embedding(planning_thought))

      persona.a_mem.add_thought(created, expiration, s, p, o, 
                                planning_thought, keywords, thought_poignancy, 
                                thought_embedding_pair, evidence)



      memo_thought = generate_memo_on_convo(persona, all_utt)
      memo_thought = f"{persona.scratch.name} {memo_thought}" # Assuming memo_thought is a complete sentence following the name.

      created = persona.scratch.curr_time
      expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
      s, p, o = generate_action_event_triple(memo_thought, persona)
      keywords = set([s, p, o])
      thought_poignancy = generate_poig_score(persona, "thought", memo_thought)
      thought_embedding_pair = (memo_thought, get_embedding(memo_thought))

      persona.a_mem.add_thought(created, expiration, s, p, o, 
                                memo_thought, keywords, thought_poignancy, 
                                thought_embedding_pair, evidence)



























