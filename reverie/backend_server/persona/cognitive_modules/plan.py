"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: plan.py
描述: 此文件定义了生成式代理的“计划”模块。
"""
import datetime
import math
import random 
import sys
import time
sys.path.append('../../')

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.converse import *

##############################################################################
# 第二章: 生成
##############################################################################

def generate_wake_up_hour(persona):
  """
  生成角色醒来的时间。这成为我们生成角色每日计划过程中不可或缺的一部分。
  
  角色状态: 身份稳定集, 生活方式, 名字

  输入:
    persona: Persona 类实例
  输出:
    一个表示角色醒来小时的整数
  输出示例:
    8
  """
  if debug: print ("GNS FUNCTION: <generate_wake_up_hour>")
  return int(run_gpt_prompt_wake_up_hour(persona)[0])


def generate_first_daily_plan(persona, wake_up_hour): 
  """
  为角色生成每日计划。
  基本上是跨越一天的长期规划。返回角色今天将要执行的动作列表。
  通常格式如下:
  'wake up and complete the morning routine at 6:00 am', 
  'eat breakfast at 7:00 am',...
  注意动作描述末尾不带句号。

  角色状态: 身份稳定集, 生活方式, cur_data_str (当前日期字符串), 名字

  输入:
    persona: Persona 类实例
    wake_up_hour: 一个整数，表示角色醒来的小时 (例如：8)
  输出:
    一个大致的每日行动列表。
  输出示例:
    ['wake up and complete the morning routine at 6:00 am', 
     'have breakfast and brush teeth at 6:30 am',
     'work on painting project from 8:00 am to 12:00 pm', 
     'have lunch at 12:00 pm', 
     'take a break and watch TV from 2:00 pm to 4:00 pm', 
     'work on painting project from 4:00 pm to 6:00 pm', 
     'have dinner at 6:00 pm', 'watch TV from 7:00 pm to 8:00 pm']
  """
  if debug: print ("GNS FUNCTION: <generate_first_daily_plan>")
  return run_gpt_prompt_daily_plan(persona, wake_up_hour)[0]


def generate_hourly_schedule(persona, wake_up_hour): 
  """
  根据每日需求，创建每小时的日程安排——一次一小时。
  每小时的动作形式如下所示:
  "sleeping in her bed" (在她的床上睡觉)
  
  输出基本上是为了完成短语 "x is..." (x 正在...)

  角色状态: 身份稳定集, daily_plan (每日计划)

  输入:
    persona: Persona 类实例
    wake_up_hour: 角色的整数形式的起床小时。
  输出:
    一个包含活动及其持续时间（分钟）的列表:
  输出示例:
    [['sleeping', 360], ['waking up and starting her morning routine', 60], 
     ['eating breakfast', 60],..]
  """
  if debug: print ("GNS FUNCTION: <generate_hourly_schedule>")

  hour_str = ["00:00 AM", "01:00 AM", "02:00 AM", "03:00 AM", "04:00 AM", 
              "05:00 AM", "06:00 AM", "07:00 AM", "08:00 AM", "09:00 AM", 
              "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", 
              "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM",
              "08:00 PM", "09:00 PM", "10:00 PM", "11:00 PM"]
  n_m1_activity = []
  diversity_repeat_count = 3
  for i in range(diversity_repeat_count): 
    n_m1_activity_set = set(n_m1_activity)
    if len(n_m1_activity_set) < 5: 
      n_m1_activity = []
      for count, curr_hour_str in enumerate(hour_str): 
        if wake_up_hour > 0: 
          n_m1_activity += ["sleeping"]
          wake_up_hour -= 1
        else: 
          n_m1_activity += [run_gpt_prompt_generate_hourly_schedule(
                          persona, curr_hour_str, n_m1_activity, hour_str)[0]]
  
  # 步骤 1. 将每小时的日程压缩成以下格式:
  # 整数表示小时数。它们加起来应该等于 24。
  # [['sleeping', 6], ['waking up and starting her morning routine', 1], 
  # ['eating breakfast', 1], ['getting ready for the day', 1], 
  # ['working on her painting', 2], ['taking a break', 1], 
  # ['having lunch', 1], ['working on her painting', 3], 
  # ['taking a break', 2], ['working on her painting', 2], 
  # ['relaxing and watching TV', 1], ['going to bed', 1], ['sleeping', 2]]
  _n_m1_hourly_compressed = []
  prev = None 
  prev_count = 0
  for i in n_m1_activity: 
    if i != prev:
      prev_count = 1 
      _n_m1_hourly_compressed += [[i, prev_count]]
      prev = i
    else: 
      if _n_m1_hourly_compressed: 
        _n_m1_hourly_compressed[-1][1] += 1

  # 步骤 2. 扩展到分钟级别 (从小时级别)
  # [['sleeping', 360], ['waking up and starting her morning routine', 60], 
  # ['eating breakfast', 60],..]
  n_m1_hourly_compressed = []
  for task, duration in _n_m1_hourly_compressed: 
    n_m1_hourly_compressed += [[task, duration*60]]

  return n_m1_hourly_compressed


def generate_task_decomp(persona, task, duration): 
  """
  根据任务描述对任务进行少样本分解。

  角色状态: 身份稳定集, curr_date_str (当前日期字符串), 名字

  输入:
    persona: Persona 类实例
    task: 字符串形式的当前任务描述
          (例如："waking up and starting her morning routine" - 醒来并开始她的晨间事务)
    duration: 一个整数，表示此任务预计持续的分钟数 (例如：60)
  输出:
    一个列表的列表，其中内部列表包含分解后的任务描述和任务预计持续的分钟数。
  输出示例:
    [['going to the bathroom', 5], ['getting dressed', 5], 
     ['eating breakfast', 15], ['checking her email', 5], 
     ['getting her supplies ready for the day', 15], 
     ['starting to work on her painting', 15]] 
  """
  if debug: print ("GNS FUNCTION: <generate_task_decomp>")
  return run_gpt_prompt_task_decomp(persona, task, duration)[0]


def generate_action_sector(act_desp, persona, maze): 
  """待办
  根据角色和任务描述，选择 action_sector (行动区域)。

  角色状态: 身份稳定集, 前一天的日程, 每日计划

  输入:
    act_desp: 新动作的描述 (例如："sleeping" - 睡觉)
    persona: Persona 类实例
  输出:
    action_sector (例如："bedroom 2" - 卧室2) (注意：示例输出中给出的是 arena，但函数名是 sector)
  输出示例:
    "bedroom 2" 
  """
  if debug: print ("GNS FUNCTION: <generate_action_sector>")
  return run_gpt_prompt_action_sector(act_desp, persona, maze)[0]


def generate_action_arena(act_desp, persona, maze, act_world, act_sector): 
  """待办
  根据角色和任务描述，选择 action_arena (行动竞技场)。

  角色状态: 身份稳定集, 前一天的日程, 每日计划

  输入:
    act_desp: 新动作的描述 (例如："sleeping" - 睡觉)
    persona: Persona 类实例
  输出:
    action_arena (例如："bedroom 2" - 卧室2)
  输出示例:
    "bedroom 2"
  """
  if debug: print ("GNS FUNCTION: <generate_action_arena>")
  return run_gpt_prompt_action_arena(act_desp, persona, maze, act_world, act_sector)[0]


def generate_action_game_object(act_desp, act_address, persona, maze):
  """待办
  根据动作描述和动作地址（我们期望动作发生的地址），选择一个游戏对象。

  角色状态: 身份稳定集, 前一天的日程, 每日计划

  输入:
    act_desp: 动作的描述 (例如："sleeping" - 睡觉)
    act_address: 动作将发生的竞技场：
               (例如："dolores double studio:double studio:bedroom 2")
    persona: Persona 类实例
  输出:
    act_game_object (行动游戏对象)
  输出示例:
    "bed"
  """
  if debug: print ("GNS FUNCTION: <generate_action_game_object>")
  if not persona.s_mem.get_str_accessible_arena_game_objects(act_address): 
    return "<random>"
  return run_gpt_prompt_action_game_object(act_desp, persona, maze, act_address)[0]


def generate_action_pronunciatio(act_desp, persona): 
  """待办
  给定一个动作描述，通过少样本提示创建一个表情符号字符串描述。

  基本不需要来自角色的任何信息。

  输入:
    act_desp: 动作的描述 (例如："sleeping" - 睡觉)
    persona: Persona 类实例
  输出:
    一个用于翻译动作描述的表情符号字符串。
  输出示例:
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_pronunciatio>")
  try: 
    x = run_gpt_prompt_pronunciatio(act_desp, persona)[0]
  except: 
    x = "🙂"

  if not x: 
    return "🙂"
  return x


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


