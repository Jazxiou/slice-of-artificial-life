"""
Original Author: Joon Sung Park (joonspk@stanford.edu)
Fork Maintainer: Yasmina Abdallah
File: views.py
"""

import datetime
import json
import os
import random
import string
from os import listdir

from django.contrib.staticfiles.templatetags.staticfiles import static
from django.http import HttpResponse, JsonResponse
from django.shortcuts import HttpResponseRedirect, redirect, render
from global_methods import *

from .models import *


def persona_list(sim_code):
    """The characters in a simulation asset URLs."""
    personas = []
    for i in find_filenames(f"storage/{sim_code}/personas", ""):
        name = i.split("/")[-1].strip()
        if name[0] == ".":
            continue
        underscore = name.replace(" ", "_")
        personas += [
            {
                "original": name,
                "underscore": underscore,
                "sprite": static(f"assets/characters/{underscore}.png"),
                "profile": static(f"assets/characters/profile/{underscore}.png"),
            }
        ]
    return personas


def landing(request):
    context = {}
    template = "landing/landing.html"
    return render(request, template, context)


def demo(request, sim_code, step, play_speed="2"):
    move_file = f"compressed_storage/{sim_code}/master_movement.json"
    meta_file = f"compressed_storage/{sim_code}/meta.json"
    step = int(step)
    play_speed_opt = {"1": 1, "2": 2, "3": 4, "4": 8, "5": 16, "6": 32}
    if play_speed not in play_speed_opt:
        play_speed = 2
    else:
        play_speed = play_speed_opt[play_speed]

    # Loading the basic meta information about the simulation.
    meta = dict()
    with open(meta_file) as json_file:
        meta = json.load(json_file)

    sec_per_step = meta["sec_per_step"]
    start_datetime = datetime.datetime.strptime(meta["start_date"] + " 00:00:00", "%B %d, %Y %H:%M:%S")
    for i in range(step):
        start_datetime += datetime.timedelta(seconds=sec_per_step)
    start_datetime = start_datetime.strftime("%Y-%m-%dT%H:%M:%S")

    # Loading the movement file
    raw_all_movement = dict()
    with open(move_file) as json_file:
        raw_all_movement = json.load(json_file)

    # Loading all names of the personas
    persona_names = dict()
    persona_names = []
    persona_names_set = set()
    for p in list(raw_all_movement["0"].keys()):
        persona_names += [{"original": p, "underscore": p.replace(" ", "_"), "initial": p[0] + p.split(" ")[-1][0]}]
        persona_names_set.add(p)

    # <all_movement> is the main movement variable that we are passing to the
    # frontend. Whereas we use ajax scheme to communicate steps to the frontend
    # during the simulation stage, for this demo, we send all movement
    # information in one step.
    all_movement = dict()

    # Preparing the initial step.
    # <init_prep> sets the locations and descriptions of all agents at the
    # beginning of the demo determined by <step>.
    init_prep = dict()
    for int_key in range(step + 1):
        key = str(int_key)
        val = raw_all_movement[key]
        for p in persona_names_set:
            if p in val:
                init_prep[p] = val[p]
    persona_init_pos = dict()
    for p in persona_names_set:
        persona_init_pos[p.replace(" ", "_")] = init_prep[p]["movement"]
    all_movement[step] = init_prep

    # Finish loading <all_movement>
    for int_key in range(step + 1, len(raw_all_movement.keys())):
        all_movement[int_key] = raw_all_movement[str(int_key)]

    context = {
        "sim_code": sim_code,
        "step": step,
        "persona_names": persona_names,
        "persona_init_pos": json.dumps(persona_init_pos),
        "all_movement": json.dumps(all_movement),
        "start_datetime": start_datetime,
        "sec_per_step": sec_per_step,
        "play_speed": play_speed,
        "mode": "demo",
    }
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

    persona_names = persona_list(sim_code)
    persona_names_set = set(p["original"] for p in persona_names)

    persona_init_pos = []
    file_count = []
    for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
        x = i.split("/")[-1].strip()
        if x[0] != ".":
            file_count += [int(x.split(".")[0])]
    curr_json = f"storage/{sim_code}/environment/{str(max(file_count))}.json"
    with open(curr_json) as json_file:
        persona_init_pos_dict = json.load(json_file)
        for key, val in persona_init_pos_dict.items():
            if key in persona_names_set:
                persona_init_pos += [[key, val["x"], val["y"]]]

    context = {
        "sim_code": sim_code,
        "step": step,
        "persona_names": persona_names,
        "persona_init_pos": persona_init_pos,
        "atlas_json": static("assets/characters/atlas.json"),
        "camera_sprite": static("assets/characters/Yuriko_Yamamoto.png"),
        "mode": "simulate",
    }
    template = "home/home.html"
    return render(request, template, context)


def replay(request, sim_code, step):
    sim_code = sim_code
    step = int(step)

    persona_names = persona_list(sim_code)
    persona_names_set = set(p["original"] for p in persona_names)

    persona_init_pos = []
    file_count = []
    for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
        x = i.split("/")[-1].strip()
        if x[0] != ".":
            file_count += [int(x.split(".")[0])]
    curr_json = f"storage/{sim_code}/environment/{str(max(file_count))}.json"
    with open(curr_json) as json_file:
        persona_init_pos_dict = json.load(json_file)
        for key, val in persona_init_pos_dict.items():
            if key in persona_names_set:
                persona_init_pos += [[key, val["x"], val["y"]]]

    context = {
        "sim_code": sim_code,
        "step": step,
        "persona_names": persona_names,
        "persona_init_pos": persona_init_pos,
        "atlas_json": static("assets/characters/atlas.json"),
        "camera_sprite": static("assets/characters/Yuriko_Yamamoto.png"),
        "mode": "replay",
    }
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

    context = {
        "sim_code": sim_code,
        "step": step,
        "persona_name": persona_name,
        "persona_name_underscore": persona_name_underscore,
        "scratch": scratch,
        "spatial": spatial,
        "a_mem_event": a_mem_event,
        "a_mem_chat": a_mem_chat,
        "a_mem_thought": a_mem_thought,
    }
    template = "persona_state/persona_state.html"
    return render(request, template, context)


