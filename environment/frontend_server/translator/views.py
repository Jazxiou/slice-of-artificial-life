"""
作者: Joon Sung Park (joonspk@stanford.edu)
文件: views.py
"""
import os
import string
import random
import json
from os import listdir
import os

import datetime
from django.shortcuts import render, redirect, HttpResponseRedirect
from django.http import HttpResponse, JsonResponse
from global_methods import *

from django.contrib.staticfiles.templatetags.staticfiles import static
from .models import *

def landing(request): 
  context = {}
  template = "landing/landing.html"
  return render(request, template, context)


def demo(request, sim_code, step, play_speed="2"): 
  move_file = f"compressed_storage/{sim_code}/master_movement.json"
  meta_file = f"compressed_storage/{sim_code}/meta.json"
  step = int(step)
  play_speed_opt = {"1": 1, "2": 2, "3": 4,
                    "4": 8, "5": 16, "6": 32}
  if play_speed not in play_speed_opt: play_speed = 2
  else: play_speed = play_speed_opt[play_speed]

  # 加载关于模拟的基本元信息。
  meta = dict() 
  with open (meta_file) as json_file: 
    meta = json.load(json_file)

  sec_per_step = meta["sec_per_step"]
  start_datetime = datetime.datetime.strptime(meta["start_date"] + " 00:00:00", 
                                              '%B %d, %Y %H:%M:%S')
  for i in range(step): 
    start_datetime += datetime.timedelta(seconds=sec_per_step)
  start_datetime = start_datetime.strftime("%Y-%m-%dT%H:%M:%S")

  # 加载移动文件
  raw_all_movement = dict()
  with open(move_file) as json_file: 
    raw_all_movement = json.load(json_file)
 
  # 加载所有角色的名称
  persona_names = dict()
  persona_names = []
  persona_names_set = set()
  for p in list(raw_all_movement["0"].keys()): 
    persona_names += [{"original": p, 
                       "underscore": p.replace(" ", "_"), 
                       "initial": p[0] + p.split(" ")[-1][0]}]
    persona_names_set.add(p)

  # <all_movement> 是我们传递给前端的主要移动变量。
  # 在模拟阶段，我们使用 ajax 方案与前端通信步骤，但在此演示中，
  # 我们一步发送所有移动信息。
  all_movement = dict()

  # 准备初始步骤。
  # <init_prep> 设置由 <step> 决定的演示开始时所有代理的位置和描述。
  init_prep = dict() 
  for int_key in range(step+1): 
    key = str(int_key)
    val = raw_all_movement[key]
    for p in persona_names_set: 
      if p in val: 
        init_prep[p] = val[p]
  persona_init_pos = dict()
  for p in persona_names_set: 
    persona_init_pos[p.replace(" ","_")] = init_prep[p]["movement"]
  all_movement[step] = init_prep

  # 完成加载 <all_movement>
  for int_key in range(step+1, len(raw_all_movement.keys())): 
    all_movement[int_key] = raw_all_movement[str(int_key)]

  context = {"sim_code": sim_code,
             "step": step,
             "persona_names": persona_names,
             "persona_init_pos": json.dumps(persona_init_pos), 
             "all_movement": json.dumps(all_movement), 
             "start_datetime": start_datetime,
             "sec_per_step": sec_per_step,
             "play_speed": play_speed,
             "mode": "demo"}
  template = "demo/demo.html"

  return render(request, template, context)


def UIST_Demo(request): 
  return demo(request, "March20_the_ville_n25_UIST_RUN-step-1-141", 2160, play_speed="3")


def home(request):
  f_curr_sim_code = "temp_storage/curr_sim_code.json"
  f_curr_step = "temp_storage/curr_step.json"

  if not check_if_file_exists(f_curr_step): 
    context = {}
    template = "home/error_start_backend.html"
    return render(request, template, context)

  with open(f_curr_sim_code) as json_file:  
    sim_code = json.load(json_file)["sim_code"]
  
  with open(f_curr_step) as json_file:  
    step = json.load(json_file)["step"]

  os.remove(f_curr_step)

  persona_names = []
  persona_names_set = set()
  for i in find_filenames(f"storage/{sim_code}/personas", ""): 
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      persona_names += [[x, x.replace(" ", "_")]]
      persona_names_set.add(x)

  persona_init_pos = []
  file_count = []
  for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      file_count += [int(x.split(".")[0])]
  curr_json = f'storage/{sim_code}/environment/{str(max(file_count))}.json'
  with open(curr_json) as json_file:  
    persona_init_pos_dict = json.load(json_file)
    for key, val in persona_init_pos_dict.items(): 
      if key in persona_names_set: 
        persona_init_pos += [[key, val["x"], val["y"]]]

  context = {"sim_code": sim_code,
             "step": step, 
             "persona_names": persona_names,
             "persona_init_pos": persona_init_pos,
             "mode": "simulate"}
  template = "home/home.html"
  return render(request, template, context)