def generate_act_obj_desc(act_game_object, act_desp, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_desc>")
  return run_gpt_prompt_act_obj_desc(act_game_object, act_desp, persona)[0]


def generate_act_obj_event_triple(act_game_object, act_obj_desc, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_event_triple>")
  return run_gpt_prompt_act_obj_event_triple(act_game_object, act_obj_desc, persona)[0]


def generate_convo(maze, init_persona, target_persona): 
  curr_loc = maze.access_tile(init_persona.scratch.curr_tile)

  # convo = run_gpt_prompt_create_conversation(init_persona, target_persona, curr_loc)[0]
  # convo = agent_chat_v1(maze, init_persona, target_persona)
  convo = agent_chat_v2(maze, init_persona, target_persona)
  all_utt = ""

  for row in convo: 
    speaker = row[0]
    utt = row[1]
    all_utt += f"{speaker}: {utt}\n"

  convo_length = math.ceil(int(len(all_utt)/8) / 30)

  if debug: print ("GNS FUNCTION: <generate_convo>")
  return convo, convo_length


def generate_convo_summary(persona, convo): 
  convo_summary = run_gpt_prompt_summarize_conversation(persona, convo)[0]
  return convo_summary


def generate_decide_to_talk(init_persona, target_persona, retrieved): 
  x =run_gpt_prompt_decide_to_talk(init_persona, target_persona, retrieved)[0]
  if debug: print ("GNS FUNCTION: <generate_decide_to_talk>")

  if x == "yes": 
    return True
  else: 
    return False


def generate_decide_to_react(init_persona, target_persona, retrieved): 
  if debug: print ("GNS FUNCTION: <generate_decide_to_react>")
  return run_gpt_prompt_decide_to_react(init_persona, target_persona, retrieved)[0]


def generate_new_decomp_schedule(persona, inserted_act, inserted_act_dur,  start_hour, end_hour): 
  # 步骤 1: 设置函数的核心变量。
  # <p> 是我们当前正在编辑其日程的角色。
  p = persona
  # <today_min_pass> 表示今天已经过去的分钟数。
  today_min_pass = (int(p.scratch.curr_time.hour) * 60 
                    + int(p.scratch.curr_time.minute) + 1)
  
  # 步骤 2: 我们需要创建 <main_act_dur> 和 <truncated_act_dur>。
  # 这些基本上是角色 <f_daily_schedule> 的子组件，
  # 但侧重于当前的分解。
  # 这是 <main_act_dur> 的一个例子:
  # ['醒来并完成她的晨间事务 (早上6点醒来)', 5]
  # ['醒来并完成她的晨间事务 (早上6点醒来)', 5]
  # ['醒来并完成她的晨间事务 (上厕所)', 5]
  # ['醒来并完成她的晨间事务 (洗漱...)', 10]
  # ['醒来并完成她的晨间事务 (整理床铺)', 5]
  # ['醒来并完成她的晨间事务 (吃早餐)', 15]
  # ['醒来并完成她的晨间事务 (穿衣服)', 10]
  # ['醒来并完成她的晨间事务 (离开她的...)', 5]
  # ['醒来并完成她的晨间事务 (开始她的...)', 5]
  # ['为她的一天做准备 (早上6点醒来)', 5]
  # ['为她的一天做准备 (整理床铺)', 5]
  # ['为她的一天做准备 (洗澡)', 15]
  # ['为她的一天做准备 (穿衣服)', 5]
  # ['为她的一天做准备 (吃早餐)', 10]
  # ['为她的一天做准备 (刷牙)', 5]
  # ['为她的一天做准备 (煮咖啡)', 5]
  # ['为她的一天做准备 (查邮件)', 5]
  # ['为她的一天做准备 (开始画画)', 5]
  # 
  # 而 <truncated_act_dur> 只关系到事件发生之前的部分。
  # ['醒来并完成她的晨间事务 (早上6点醒来)', 5]
  # ['醒来并完成她的晨间事务 (早上6点醒来)', 2]
  main_act_dur = []
  truncated_act_dur = []
  dur_sum = 0 # duration sum / 持续时间总和
  count = 0 # enumerate count / 枚举计数
  truncated_fin = False 

  print ("DEBUG::: ", persona.scratch.name)
  for act, dur in p.scratch.f_daily_schedule: 
    if (dur_sum >= start_hour * 60) and (dur_sum < end_hour * 60): 
      main_act_dur += [[act, dur]]
      if dur_sum <= today_min_pass:
        truncated_act_dur += [[act, dur]]
      elif dur_sum > today_min_pass and not truncated_fin: 
        # 我们需要像这样插入最后一个动作和持续时间列表：
        # 例如： ['醒来并完成她的晨间事务 (醒来...)', 2]
        truncated_act_dur += [[p.scratch.f_daily_schedule[count][0], 
                               dur_sum - today_min_pass]] 
        truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## 12月7日调试;.. +1是否正确???
        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass + 1) ######## 12月7日调试;.. +1是否正确???
        print ("DEBUG::: ", truncated_act_dur)

        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## 12月7日调试;.. +1是否正确???
        truncated_fin = True
    dur_sum += dur
    count += 1

  persona_name = persona.name 
  main_act_dur = main_act_dur

  x = truncated_act_dur[-1][0].split("(")[0].strip() + " (在去 " + truncated_act_dur[-1][0].split("(")[-1][:-1] + " 的路上)"
  truncated_act_dur[-1][0] = x 

  if "(" in truncated_act_dur[-1][0]: 
    inserted_act = truncated_act_dur[-1][0].split("(")[0].strip() + " (" + inserted_act + ")"

  # 下面 inserted_act_dur+1 的处理是一个重要的决定，但我不确定
  # 我是否完全理解其含义。可能需要
  # 重新审视。
  truncated_act_dur += [[inserted_act, inserted_act_dur]]
  start_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=start_hour))
  end_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=end_hour))

  if debug: print ("GNS FUNCTION: <generate_new_decomp_schedule>")
  return run_gpt_prompt_new_decomp_schedule(persona, 
                                            main_act_dur, 
                                            truncated_act_dur, 
                                            start_time_hour,
                                            end_time_hour,
                                            inserted_act,
                                            inserted_act_dur)[0]


