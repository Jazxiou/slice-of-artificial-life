"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: scratch.py
描述: 定义了生成式代理的短期记忆模块。
"""
import datetime
import json
import sys
sys.path.append('../../')

from global_methods import *

class Scratch: 
  def __init__(self, f_saved): 
    # PERSONA HYPERPARAMETERS (角色超参数)
    # <vision_r> 表示角色可以看到的周围瓦片数量。
    self.vision_r = 4
    # <att_bandwidth> 待办
    self.att_bandwidth = 3
    # <retention> 待办
    self.retention = 5

    # WORLD INFORMATION (世界信息)
    # 感知到的世界时间。
    self.curr_time = None
    # 角色的当前 x,y 瓦片坐标。
    self.curr_tile = None
    # 感知到的世界每日需求。
    self.daily_plan_req = None
    
    # THE CORE IDENTITY OF THE PERSONA (角色的核心身份)
    # 角色的基本信息。
    self.name = None
    self.first_name = None
    self.last_name = None
    self.age = None
    # L0 永久核心特质。
    self.innate = None
    # L1 稳定特质。
    self.learned = None
    # L2 外部实现。
    self.currently = None
    self.lifestyle = None
    self.living_area = None

    # REFLECTION VARIABLES (反思变量)
    self.concept_forget = 100
    self.daily_reflection_time = 60 * 3
    self.daily_reflection_size = 5
    self.overlap_reflect_th = 2
    self.kw_strg_event_reflect_th = 4
    self.kw_strg_thought_reflect_th = 4

    # New reflection variables (新的反思变量)
    self.recency_w = 1
    self.relevance_w = 1
    self.importance_w = 1
    self.recency_decay = 0.99
    self.importance_trigger_max = 150
    self.importance_trigger_curr = self.importance_trigger_max
    self.importance_ele_n = 0 
    self.thought_count = 5

    # PERSONA PLANNING (角色规划)
    # <daily_req> 是角色今天旨在实现的各种目标的列表。
    # e.g., ['Work on her paintings for her upcoming show', 
    #        'Take a break to watch some TV', 
    #        'Make lunch for herself', 
    #        'Work on her paintings some more', 
    #        'Go to bed early']
    # 它们必须在一天结束时更新，因此我们跟踪它们最初生成的时间。
    self.daily_req = []
    # <f_daily_schedule> 表示一种长期规划。它列出了角色的每日计划。
    # 注意，我们采用长期规划和短期分解的方法，也就是说，我们首先制定每小时的日程安排，
    # 然后逐步分解。
    # 以下示例中有三点需要注意：
    # 1) 注意 "sleeping" (睡觉) 是如何没有被分解的——一些常见事件，主要是睡觉，被硬编码为不可分解。
    # 2) 一些元素开始被分解……随着时间的推移，更多的内容将被分解（当它们被分解时，它们会保留原始的每小时动作描述不变）。
    # 3) 后面的元素没有被分解。当事件发生时，未分解的元素将被舍弃。
    # e.g., [['sleeping', 360], 
    #         ['wakes up and ... (wakes up and stretches ...)', 5], 
    #         ['wakes up and starts her morning routine (out of bed )', 10],
    #         ...
    #         ['having lunch', 60], 
    #         ['working on her painting', 180], ...]
    self.f_daily_schedule = []
    # <f_daily_schedule_hourly_org> 最初是 f_daily_schedule 的副本，
    # 但保留了每小时日程的原始未分解版本。
    # e.g., [['sleeping', 360], 
    #        ['wakes up and starts her morning routine', 120],
    #        ['working on her painting', 240], ... ['going to bed', 60]]
    self.f_daily_schedule_hourly_org = []
    
    # CURR ACTION (当前动作)
    # <address> 是动作发生地点的字符串地址。它的格式是
    # "{世界}:{区域}:{竞技场}:{游戏对象}"。重要的是，访问此地址时不要使用负索引（例如 [-1]），
    # 因为在某些情况下，末尾的地址元素可能不存在。
    # e.g., "dolores double studio:double studio:bedroom 1:bed"
    self.act_address = None
    # <start_time> 是一个 python datetime 实例，指示动作开始的时间。
    self.act_start_time = None
    # <duration> 是一个整数值，指示一个动作预计持续的分钟数。
    self.act_duration = None
    # <description> 是动作的字符串描述。
    self.act_description = None
    # <pronunciatio> 是 self.description 的描述性表达。
    # 目前，它是以表情符号实现的。
    self.act_pronunciatio = None
    # <event_form> 表示角色当前参与的事件三元组。
    self.act_event = (self.name, None, None)

    # <obj_description> 是对象动作的字符串描述。
    self.act_obj_description = None
    # <obj_pronunciatio> 是对象动作的描述性表达。
    # 目前，它是以表情符号实现的。
    self.act_obj_pronunciatio = None
    # <obj_event_form> 表示动作对象当前参与的事件三元组。
    self.act_obj_event = (self.name, None, None)

    # <chatting_with> 是当前角色正在与之聊天的角色的字符串名称。如果不存在则为 None。
    self.chatting_with = None
    # <chat> 是一个列表的列表，用于保存两个角色之间的对话。
    # 它的格式是：[["Dolores Murphy", "Hi"], 
    #                           ["Maeve Jenson", "Hi"] ...]
    self.chat = None
    # <chatting_with_buffer>  
    # e.g., ["Dolores Murphy"] = self.vision_r
    self.chatting_with_buffer = dict()
    self.chatting_end_time = None

    # <path_set> 如果我们已经计算了角色执行此动作将要采用的路径，则为 True。
    # 该路径存储在角色的 scratch.planned_path 中。
    self.act_path_set = False
    # <planned_path> 是一个 x y 坐标元组（瓦片）的列表，描述了角色执行 <curr_action> (当前动作) 将要采用的路径。
    # 该列表不包括角色的当前瓦片，但包括目标瓦片。
    # e.g., [(50, 10), (49, 10), (48, 10), ...]
    self.planned_path = []

    if check_if_file_exists(f_saved): 
      # 如果我们有引导文件，在此处加载。
      scratch_load = json.load(open(f_saved))

      self.vision_r = scratch_load["vision_r"]
      self.att_bandwidth = scratch_load["att_bandwidth"]
      self.retention = scratch_load["retention"]

      if scratch_load["curr_time"]: 
        self.curr_time = datetime.datetime.strptime(scratch_load["curr_time"],
                                                  "%B %d, %Y, %H:%M:%S")
      else: 
        self.curr_time = None
      self.curr_tile = scratch_load["curr_tile"]
      self.daily_plan_req = scratch_load["daily_plan_req"]

      self.name = scratch_load["name"]
      self.first_name = scratch_load["first_name"]
      self.last_name = scratch_load["last_name"]
      self.age = scratch_load["age"]
      self.innate = scratch_load["innate"]
      self.learned = scratch_load["learned"]
      self.currently = scratch_load["currently"]
      self.lifestyle = scratch_load["lifestyle"]
      self.living_area = scratch_load["living_area"]

      self.concept_forget = scratch_load["concept_forget"]
      self.daily_reflection_time = scratch_load["daily_reflection_time"]
      self.daily_reflection_size = scratch_load["daily_reflection_size"]
      self.overlap_reflect_th = scratch_load["overlap_reflect_th"]
      self.kw_strg_event_reflect_th = scratch_load["kw_strg_event_reflect_th"]
      self.kw_strg_thought_reflect_th = scratch_load["kw_strg_thought_reflect_th"]

      self.recency_w = scratch_load["recency_w"]
      self.relevance_w = scratch_load["relevance_w"]
      self.importance_w = scratch_load["importance_w"]
      self.recency_decay = scratch_load["recency_decay"]
      self.importance_trigger_max = scratch_load["importance_trigger_max"]
      self.importance_trigger_curr = scratch_load["importance_trigger_curr"]
      self.importance_ele_n = scratch_load["importance_ele_n"]
      self.thought_count = scratch_load["thought_count"]

      self.daily_req = scratch_load["daily_req"]
      self.f_daily_schedule = scratch_load["f_daily_schedule"]
      self.f_daily_schedule_hourly_org = scratch_load["f_daily_schedule_hourly_org"]

      self.act_address = scratch_load["act_address"]
      if scratch_load["act_start_time"]: 
        self.act_start_time = datetime.datetime.strptime(
                                              scratch_load["act_start_time"],
                                              "%B %d, %Y, %H:%M:%S")
      else: 
        self.curr_time = None
      self.act_duration = scratch_load["act_duration"]
      self.act_description = scratch_load["act_description"]
      self.act_pronunciatio = scratch_load["act_pronunciatio"]
      self.act_event = tuple(scratch_load["act_event"])

      self.act_obj_description = scratch_load["act_obj_description"]
      self.act_obj_pronunciatio = scratch_load["act_obj_pronunciatio"]
      self.act_obj_event = tuple(scratch_load["act_obj_event"])

      self.chatting_with = scratch_load["chatting_with"]
      self.chat = scratch_load["chat"]
      self.chatting_with_buffer = scratch_load["chatting_with_buffer"]
      if scratch_load["chatting_end_time"]: 
        self.chatting_end_time = datetime.datetime.strptime(
                                            scratch_load["chatting_end_time"],
                                            "%B %d, %Y, %H:%M:%S")
      else:
        self.chatting_end_time = None

      self.act_path_set = scratch_load["act_path_set"]
      self.planned_path = scratch_load["planned_path"]


  def save(self, out_json):
    """
    保存角色的暂存信息。

    输入:
      out_json: 我们将保存角色状态的文件。
    输出:
      无
    """
    scratch = dict() 
    scratch["vision_r"] = self.vision_r
    scratch["att_bandwidth"] = self.att_bandwidth
    scratch["retention"] = self.retention

    scratch["curr_time"] = self.curr_time.strftime("%B %d, %Y, %H:%M:%S")
    scratch["curr_tile"] = self.curr_tile
    scratch["daily_plan_req"] = self.daily_plan_req

    scratch["name"] = self.name
    scratch["first_name"] = self.first_name
    scratch["last_name"] = self.last_name
    scratch["age"] = self.age
    scratch["innate"] = self.innate
    scratch["learned"] = self.learned
    scratch["currently"] = self.currently
    scratch["lifestyle"] = self.lifestyle
    scratch["living_area"] = self.living_area

    scratch["concept_forget"] = self.concept_forget
    scratch["daily_reflection_time"] = self.daily_reflection_time
    scratch["daily_reflection_size"] = self.daily_reflection_size
    scratch["overlap_reflect_th"] = self.overlap_reflect_th
    scratch["kw_strg_event_reflect_th"] = self.kw_strg_event_reflect_th
    scratch["kw_strg_thought_reflect_th"] = self.kw_strg_thought_reflect_th

    scratch["recency_w"] = self.recency_w
    scratch["relevance_w"] = self.relevance_w
    scratch["importance_w"] = self.importance_w
    scratch["recency_decay"] = self.recency_decay
    scratch["importance_trigger_max"] = self.importance_trigger_max
    scratch["importance_trigger_curr"] = self.importance_trigger_curr
    scratch["importance_ele_n"] = self.importance_ele_n
    scratch["thought_count"] = self.thought_count

    scratch["daily_req"] = self.daily_req
    scratch["f_daily_schedule"] = self.f_daily_schedule
    scratch["f_daily_schedule_hourly_org"] = self.f_daily_schedule_hourly_org

    scratch["act_address"] = self.act_address
    scratch["act_start_time"] = (self.act_start_time
                                     .strftime("%B %d, %Y, %H:%M:%S"))
    scratch["act_duration"] = self.act_duration
    scratch["act_description"] = self.act_description
    scratch["act_pronunciatio"] = self.act_pronunciatio
    scratch["act_event"] = self.act_event

    scratch["act_obj_description"] = self.act_obj_description
    scratch["act_obj_pronunciatio"] = self.act_obj_pronunciatio
    scratch["act_obj_event"] = self.act_obj_event

    scratch["chatting_with"] = self.chatting_with
    scratch["chat"] = self.chat
    scratch["chatting_with_buffer"] = self.chatting_with_buffer
    if self.chatting_end_time: 
      scratch["chatting_end_time"] = (self.chatting_end_time
                                        .strftime("%B %d, %Y, %H:%M:%S"))
    else: 
      scratch["chatting_end_time"] = None

    scratch["act_path_set"] = self.act_path_set
    scratch["planned_path"] = self.planned_path

    with open(out_json, "w") as outfile:
      json.dump(scratch, outfile, indent=2) 


  def get_f_daily_schedule_index(self, advance=0):
    """
    获取 self.f_daily_schedule 的当前索引。

    回想一下，self.f_daily_schedule 存储了到目前为止已分解的动作序列，
    以及当天剩余未来动作的每小时序列。
    鉴于 self.f_daily_schedule 是一个列表的列表，其中内部列表由 [任务, 持续时间] 组成，
    我们继续累加持续时间，直到达到 "if elapsed > today_min_elapsed" (如果已过时间 > 今天已过分钟数) 条件。
    我们停止处的索引就是要返回的索引。

    输入
      advance: 我们希望展望未来的分钟数（整数值）。
               这使我们能够获取未来时间范围的索引。
    输出
      f_daily_schedule 当前索引的整数值。
    """
    # 我们首先计算今天已经过去的分钟数。
    today_min_elapsed = 0
    today_min_elapsed += self.curr_time.hour * 60
    today_min_elapsed += self.curr_time.minute
    today_min_elapsed += advance

    x = 0
    for task, duration in self.f_daily_schedule: 
      x += duration
    x = 0
    for task, duration in self.f_daily_schedule_hourly_org: 
      x += duration

    # 然后我们据此计算当前索引。
    curr_index = 0
    elapsed = 0
    for task, duration in self.f_daily_schedule: 
      elapsed += duration
      if elapsed > today_min_elapsed: 
        return curr_index
      curr_index += 1

    return curr_index


  def get_f_daily_schedule_hourly_org_index(self, advance=0):
    """
    获取 self.f_daily_schedule_hourly_org 的当前索引。
    除此以外，与 get_f_daily_schedule_index 相同。

    输入
      advance: 我们希望展望未来的分钟数（整数值）。
               这使我们能够获取未来时间范围的索引。
    输出
      f_daily_schedule_hourly_org 当前索引的整数值。(应为 f_daily_schedule_hourly_org)
    """
    # 我们首先计算今天已经过去的分钟数。
    today_min_elapsed = 0
    today_min_elapsed += self.curr_time.hour * 60
    today_min_elapsed += self.curr_time.minute
    today_min_elapsed += advance
    # 然后我们据此计算当前索引。
    curr_index = 0
    elapsed = 0
    for task, duration in self.f_daily_schedule_hourly_org: 
      elapsed += duration
      if elapsed > today_min_elapsed: 
        return curr_index
      curr_index += 1
    return curr_index


  def get_str_iss(self): 
    """
    ISS 代表“身份稳定集”。这描述了此角色的共同集摘要
    ——基本上，这是在几乎所有需要调用角色的提示中都会使用的
    角色的最基本描述。

    输入
      无
    输出
      字符串形式的角色的身份稳定集摘要。
    输出字符串示例
      "姓名: 多洛莉丝·海特米勒
       年龄: 28
       先天特质: 棱角分明, 独立, 忠诚
       习得特质: 多洛莉丝是一位画家，她想安静地生活和画画，同时享受她的日常生活。
       当前: 多洛莉丝正在为她的首次个展做准备。她大部分时间在家工作。
       生活方式: 多洛莉丝大约晚上11点睡觉，睡7个小时，下午6点左右吃晚饭。
       每日计划需求: 多洛莉丝计划整天呆在家里，从不外出。"
    """
    commonset = ""
    commonset += f"姓名: {self.name}\n" # Name
    commonset += f"年龄: {self.age}\n" # Age
    commonset += f"先天特质: {self.innate}\n" # Innate traits
    commonset += f"习得特质: {self.learned}\n" # Learned traits
    commonset += f"当前: {self.currently}\n" # Currently
    commonset += f"生活方式: {self.lifestyle}\n" # Lifestyle
    commonset += f"每日计划需求: {self.daily_plan_req}\n" # Daily plan requirement
    commonset += f"当前日期: {self.curr_time.strftime('%A %B %d')}\n" # Current Date
    return commonset


  def get_str_name(self): 
    return self.name


  def get_str_firstname(self): 
    return self.first_name


  def get_str_lastname(self): 
    return self.last_name


  def get_str_age(self): 
    return str(self.age)


  def get_str_innate(self): 
    return self.innate


  def get_str_learned(self): 
    return self.learned


  def get_str_currently(self): 
    return self.currently


  def get_str_lifestyle(self): 
    return self.lifestyle


  def get_str_daily_plan_req(self): 
    return self.daily_plan_req


  def get_str_curr_date_str(self): 
    return self.curr_time.strftime("%A %B %d")


  def get_curr_event(self):
    if not self.act_address: 
      return (self.name, None, None)
    else: 
      return self.act_event


  def get_curr_event_and_desc(self): 
    if not self.act_address: 
      return (self.name, None, None, None)
    else: 
      return (self.act_event[0], 
              self.act_event[1], 
              self.act_event[2],
              self.act_description)


  def get_curr_obj_event_and_desc(self): 
    if not self.act_address: 
      return ("", None, None, None)
    else: 
      return (self.act_address, 
              self.act_obj_event[1], 
              self.act_obj_event[2],
              self.act_obj_description)


  def add_new_action(self, 
                     action_address, 
                     action_duration,
                     action_description,
                     action_pronunciatio, 
                     action_event,
                     chatting_with, 
                     chat, 
                     chatting_with_buffer,
                     chatting_end_time,
                     act_obj_description, 
                     act_obj_pronunciatio, 
                     act_obj_event, 
                     act_start_time=None): 
    self.act_address = action_address
    self.act_duration = action_duration
    self.act_description = action_description
    self.act_pronunciatio = action_pronunciatio
    self.act_event = action_event

    self.chatting_with = chatting_with
    self.chat = chat 
    if chatting_with_buffer: 
      self.chatting_with_buffer.update(chatting_with_buffer)
    self.chatting_end_time = chatting_end_time

    self.act_obj_description = act_obj_description
    self.act_obj_pronunciatio = act_obj_pronunciatio
    self.act_obj_event = act_obj_event
    
    self.act_start_time = self.curr_time
    
    self.act_path_set = False


  def act_time_str(self): 
    """
    返回当前时间的字符串输出。

    输入
      无
    输出
      当前时间的字符串输出。
    输出字符串示例
      "14:05 P.M."
    """
    return self.act_start_time.strftime("%H:%M %p")


  def act_check_finished(self): 
    """
    检查 self.Action 实例是否已完成。

    输入
      curr_datetime: 当前时间。如果当前时间晚于动作的开始时间 + 持续时间，
                     则动作已完成。
    输出
      布尔值 [True]: 动作已完成。
      布尔值 [False]: 动作尚未完成，仍在进行中。
    """
    if not self.act_address: 
      return True
      
    if self.chatting_with: 
      end_time = self.chatting_end_time
    else: 
      x = self.act_start_time
      if x.second != 0: 
        x = x.replace(second=0)
        x = (x + datetime.timedelta(minutes=1))
      end_time = (x + datetime.timedelta(minutes=self.act_duration))

    if end_time.strftime("%H:%M:%S") == self.curr_time.strftime("%H:%M:%S"): 
      return True
    return False


  def act_summarize(self):
    """
    将当前动作总结为字典。

    输入
      无
    输出
      ret: 动作的人类可读摘要。
    """
    exp = dict()
    exp["persona"] = self.name
    exp["address"] = self.act_address
    exp["start_datetime"] = self.act_start_time
    exp["duration"] = self.act_duration
    exp["description"] = self.act_description
    exp["pronunciatio"] = self.act_pronunciatio
    return exp


  def act_summary_str(self):
    """
    返回当前动作的字符串摘要。旨在供人类阅读。

    输入
      无
    输出
      ret: 动作的人类可读摘要。
    """
    start_datetime_str = self.act_start_time.strftime("%A %B %d -- %H:%M %p")
    ret = f"[{start_datetime_str}]\n"
    ret += f"活动: {self.name} 正在 {self.act_description}\n"
    ret += f"地址: {self.act_address}\n"
    ret += f"持续时间（分钟） (例如 x 分钟): {str(self.act_duration)} 分钟\n"
    return ret


  def get_str_daily_schedule_summary(self): 
    ret = ""
    curr_min_sum = 0
    for row in self.f_daily_schedule: 
      curr_min_sum += row[1]
      hour = int(curr_min_sum/60)
      minute = curr_min_sum%60
      ret += f"{hour:02}:{minute:02} || {row[0]}\n"
    return ret


  def get_str_daily_schedule_hourly_org_summary(self): 
    ret = ""
    curr_min_sum = 0
    for row in self.f_daily_schedule_hourly_org: 
      curr_min_sum += row[1]
      hour = int(curr_min_sum/60)
      minute = curr_min_sum%60
      ret += f"{hour:02}:{minute:02} || {row[0]}\n"
    return ret




