def replay(request, sim_code, step): 
  sim_code = sim_code
  step = int(step)

  persona_names = []
  persona_names_set = set()
  for i in find_filenames(f"storage/{sim_code}/personas", ""): 
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      persona_names += [[x, x.replace(" ", "_")]]
      persona_names_set.add(x)

  persona_init_pos = []
  file_count = []
  for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      file_count += [int(x.split(".")[0])]
  curr_json = f'storage/{sim_code}/environment/{str(max(file_count))}.json'
  with open(curr_json) as json_file:  
    persona_init_pos_dict = json.load(json_file)
    for key, val in persona_init_pos_dict.items(): 
      if key in persona_names_set: 
        persona_init_pos += [[key, val["x"], val["y"]]]

  context = {"sim_code": sim_code,
             "step": step,
             "persona_names": persona_names,
             "persona_init_pos": persona_init_pos, 
             "mode": "replay"}
  template = "home/home.html"
  return render(request, template, context)


def replay_persona_state(request, sim_code, step, persona_name): 
  sim_code = sim_code
  step = int(step)

  persona_name_underscore = persona_name
  persona_name = " ".join(persona_name.split("_"))
  memory = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
  if not os.path.exists(memory): 
    memory = f"compressed_storage/{sim_code}/personas/{persona_name}/bootstrap_memory"

  with open(memory + "/scratch.json") as json_file:  
    scratch = json.load(json_file)

  with open(memory + "/spatial_memory.json") as json_file:  
    spatial = json.load(json_file)

  with open(memory + "/associative_memory/nodes.json") as json_file:  
    associative = json.load(json_file)

  a_mem_event = []
  a_mem_chat = []
  a_mem_thought = []

  for count in range(len(associative.keys()), 0, -1): 
    node_id = f"node_{str(count)}"
    node_details = associative[node_id]

    if node_details["type"] == "event":
      a_mem_event += [node_details]

    elif node_details["type"] == "chat":
      a_mem_chat += [node_details]

    elif node_details["type"] == "thought":
      a_mem_thought += [node_details]
  
  context = {"sim_code": sim_code,
             "step": step,
             "persona_name": persona_name, 
             "persona_name_underscore": persona_name_underscore, 
             "scratch": scratch,
             "spatial": spatial,
             "a_mem_event": a_mem_event,
             "a_mem_chat": a_mem_chat,
             "a_mem_thought": a_mem_thought}
  template = "persona_state/persona_state.html"
  return render(request, template, context)


def path_tester(request):
  context = {}
  template = "path_tester/path_tester.html"
  return render(request, template, context)


def process_environment(request): 
  """
  <前端到后端>
  此函数将前端可视化世界信息发送到后端服务器。
  它通过将当前环境表示写入 "storage/environment.json" 文件来完成此操作。

  参数:
    request: Django 请求
  返回:
    HttpResponse: 字符串确认消息。
  """
  # f_curr_sim_code = "temp_storage/curr_sim_code.json"
  # with open(f_curr_sim_code) as json_file:  
  #   sim_code = json.load(json_file)["sim_code"]

  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]
  environment = data["environment"]

  with open(f"storage/{sim_code}/environment/{step}.json", "w") as outfile:
    outfile.write(json.dumps(environment, indent=2))

  return HttpResponse("已接收")


def update_environment(request): 
  """
  <后端到前端>
  此函数将角色行为的后端计算结果发送到前端可视化服务器。
  它通过从 "storage/movement.json" 文件读取新的移动信息来完成此操作。

  参数:
    request: Django 请求
  返回:
    JsonResponse
  """
  # f_curr_sim_code = "temp_storage/curr_sim_code.json"
  # with open(f_curr_sim_code) as json_file:  
  #   sim_code = json.load(json_file)["sim_code"]

  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]

  response_data = {"<step>": -1}
  if (check_if_file_exists(f"storage/{sim_code}/movement/{step}.json")):
    with open(f"storage/{sim_code}/movement/{step}.json") as json_file: 
      response_data = json.load(json_file)
      response_data["<step>"] = step

  return JsonResponse(response_data)


def path_tester_update(request): 
  """
  处理路径并将其保存到 path_tester_env.json 临时存储中，
  以便进行路径测试。

  参数:
    request: Django 请求
  返回:
    HttpResponse: 字符串确认消息。
  """
  data = json.loads(request.body)
  camera = data["camera"]

  with open(f"temp_storage/path_tester_env.json", "w") as outfile:
    outfile.write(json.dumps(camera, indent=2))

  return HttpResponse("已接收")