##############################################################################
# 第三章: 计划
##############################################################################

def revise_identity(persona): 
  p_name = persona.scratch.name

  focal_points = [f"{p_name} 在 {persona.scratch.get_str_curr_date_str()} 的计划。",
                  f"{p_name} 生活中最近的重要事件。"]
  retrieved = new_retrieve(persona, focal_points)

  statements = "[陈述]\n" # Kept brackets as they might be structural for prompt
  for key, val in retrieved.items():
    for i in val: 
      statements += f"{i.created.strftime('%A %B %d -- %H:%M %p')}: {i.embedding_key}\n"

  # print (";adjhfno;asdjao;idfjo;af", p_name)
  plan_prompt = statements + "\n"
  plan_prompt += f"根据以上陈述，{p_name} 在计划"
  plan_prompt += f" *{persona.scratch.curr_time.strftime('%A %B %d')}* 时，有什么需要记住的吗？"
  plan_prompt += f"如果有任何日程安排信息，请尽可能具体（如果陈述中提及，请包括日期、时间和地点）\n\n"
  plan_prompt += f"从 {p_name} 的视角撰写回应。"
  plan_note = ChatGPT_single_request(plan_prompt)
  # print (plan_note)

  thought_prompt = statements + "\n"
  thought_prompt += f"根据以上陈述，我们应如何总结 {p_name} 迄今为止对日子的感受？\n\n"
  thought_prompt += f"从 {p_name} 的视角撰写回应。"
  thought_note = ChatGPT_single_request(thought_prompt)
  # print (thought_note)

  currently_prompt = f"{p_name} 从 {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')} 的状态:\n"
  currently_prompt += f"{persona.scratch.currently}\n\n"
  currently_prompt += f"{p_name} 在 {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')} 结束时的想法:\n" 
  currently_prompt += (plan_note + thought_note).replace('\n', '') + "\n\n"
  currently_prompt += f"现在是 {persona.scratch.curr_time.strftime('%A %B %d')}。根据上述信息，撰写 {p_name} 在 {persona.scratch.curr_time.strftime('%A %B %d')} 的状态，以反映 {p_name} 在 {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')} 结束时的想法。请以第三人称撰写关于 {p_name} 的内容。"
  currently_prompt += f"如果有任何日程安排信息，请尽可能具体（如果陈述中提及，请包括日期、时间和地点）\n\n"
  currently_prompt += "请遵循以下格式:\nStatus: <新状态>" # "Status:" is a key
  # print ("DEBUG ;adjhfno;asdjao;asdfsidfjo;af", p_name)
  # print (currently_prompt)
  new_currently = ChatGPT_single_request(currently_prompt)
  # print (new_currently)
  # print (new_currently[10:])

  persona.scratch.currently = new_currently

  daily_req_prompt = persona.scratch.get_str_iss() + "\n"
  daily_req_prompt += f"今天是 {persona.scratch.curr_time.strftime('%A %B %d')}。这是 {persona.scratch.name} 今天的大致计划 (包含具体时间，例如：中午12点吃午饭，晚上7点到8点看电视)。\n\n"
  daily_req_prompt += f"请遵循以下格式 (列表应包含4~6项，但不能更多):\n" # "Follow this format" translated
  daily_req_prompt += f"1. 在 <时间> 起床并完成晨间事务, 2. ..." # Example translated

  new_daily_req = ChatGPT_single_request(daily_req_prompt)
  new_daily_req = new_daily_req.replace('\n', ' ')
  print ("WE ARE HERE!!!", new_daily_req)
  persona.scratch.daily_plan_req = new_daily_req