def path_tester(request):
    context = {}
    template = "path_tester/path_tester.html"
    return render(request, template, context)


def process_environment(request):
    """
    <FRONTEND to BACKEND>
    This sends the frontend visual world information to the backend server.
    It does this by writing the current environment representation to
    "storage/environment.json" file.

    ARGS:
      request: Django request
    RETURNS:
      HttpResponse: string confirmation message.
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

    return HttpResponse("received")


def update_environment(request):
    """
    <BACKEND to FRONTEND>
    This sends the backend computation of the persona behavior to the frontend
    visual server.
    It does this by reading the new movement information from
    "storage/movement.json" file.

    ARGS:
      request: Django request
    RETURNS:
      HttpResponse
    """
    # f_curr_sim_code = "temp_storage/curr_sim_code.json"
    # with open(f_curr_sim_code) as json_file:
    #   sim_code = json.load(json_file)["sim_code"]

    data = json.loads(request.body)
    step = data["step"]
    sim_code = data["sim_code"]

    response_data = {"<step>": -1}
    if check_if_file_exists(f"storage/{sim_code}/movement/{step}.json"):
        with open(f"storage/{sim_code}/movement/{step}.json") as json_file:
            response_data = json.load(json_file)
            response_data["<step>"] = step

    return JsonResponse(response_data)


def path_tester_update(request):
    """
    Processing the path and saving it to path_tester_env.json temp storage for
    conducting the path tester.

    ARGS:
      request: Django request
    RETURNS:
      HttpResponse: string confirmation message.
    """
    data = json.loads(request.body)
    camera = data["camera"]

    with open("temp_storage/path_tester_env.json", "w") as outfile:
        outfile.write(json.dumps(camera, indent=2))

    return HttpResponse("received")


# ---------------------------------------------------------------------------------------------------
# THE LIVE TOWN (the Ville Viewer). New views on new URLs; the stock pages above are untouched.
# ---------------------------------------------------------------------------------------------------


def livetown(request):
    """
    The Ville Viewer: the live town's own page.
    Same handshake as the stock `home` view (the backend announces itself through
    `temp_storage/curr_sim_code.json` / `curr_step.json`, and this page then drives the world clock
    through `process_environment` / `update_environment`), but rendering the new interface. Both
    pages read `curr_step.json` without removing it, deliberately differing from `home` there: the
    file marks "a backend is waiting", and either page may be the one that answers it, or be
    refreshed, without stranding the other.
    """
    f_curr_sim_code = "temp_storage/curr_sim_code.json"
    f_curr_step = "temp_storage/curr_step.json"

    if not check_if_file_exists(f_curr_step):
        return render(request, "home/error_start_backend.html", {})

    with open(f_curr_sim_code) as json_file:
        sim_code = json.load(json_file)["sim_code"]
    with open(f_curr_step) as json_file:
        step = json.load(json_file)["step"]

    persona_names = persona_list(sim_code)
    persona_names_set = set(p["original"] for p in persona_names)

    persona_init_pos = []
    file_count = []
    for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
        x = i.split("/")[-1].strip()
        if x[0] != ".":
            file_count += [int(x.split(".")[0])]
    curr_json = f"storage/{sim_code}/environment/{str(max(file_count))}.json"
    with open(curr_json) as json_file:
        persona_init_pos_dict = json.load(json_file)
        for key, val in persona_init_pos_dict.items():
            if key in persona_names_set:
                persona_init_pos += [[key, val["x"], val["y"]]]

    context = {
        "sim_code": sim_code,
        "step": step,
        "persona_names": persona_names,
        "persona_init_pos": persona_init_pos,
        "atlas_json": static("assets/characters/atlas.json"),
        "camera_sprite": static("assets/characters/Yuriko_Yamamoto.png"),
    }
    return render(request, "home/livetown.html", context)


def livetown_snapshot(request, persona_name):
    """
    <BACKEND to FRONTEND, slow feed> One character's viewer snapshot (memories, relationships,
    identity), refreshed by the backend every few simulated minutes. `{}` until the first one lands.
    """
    path = f"temp_storage/livetown/{persona_name}.json"
    if not check_if_file_exists(path):
        return JsonResponse({})
    with open(path) as json_file:
        return JsonResponse(json.load(json_file))


def livetown_control(request):
    """
    <FRONTEND to BACKEND> The viewer's save-and-exit / exit buttons.
    Writes the one small control file the live town's backend polls between steps
    (`run_livetown.py`). Only the two known actions are ever written; anything else is refused, so a
    broken client cannot make the backend act on words this contract does not contain.
    """
    data = json.loads(request.body)
    action = data.get("action")
    if action not in ("save_exit", "exit"):
        return JsonResponse({"ok": False, "error": "unknown action"}, status=400)
    with open("temp_storage/livetown_control.json", "w") as outfile:
        outfile.write(json.dumps({"action": action}))
    return JsonResponse({"ok": True, "action": action})
