"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: retrieve.py
描述: 此文件定义了生成式代理的“检索”模块。
"""
import sys
sys.path.append('../../')

from global_methods import *
from persona.prompt_template.gpt_structure import *

from numpy import dot
from numpy.linalg import norm

def retrieve(persona, perceived): 
  """
  此函数将角色感知到的事件作为输入，
  并返回一组相关的事件和想法，角色在规划时需要将这些作为上下文来考虑。

  输入:
    perceived: 一个事件 <ConceptNode> (概念节点) 列表，代表角色周围发生的任何事件。
               此处包含的内容由 att_bandwidth (注意力带宽) 和 retention (记忆保留度)
               超参数控制。
  输出:
    retrieved: 一个字典的字典。第一层指定一个事件，
               而后者层指定相关的 "curr_event" (当前事件), "events" (事件),
               和 "thoughts" (想法)。
  """
  # 我们分别检索事件和想法。
  retrieved = dict()
  for event in perceived: 
    retrieved[event.description] = dict()
    retrieved[event.description]["curr_event"] = event
    
    relevant_events = persona.a_mem.retrieve_relevant_events(
                        event.subject, event.predicate, event.object)
    retrieved[event.description]["events"] = list(relevant_events)

    relevant_thoughts = persona.a_mem.retrieve_relevant_thoughts(
                          event.subject, event.predicate, event.object)
    retrieved[event.description]["thoughts"] = list(relevant_thoughts)
    
  return retrieved


def cos_sim(a, b): 
  """
  此函数计算两个输入向量 'a' 和 'b' 之间的余弦相似度。
  余弦相似度是内积空间中两个非零向量之间相似性的度量，
  它测量它们之间夹角的余弦值。

  输入:
    a: 一维数组对象
    b: 一维数组对象
  输出:
    一个标量值，表示输入向量 'a' 和 'b' 之间的余弦相似度。
  
  输入示例:
    a = [0.3, 0.2, 0.5]
    b = [0.2, 0.2, 0.5]
  """
  return dot(a, b)/(norm(a)*norm(b))


def normalize_dict_floats(d, target_min, target_max):
  """
  此函数将给定字典 'd' 的浮点值归一化到目标最小值和最大值之间。
  归一化通过将值缩放到目标范围来完成，同时保持原始值之间的相对比例。

  输入:
    d: 字典。其浮点值需要归一化的输入字典。
    target_min: 整数或浮点数。原始值应缩放到的最小值。
    target_max: 整数或浮点数。原始值应缩放到的最大值。
  输出:
    d: 一个新字典，其键与输入相同，但浮点值已在 target_min 和 target_max 之间归一化。

  输入示例:
    d = {'a':1.2,'b':3.4,'c':5.6,'d':7.8}
    target_min = -5
    target_max = 5
  """
  min_val = min(val for val in d.values())
  max_val = max(val for val in d.values())
  range_val = max_val - min_val

  if range_val == 0: 
    for key, val in d.items(): 
      d[key] = (target_max - target_min)/2
  else: 
    for key, val in d.items():
      d[key] = ((val - min_val) * (target_max - target_min) 
                / range_val + target_min)
  return d


def top_highest_x_values(d, x):
  """
  此函数接收一个字典 'd' 和一个整数 'x' 作为输入，
  并返回一个新字典，其中包含输入字典 'd' 中值最高的 'x' 个键值对。

  输入:
    d: 字典。从中提取值最高的 'x' 个键值对的输入字典。
    x: 整数。要从输入字典中提取的值最高的键值对的数量。
  输出:
    一个新字典，其中包含输入字典 'd' 中值最高的 'x' 个键值对。
  
  输入示例:
    d = {'a':1.2,'b':3.4,'c':5.6,'d':7.8}
    x = 3
  """
  top_v = dict(sorted(d.items(), 
                      key=lambda item: item[1], 
                      reverse=True)[:x])
  return top_v


def extract_recency(persona, nodes):
  """
  获取当前的 Persona 对象和按时间顺序排列的节点列表，
  并输出一个计算了新近度得分的字典。

  输入:
    persona: 我们正在检索其记忆的当前角色。
    nodes: 按时间顺序排列的 Node 对象列表。
  输出:
    recency_out: 一个字典，其键是 node.node_id，值是表示新近度得分的浮点数。
  """
  recency_vals = [persona.scratch.recency_decay ** i 
                  for i in range(1, len(nodes) + 1)]
  
  recency_out = dict()
  for count, node in enumerate(nodes): 
    recency_out[node.node_id] = recency_vals[count]

  return recency_out


def extract_importance(persona, nodes):
  """
  获取当前的 Persona 对象和按时间顺序排列的节点列表，
  并输出一个计算了重要性得分的字典。

  输入:
    persona: 我们正在检索其记忆的当前角色。
    nodes: 按时间顺序排列的 Node 对象列表。
  输出:
    importance_out: 一个字典，其键是 node.node_id，值是表示重要性得分的浮点数。
  """
  importance_out = dict()
  for count, node in enumerate(nodes): 
    importance_out[node.node_id] = node.poignancy

  return importance_out


def extract_relevance(persona, nodes, focal_pt): 
  """
  获取当前的 Persona 对象、按时间顺序排列的节点列表以及 focal_pt 字符串，
  并输出一个计算了相关性得分的字典。

  输入:
    persona: 我们正在检索其记忆的当前角色。
    nodes: 按时间顺序排列的 Node 对象列表。
    focal_pt: 描述当前焦点思想或事件的字符串。
  输出:
    relevance_out: 一个字典，其键是 node.node_id，值是表示相关性得分的浮点数。
  """
  focal_embedding = get_embedding(focal_pt)

  relevance_out = dict()
  for count, node in enumerate(nodes): 
    node_embedding = persona.a_mem.embeddings[node.embedding_key]
    relevance_out[node.node_id] = cos_sim(node_embedding, focal_embedding)

  return relevance_out


def new_retrieve(persona, focal_points, n_count=30): 
  """
  给定当前角色和焦点（焦点是我们正在检索的事件或想法），
  我们为每个焦点检索一组节点并返回一个字典。

  输入:
    persona: 我们正在检索其记忆的当前角色对象。
    focal_points: 焦点列表（当前检索焦点的事件或想法的字符串描述）。
  输出:
    retrieved: 一个字典，其键是字符串焦点，值是代理联想记忆中的 Node 对象列表。

  输入示例:
    persona = <persona> 对象
    focal_points = ["你好吗？", "珍妮正在池塘里游泳"]
  """
  # <retrieved> 是我们返回的主要字典
  retrieved = dict() 
  for focal_pt in focal_points: 
    # 从代理的记忆中获取所有节点（包括想法和事件）并
    # 按创建日期时间对它们进行排序。
    # 你也可以想象获取原始对话，但目前暂时这样。
    nodes = [[i.last_accessed, i]
              for i in persona.a_mem.seq_event + persona.a_mem.seq_thought
              if "idle" not in i.embedding_key] # "idle" is a keyword, do not translate
    nodes = sorted(nodes, key=lambda x: x[0])
    nodes = [i for created, i in nodes]

    # 计算组件字典并对其进行归一化。
    recency_out = extract_recency(persona, nodes)
    recency_out = normalize_dict_floats(recency_out, 0, 1)
    importance_out = extract_importance(persona, nodes)
    importance_out = normalize_dict_floats(importance_out, 0, 1)  
    relevance_out = extract_relevance(persona, nodes, focal_pt)
    relevance_out = normalize_dict_floats(relevance_out, 0, 1)

    # 计算结合了组件值的最终得分。
    # 笔记：测试不同的权重。[1, 1, 1] 的效果通常不错，
    # 但将来这些权重可能应该通过学习得到，
    # 或许可以通过类似强化学习的过程。
    # gw = [1, 1, 1]
    # gw = [1, 2, 1]
    gw = [0.5, 3, 2]
    master_out = dict()
    for key in recency_out.keys(): 
      master_out[key] = (persona.scratch.recency_w*recency_out[key]*gw[0] 
                     + persona.scratch.relevance_w*relevance_out[key]*gw[1] 
                     + persona.scratch.importance_w*importance_out[key]*gw[2])

    master_out = top_highest_x_values(master_out, len(master_out.keys()))
    for key, val in master_out.items(): 
      print (persona.a_mem.id_to_node[key].embedding_key, val) # DEBUG
      print (persona.scratch.recency_w*recency_out[key]*1,  # DEBUG
             persona.scratch.relevance_w*relevance_out[key]*1,  # DEBUG
             persona.scratch.importance_w*importance_out[key]*1) # DEBUG

    # 提取最高的 x 个值。
    # <master_out> 的键是 node.id，值是浮点数。一旦我们得到
    # 最高的 x 个值，我们希望将 node.id 转换为节点并返回
    # 节点列表。
    master_out = top_highest_x_values(master_out, n_count)
    master_nodes = [persona.a_mem.id_to_node[key] 
                    for key in list(master_out.keys())]

    for n in master_nodes: 
      n.last_accessed = persona.scratch.curr_time
      
    retrieved[focal_pt] = master_nodes

  return retrieved