def _long_term_planning(persona, new_day): 
  """
  如果是一天的开始，则制定角色的每日长期计划。
  这主要包含两个部分：首先，我们创建起床时间，
  其次，我们据此创建每小时的日程安排。
  输入
    new_day: 指示当前时间是否表示“第一天”、
             “新的一天”或 False (两者都不是)。这很重要，因为我们
             在新的一天为角色创建长期规划。
  """
  # 我们首先为角色创建起床时间。
  wake_up_hour = generate_wake_up_hour(persona)

  # 当新的一天开始时，我们首先创建角色的 daily_req (每日需求)。
  # 注意，daily_req 是一个字符串列表，大致描述了角色的一天。
  if new_day == "First day": 
    # 为生成开始时引导每日计划：
    # 如果这是生成的开始（因此没有前一天的每日需求），
    # 或者如果是在新的一天，我们希望创建一套新的每日需求。
    persona.scratch.daily_req = generate_first_daily_plan(persona, 
                                                          wake_up_hour)
  elif new_day == "New day":
    revise_identity(persona)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 待办
    # 我们需要在这里创建一个新的 daily_req...
    persona.scratch.daily_req = persona.scratch.daily_req

  # 根据 daily_req，我们为角色创建一个每小时的日程安排，
  # 这是一个待办事项列表，包含时间持续长度（分钟），
  # 总计24小时。
  persona.scratch.f_daily_schedule = generate_hourly_schedule(persona, 
                                                              wake_up_hour)
  persona.scratch.f_daily_schedule_hourly_org = (persona.scratch
                                                   .f_daily_schedule[:])


  # 3月4日添加 -- 将计划添加到记忆中。
  thought = f"这是 {persona.scratch.name} 在 {persona.scratch.curr_time.strftime('%A %B %d')} 的计划:"
  for i in persona.scratch.daily_req: 
    thought += f" {i},"
  thought = thought[:-1] + "."
  created = persona.scratch.curr_time
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  s, p, o = (persona.scratch.name, "plan", persona.scratch.curr_time.strftime('%A %B %d'))
  keywords = set(["plan"])
  thought_poignancy = 5
  thought_embedding_pair = (thought, get_embedding(thought))
  persona.a_mem.add_thought(created, expiration, s, p, o, 
                            thought, keywords, thought_poignancy, 
                            thought_embedding_pair, None)

  # print("Sleeping for 20 seconds...")
  # time.sleep(10)
  # print("Done sleeping!")



def _determine_action(persona, maze): 
  """
  为角色创建下一个动作序列。
  此函数的主要目标是在角色的暂存空间上运行 "add_new_action"，
  从而为下一个动作设置所有与动作相关的变量。
  作为其中的一部分，角色可能需要根据需要分解其每小时的日程安排。
  输入
    persona: 我们正在确定其动作的当前 <Persona> 实例。
    maze: 当前的 <Maze> 实例。
  """
  def determine_decomp(act_desp, act_dura):
    """
    给定一个动作描述及其持续时间，我们确定是否需要分解它。
    如果动作是关于代理睡觉的，我们通常不希望分解它，
    所以我们在这里捕获这种情况。

    输入:
      act_desp: 动作的描述 (例如："sleeping" - 睡觉)
      act_dura: 动作的持续时间（分钟）。
    输出:
      一个布尔值。如果需要分解则为 True，否则为 False。
    """
    if "sleep" not in act_desp and "bed" not in act_desp: 
      return True
    elif "sleeping" in act_desp or "asleep" in act_desp or "in bed" in act_desp:
      return False
    elif "sleep" in act_desp or "bed" in act_desp: 
      if act_dura > 60: 
        return False
    return True

  # 此函数的目标是获取与
  # <curr_index> 相关联的动作。作为其中的一部分，我们可能需要分解一些大块的
  # 动作。
  # 重要提示：我们尝试在任何给定时间点至少分解两个小时的日程。
  curr_index = persona.scratch.get_f_daily_schedule_index()
  curr_index_60 = persona.scratch.get_f_daily_schedule_index(advance=60)

  # * 分解 * 
  # 在一天的第一个小时，我们需要分解两个小时的
  # 序列。我们在这里执行此操作。
  if curr_index == 0:
    # 如果这是一天的第一个小时，则调用此部分。
    act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index]
    if act_dura >= 60: 
      # 如果下一个动作超过一小时，并且符合
      # determine_decomp 中描述的标准，我们就进行分解。
      if determine_decomp(act_desp, act_dura): 
        persona.scratch.f_daily_schedule[curr_index:curr_index+1] = (
                            generate_task_decomp(persona, act_desp, act_dura))
    if curr_index_60 + 1 < len(persona.scratch.f_daily_schedule):
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60+1]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60+1:curr_index_60+2] = (
                            generate_task_decomp(persona, act_desp, act_dura))

  if curr_index_60 < len(persona.scratch.f_daily_schedule):
    # 如果不是一天的第一个小时，则始终调用此部分（它也
    # 在一天的第一个小时被调用——以便我们可以一次性
    # 分解两个小时）。当然，我们也需要有东西可以分解，
    # 所以我们也会检查这一点。
    if persona.scratch.curr_time.hour < 23:
      # 而且我们不想在晚上11点之后进行分解。
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60:curr_index_60+1] = (
                              generate_task_decomp(persona, act_desp, act_dura))
  # * 分解结束 * 

  # 根据动作描述和持续时间生成一个 <Action> 实例。此时，
  # 我们假设所有相关动作都已分解并准备就绪
  # 在 f_daily_schedule 中。
  print ("DEBUG LJSDLFSKJF")
  for i in persona.scratch.f_daily_schedule: print (i)
  print (curr_index)
  print (len(persona.scratch.f_daily_schedule))
  print (persona.scratch.name)
  print ("------")

  # 1440
  x_emergency = 0
  for i in persona.scratch.f_daily_schedule: 
    x_emergency += i[1]
  # print ("x_emergency", x_emergency)

  if 1440 - x_emergency > 0: 
    print ("x_emergency__AAA", x_emergency)
  persona.scratch.f_daily_schedule += [["sleeping", 1440 - x_emergency]]
  



  act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index] 



  # 查找动作的目标位置并创建与动作相关的
  # 变量。
  act_world = maze.access_tile(persona.scratch.curr_tile)["world"]
  # act_sector = maze.access_tile(persona.scratch.curr_tile)["sector"]
  act_sector = generate_action_sector(act_desp, persona, maze)
  act_arena = generate_action_arena(act_desp, persona, maze, act_world, act_sector)
  act_address = f"{act_world}:{act_sector}:{act_arena}"
  act_game_object = generate_action_game_object(act_desp, act_address,
                                                persona, maze)
  new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
  act_pron = generate_action_pronunciatio(act_desp, persona)
  act_event = generate_action_event_triple(act_desp, persona)
  # 角色的动作也会影响对象状态。我们在这里进行设置。
  act_obj_desp = generate_act_obj_desc(act_game_object, act_desp, persona)
  act_obj_pron = generate_action_pronunciatio(act_obj_desp, persona)
  act_obj_event = generate_act_obj_event_triple(act_game_object, 
                                                act_obj_desp, persona)

  # 将动作添加到角色的队列中。
  persona.scratch.add_new_action(new_address, 
                                 int(act_dura), 
                                 act_desp, 
                                 act_pron, 
                                 act_event,
                                 None,
                                 None,
                                 None,
                                 None,
                                 act_obj_desp, 
                                 act_obj_pron, 
                                 act_obj_event)


def _choose_retrieved(persona, retrieved): 
  """
  检索到的元素有多个核心 "curr_events" (当前事件)。我们需要选择一个
  我们将要对其做出反应的事件。我们在这里选择那个事件。
  输入
    persona: 我们正在确定其动作的当前 <Persona> 实例。
    retrieved: 从角色的联想记忆中检索到的 <ConceptNode> (概念节点) 字典。
               此字典的格式如下：
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
  """
  # 一旦我们完成反思，我们可能希望在这里构建一个更
  # 复杂的结构。
  
  # 我们暂时不处理自身事件...
  copy_retrieved = retrieved.copy()
  for event_desc, rel_ctx in copy_retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if curr_event.subject == persona.name: 
      del retrieved[event_desc]

  # 始终首先选择角色。
  priority = []
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if (":" not in curr_event.subject 
        and curr_event.subject != persona.name): 
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)

  # 跳过空闲状态。
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if "is idle" not in event_desc:  # "is idle" is a specific string, kept in English for logic
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)
  return None


def _should_react(persona, retrieved, personas): 
  """
  根据检索到的值，确定角色应表现出何种形式的反应。
  输入
    persona: 我们正在确定其动作的当前 <Persona> 实例。
    retrieved: 从角色的联想记忆中检索到的 <ConceptNode> (概念节点) 字典。
               此字典的格式如下：
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
    personas: 一个字典，其中包含所有角色名称作为键，<Persona> 实例作为值。
  """
  def lets_talk(init_persona, target_persona, retrieved):
    if (not target_persona.scratch.act_address 
        or not target_persona.scratch.act_description
        or not init_persona.scratch.act_address
        or not init_persona.scratch.act_description): 
      return False

    if ("sleeping" in target_persona.scratch.act_description  # "sleeping" is a keyword
        or "sleeping" in init_persona.scratch.act_description): 
      return False

    if init_persona.scratch.curr_time.hour == 23: 
      return False

    if "<waiting>" in target_persona.scratch.act_address: # "<waiting>" is a tag
      return False

    if (target_persona.scratch.chatting_with 
      or init_persona.scratch.chatting_with): 
      return False

    if (target_persona.name in init_persona.scratch.chatting_with_buffer): 
      if init_persona.scratch.chatting_with_buffer[target_persona.name] > 0: 
        return False

    if generate_decide_to_talk(init_persona, target_persona, retrieved): 

      return True

    return False

  def lets_react(init_persona, target_persona, retrieved): 
    if (not target_persona.scratch.act_address 
        or not target_persona.scratch.act_description
        or not init_persona.scratch.act_address
        or not init_persona.scratch.act_description): 
      return False

    if ("sleeping" in target_persona.scratch.act_description # "sleeping" is a keyword
        or "sleeping" in init_persona.scratch.act_description): 
      return False

    # return False
    if init_persona.scratch.curr_time.hour == 23: 
      return False

    if "waiting" in target_persona.scratch.act_description: # "waiting" is a keyword
      return False
    if init_persona.scratch.planned_path == []:
      return False

    if (init_persona.scratch.act_address 
        != target_persona.scratch.act_address): 
      return False

    react_mode = generate_decide_to_react(init_persona, 
                                          target_persona, retrieved)

    if react_mode == "1": 
      wait_until = ((target_persona.scratch.act_start_time 
        + datetime.timedelta(minutes=target_persona.scratch.act_duration - 1))
        .strftime("%B %d, %Y, %H:%M:%S"))
      return f"wait: {wait_until}" # "wait:" is a command prefix
    elif react_mode == "2":
      return False
      return "do other things" # "do other things" is a specific mode string
    else:
      return False #"keep" # "keep" is a specific mode string

  # 如果角色当前正在聊天，则默认为无反应
  if persona.scratch.chatting_with: 
    return False
  if "<waiting>" in persona.scratch.act_address: # "<waiting>" is a tag
    return False

  # 回想一下，retrieved 的格式如下：
  # 字典 {["curr_event"] = <ConceptNode>, 
  #             ["events"] = [<ConceptNode>, ...], 
  #             ["thoughts"] = [<ConceptNode>, ...]}
  curr_event = retrieved["curr_event"]

  if ":" not in curr_event.subject: 
    # 这是一个角色事件。
    if lets_talk(persona, personas[curr_event.subject], retrieved):
      return f"chat with {curr_event.subject}" # "chat with" is a command prefix
    react_mode = lets_react(persona, personas[curr_event.subject], 
                            retrieved)
    return react_mode
  return False


def _create_react(persona, inserted_act, inserted_act_dur,
                  act_address, act_event, chatting_with, chat, chatting_with_buffer,
                  chatting_end_time, 
                  act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
                  act_obj_event, act_start_time=None): 
  p = persona 

  min_sum = 0
  for i in range (p.scratch.get_f_daily_schedule_hourly_org_index()): 
    min_sum += p.scratch.f_daily_schedule_hourly_org[i][1]
  start_hour = int (min_sum/60)

  if (p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] >= 120):
    end_hour = start_hour + p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1]/60

  elif (p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] + 
      p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()+1][1]): 
    end_hour = start_hour + ((p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] + 
              p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()+1][1])/60)

  else: 
    end_hour = start_hour + 2
  end_hour = int(end_hour)

  dur_sum = 0
  count = 0 
  start_index = None
  end_index = None
  for act, dur in p.scratch.f_daily_schedule: 
    if dur_sum >= start_hour * 60 and start_index == None:
      start_index = count
    if dur_sum >= end_hour * 60 and end_index == None: 
      end_index = count
    dur_sum += dur
    count += 1

  ret = generate_new_decomp_schedule(p, inserted_act, inserted_act_dur, 
                                       start_hour, end_hour)
  p.scratch.f_daily_schedule[start_index:end_index] = ret
  p.scratch.add_new_action(act_address,
                           inserted_act_dur,
                           inserted_act,
                           act_pronunciatio,
                           act_event,
                           chatting_with,
                           chat,
                           chatting_with_buffer,
                           chatting_end_time,
                           act_obj_description,
                           act_obj_pronunciatio,
                           act_obj_event,
                           act_start_time)


def _chat_react(maze, persona, focused_event, reaction_mode, personas):
  # 有两个角色——发起对话的角色
  # 和作为目标的角色。我们在这里获取角色实例。
  init_persona = persona
  target_persona = personas[reaction_mode[9:].strip()]
  curr_personas = [init_persona, target_persona]

  # 在这里实际创建对话。
  convo, duration_min = generate_convo(maze, init_persona, target_persona)
  convo_summary = generate_convo_summary(init_persona, convo)
  inserted_act = convo_summary
  inserted_act_dur = duration_min

  act_start_time = target_persona.scratch.act_start_time

  curr_time = target_persona.scratch.curr_time
  if curr_time.second != 0: 
    temp_curr_time = curr_time + datetime.timedelta(seconds=60 - curr_time.second)
    chatting_end_time = temp_curr_time + datetime.timedelta(minutes=inserted_act_dur)
  else: 
    chatting_end_time = curr_time + datetime.timedelta(minutes=inserted_act_dur)

  for role, p in [("init", init_persona), ("target", target_persona)]: 
    if role == "init": 
      act_address = f"<persona> {target_persona.name}"
      act_event = (p.name, "chat with", target_persona.name) # "chat with" is a predicate
      chatting_with = target_persona.name
      chatting_with_buffer = {}
      chatting_with_buffer[target_persona.name] = 800
    elif role == "target": 
      act_address = f"<persona> {init_persona.name}"
      act_event = (p.name, "chat with", init_persona.name) # "chat with" is a predicate
      chatting_with = init_persona.name
      chatting_with_buffer = {}
      chatting_with_buffer[init_persona.name] = 800

    act_pronunciatio = "💬" 
    act_obj_description = None
    act_obj_pronunciatio = None
    act_obj_event = (None, None, None)

    _create_react(p, inserted_act, inserted_act_dur,
      act_address, act_event, chatting_with, convo, chatting_with_buffer, chatting_end_time,
      act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
      act_obj_event, act_start_time)


def _wait_react(persona, reaction_mode): 
  p = persona

  inserted_act = f'等待开始 {p.scratch.act_description.split("(")[-1][:-1]}'
  end_time = datetime.datetime.strptime(reaction_mode[6:].strip(), "%B %d, %Y, %H:%M:%S")
  inserted_act_dur = (end_time.minute + end_time.hour * 60) - (p.scratch.curr_time.minute + p.scratch.curr_time.hour * 60) + 1

  act_address = f"<waiting> {p.scratch.curr_tile[0]} {p.scratch.curr_tile[1]}"
  act_event = (p.name, "waiting to start", p.scratch.act_description.split("(")[-1][:-1]) # "waiting to start" is a predicate
  chatting_with = None
  chat = None
  chatting_with_buffer = None
  chatting_end_time = None

  act_pronunciatio = "⌛" 
  act_obj_description = None
  act_obj_pronunciatio = None
  act_obj_event = (None, None, None)

  _create_react(p, inserted_act, inserted_act_dur,
    act_address, act_event, chatting_with, chat, chatting_with_buffer, chatting_end_time,
    act_pronunciatio, act_obj_description, act_obj_pronunciatio, act_obj_event)


def plan(persona, maze, personas, new_day, retrieved): 
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
               而第二层指定相关的 "curr_event" (当前事件), "events" (事件), 
               和 "thoughts" (想法)。
  输出
    角色的目标动作地址 (persona.scratch.act_address)。
  """ 
  # 第一部分: 生成每小时的日程安排。
  if new_day: 
    _long_term_planning(persona, new_day)

  # 第二部分: 如果当前动作已过期，我们希望创建一个新计划。
  if persona.scratch.act_check_finished(): 
    _determine_action(persona, maze)

  # 第三部分: 如果你感知到一个需要回应的事件（看到
  # 另一个角色），并检索到相关信息。
  # 步骤 1: retrieved 中可能包含多个事件。这里的第一个
  #         任务是确定我们希望角色关注哪个事件。
  #         <focused_event> 的格式如下所示的字典：
  #         字典 {["curr_event"] = <ConceptNode>, 
  #                     ["events"] = [<ConceptNode>, ...], 
  #                     ["thoughts"] = [<ConceptNode>, ...]}
  focused_event = False
  if retrieved.keys(): 
    focused_event = _choose_retrieved(persona, retrieved)
  
  # 步骤 2: 一旦我们选择了一个事件，我们需要确定角色是否
  #         将对感知到的事件采取任何行动。由 _should_react 返回
  #         的反应模式有三种可能。
  #         a) "chat with {target_persona.name}" (与 {target_persona.name} 聊天)
  #         b) "react" (反应)
  #         c) False (否)
  if focused_event: 
    reaction_mode = _should_react(persona, focused_event, personas)
    if reaction_mode: 
      # 如果我们确实想聊天，那么我们就生成对话
      if reaction_mode[:9] == "chat with": # "chat with" is a command prefix
        _chat_react(maze, persona, focused_event, reaction_mode, personas)
      elif reaction_mode[:4] == "wait": # "wait" is a command prefix
        _wait_react(persona, reaction_mode)
      # elif reaction_mode == "do other things": 
      #   _chat_react(persona, focused_event, reaction_mode, personas)

  # 步骤 3: 清理与聊天相关的状态。
  # 如果角色没有与任何人聊天，我们在此清理任何与聊天相关的状态。
  if persona.scratch.act_event[1] != "chat with": # "chat with" is a predicate
    persona.scratch.chatting_with = None
    persona.scratch.chat = None
    persona.scratch.chatting_end_time = None
  # 我们要确保角色不会在无限循环中
  # 相互交谈。因此，chatting_with_buffer 维持一种形式的
  # 缓冲区，使角色在与同一目标聊天一次后等待一段时间，
  # 然后才能再次与之聊天。我们在这里跟踪缓冲区的值。
  curr_persona_chat_buffer = persona.scratch.chatting_with_buffer
  for persona_name, buffer_count in curr_persona_chat_buffer.items():
    if persona_name != persona.scratch.chatting_with: 
      persona.scratch.chatting_with_buffer[persona_name] -= 1

  return persona.scratch.act_address













































 
