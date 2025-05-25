"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: reverie.py
Description: This is the main program for running generative agent simulations
that defines the ReverieServer class. This class maintains and records all  
states related to the simulation. The primary mode of interaction for those  
running the simulation should be through the open_server function, which  
enables the simulator to input command-line prompts for running and saving  
the simulation, among other tasks.

Release note (June 14, 2023) -- Reverie implements the core simulation 
mechanism described in my paper entitled "Generative Agents: Interactive 
Simulacra of Human Behavior." If you are reading through these lines after 
having read the paper, you might notice that I use older terms to describe 
generative agents and their cognitive modules here. Most notably, I use the 
term "personas" to refer to generative agents, "associative memory" to refer 
to the memory stream, and "reverie" to refer to the overarching simulation 
framework.
"""
import json
import numpy
import datetime
import pickle
import time
import math
import os
import shutil
import traceback
import logging

from selenium import webdriver

from global_methods import *
from utils import *
from maze import *
from persona.persona import *

# ==================================================================================================
# CONFIGURE LOGGER
# ==================================================================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Default logging level
# Create a stream handler to output to console
stream_handler = logging.StreamHandler()
# Define log format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)
# Add the handler to the logger
if not logger.handlers:
    logger.addHandler(stream_handler)

##############################################################################
#                                  REVERIE                                   #
##############################################################################

class ReverieServer: 
  def __init__(self, 
               fork_sim_code,
               sim_code):
    # FORKING FROM A PRIOR SIMULATION:
    # <fork_sim_code> indicates the simulation we are forking from. 
    # Interestingly, all simulations must be forked from some initial 
    # simulation, where the first simulation is "hand-crafted".
    self.fork_sim_code = fork_sim_code
    logger.info(f"Forking simulation from: {self.fork_sim_code}")
    fork_folder = f"{fs_storage}/{self.fork_sim_code}"

    # <sim_code> indicates our current simulation. The first step here is to 
    # copy everything that's in <fork_sim_code>, but edit its 
    # reverie/meta/json's fork variable. 
    self.sim_code = sim_code
    logger.info(f"Initializing new simulation: {self.sim_code}")
    sim_folder = f"{fs_storage}/{self.sim_code}"
    try:
      copyanything(fork_folder, sim_folder)
      logger.info(f"Copied data from {fork_folder} to {sim_folder}")
    except Exception as e:
      logger.error(f"Error copying data from {fork_folder} to {sim_folder}: {e}", exc_info=True)
      # Depending on the desired behavior, we might want to raise the exception or exit
      raise # Reraising the exception as this is a critical step

    try:
      with open(f"{sim_folder}/reverie/meta.json") as json_file:  
        reverie_meta = json.load(json_file)
      with open(f"{sim_folder}/reverie/meta.json", "w") as outfile: 
        reverie_meta["fork_sim_code"] = fork_sim_code
        outfile.write(json.dumps(reverie_meta, indent=2))
      logger.info(f"Updated meta.json in {sim_folder} with fork_sim_code: {fork_sim_code}")
    except FileNotFoundError:
      logger.error(f"meta.json not found in {sim_folder}. This should have been copied from the fork.", exc_info=True)
      raise
    except json.JSONDecodeError:
      logger.error(f"Error decoding meta.json in {sim_folder}.", exc_info=True)
      raise
    except IOError as e:
      logger.error(f"IOError when accessing meta.json in {sim_folder}: {e}", exc_info=True)
      raise
    
    logger.info("Loading Reverie's global variables...")
    # LOADING REVERIE'S GLOBAL VARIABLES
    # The start datetime of the Reverie: 
    # <start_datetime> is the datetime instance for the start datetime of 
    # the Reverie instance. Once it is set, this is not really meant to 
    # change. It takes a string date in the following example form: 
    # "June 25, 2022"
    # e.g., ...strptime(June 25, 2022, "%B %d, %Y")
    try:
      self.start_time = datetime.datetime.strptime(
                          f"{reverie_meta['start_date']}, 00:00:00",  
                          "%B %d, %Y, %H:%M:%S")
      # <curr_time> is the datetime instance that indicates the game's current
      # time. This gets incremented by <sec_per_step> amount everytime the world
      # progresses (that is, everytime curr_env_file is recieved). 
      self.curr_time = datetime.datetime.strptime(reverie_meta['curr_time'], 
                                                  "%B %d, %Y, %H:%M:%S")
      # <sec_per_step> denotes the number of seconds in game time that each 
      # step moves foward. 
      self.sec_per_step = reverie_meta['sec_per_step']
      
      # <maze> is the main Maze instance. Note that we pass in the maze_name
      # (e.g., "double_studio") to instantiate Maze. 
      # e.g., Maze("double_studio")
      self.maze = Maze(reverie_meta['maze_name'])
      
      # <step> denotes the number of steps that our game has taken. A step here
      # literally translates to the number of moves our personas made in terms
      # of the number of tiles. 
      self.step = reverie_meta['step']
      logger.info(f"Reverie meta loaded: Start time: {self.start_time}, Current time: {self.curr_time}, Step: {self.step}")
    except KeyError as e:
      logger.error(f"KeyError accessing Reverie meta: {e}. Check meta.json structure.", exc_info=True)
      raise
    except ValueError as e:
      logger.error(f"ValueError during datetime parsing from Reverie meta: {e}.", exc_info=True)
      raise

    logger.info("Setting up personas...")
    # SETTING UP PERSONAS IN REVERIE
    # <personas> is a dictionary that takes the persona's full name as its 
    # keys, and the actual persona instance as its values.
    # This dictionary is meant to keep track of all personas who are part of
    # the Reverie instance. 
    # e.g., ["Isabella Rodriguez"] = Persona("Isabella Rodriguezs")
    self.personas = dict()
    # <personas_tile> is a dictionary that contains the tile location of
    # the personas (!-> NOT px tile, but the actual tile coordinate).
    # The tile take the form of a set, (row, col). 
    # e.g., ["Isabella Rodriguez"] = (58, 39)
    self.personas_tile = dict()
    
    # # <persona_convo_match> is a dictionary that describes which of the two
    # # personas are talking to each other. It takes a key of a persona's full
    # # name, and value of another persona's full name who is talking to the 
    # # original persona. 
    # # e.g., dict["Isabella Rodriguez"] = ["Maria Lopez"]
    # self.persona_convo_match = dict()
    # # <persona_convo> contains the actual content of the conversations. It
    # # takes as keys, a pair of persona names, and val of a string convo. 
    # # Note that the key pairs are *ordered alphabetically*. 
    # # e.g., dict[("Adam Abraham", "Zane Xu")] = "Adam: baba \n Zane:..."
    # self.persona_convo = dict()

    # Loading in all personas. 
    try:
      init_env_file = f"{sim_folder}/environment/{str(self.step)}.json"
      with open(init_env_file) as f:
        init_env = json.load(f)
      logger.info(f"Loading initial environment from: {init_env_file}")

      for persona_name in reverie_meta['persona_names']: 
        logger.debug(f"Loading persona: {persona_name}")
        persona_folder = f"{sim_folder}/personas/{persona_name}"
        p_x = init_env[persona_name]["x"]
        p_y = init_env[persona_name]["y"]
        curr_persona = Persona(persona_name, persona_folder)

        self.personas[persona_name] = curr_persona
        self.personas_tile[persona_name] = (p_x, p_y)
        self.maze.tiles[p_y][p_x]["events"].add(curr_persona.scratch
                                                .get_curr_event_and_desc())
        logger.info(f"Loaded persona {persona_name} at tile ({p_x}, {p_y})")
    except FileNotFoundError:
      logger.error(f"Initial environment file {init_env_file} not found.", exc_info=True)
      raise
    except json.JSONDecodeError:
      logger.error(f"Error decoding initial environment file {init_env_file}.", exc_info=True)
      raise
    except KeyError as e:
      logger.error(f"KeyError when loading persona data from init_env or reverie_meta: {e}", exc_info=True)
      raise
    except Exception as e:
      logger.error(f"An unexpected error occurred during persona setup: {e}", exc_info=True)
      raise

    # REVERIE SETTINGS PARAMETERS:  
    # <server_sleep> denotes the amount of time that our while loop rests each
    # cycle; this is to not kill our machine. 
    self.server_sleep = 0.1
    logger.info(f"Server sleep time set to: {self.server_sleep}s")

    # SIGNALING THE FRONTEND SERVER: 
    # curr_sim_code.json contains the current simulation code, and
    # curr_step.json contains the current step of the simulation. These are 
    # used to communicate the code and step information to the frontend. 
    # Note that step file is removed as soon as the frontend opens up the 
    # simulation. 
    logger.info("Signaling frontend server with simulation code and step...")
    try:
      curr_sim_code = dict()
      curr_sim_code["sim_code"] = self.sim_code
      with open(f"{fs_temp_storage}/curr_sim_code.json", "w") as outfile: 
        outfile.write(json.dumps(curr_sim_code, indent=2))
      
      curr_step = dict()
      curr_step["step"] = self.step
      with open(f"{fs_temp_storage}/curr_step.json", "w") as outfile: 
        outfile.write(json.dumps(curr_step, indent=2))
      logger.info(f"Frontend signal files created in {fs_temp_storage}")
    except IOError as e:
      logger.error(f"IOError writing frontend signal files: {e}", exc_info=True)
    except Exception as e:
      logger.error(f"Unexpected error writing frontend signal files: {e}", exc_info=True)


  def save(self): 
    """
    Save all Reverie progress -- this includes Reverie's global state as well
    as all the personas.  

    INPUT
      None
    OUTPUT 
      None
      * Saves all relevant data to the designated memory directory
    """
    logger.info(f"Saving simulation state for sim_code: {self.sim_code}")
    # <sim_folder> points to the current simulation folder.
    sim_folder = f"{fs_storage}/{self.sim_code}"

    try:
      # Save Reverie meta information.
      reverie_meta = dict() 
      reverie_meta["fork_sim_code"] = self.fork_sim_code
      reverie_meta["start_date"] = self.start_time.strftime("%B %d, %Y")
      reverie_meta["curr_time"] = self.curr_time.strftime("%B %d, %Y, %H:%M:%S")
      reverie_meta["sec_per_step"] = self.sec_per_step
      reverie_meta["maze_name"] = self.maze.maze_name
      reverie_meta["persona_names"] = list(self.personas.keys())
      reverie_meta["step"] = self.step
      reverie_meta_f = f"{sim_folder}/reverie/meta.json"
      with open(reverie_meta_f, "w") as outfile: 
        outfile.write(json.dumps(reverie_meta, indent=2))
      logger.info(f"Saved Reverie meta to {reverie_meta_f}")
    except IOError as e:
      logger.error(f"IOError saving Reverie meta: {e}", exc_info=True)
    except Exception as e:
      logger.error(f"Unexpected error saving Reverie meta: {e}", exc_info=True)

    try:
      # Save the personas.
      for persona_name, persona in self.personas.items(): 
        logger.debug(f"Saving persona: {persona_name}")
        save_folder = f"{sim_folder}/personas/{persona_name}/bootstrap_memory"
        persona.save(save_folder)
      logger.info(f"Saved all personas to {sim_folder}/personas")
    except Exception as e: # Persona save method might raise various exceptions
      logger.error(f"Error saving one or more personas: {e}", exc_info=True)
    logger.info("Save process completed.")


  def start_path_tester_server(self): 
    """
    Starts the path tester server. This is for generating the spatial memory
    that we need for bootstrapping a persona's state. 

    To use this, you need to open server and enter the path tester mode, and
    open the front-end side of the browser. 

    INPUT 
      None
    OUTPUT 
      None
      * Saves the spatial memory of the test agent to the path_tester_env.json
        of the temp storage. 
    """
    logger.info("Starting path tester server...")
    def print_tree(tree): 
      # This function is for direct output, so keeping print statements.
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
      
      _print_tree(tree, 0)

    # <curr_vision> is the vision radius of the test agent. Recommend 8 as 
    # our default. 
    curr_vision = 8
    # <s_mem> is our test spatial memory. 
    s_mem = dict()

    # The main while loop for the test agent. 
    while (True): 
      try: 
        curr_dict = {}
        tester_file = fs_temp_storage + "/path_tester_env.json"
        if check_if_file_exists(tester_file): 
          logger.debug(f"Path tester env file found: {tester_file}")
          try:
            with open(tester_file) as json_file: 
              curr_dict = json.load(json_file)
            os.remove(tester_file)
            logger.debug(f"Processed and removed {tester_file}")
          except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {tester_file}", exc_info=True)
            continue # Skip this iteration if file is corrupted
          except IOError as e:
            logger.error(f"IOError with {tester_file}: {e}", exc_info=True)
            continue # Skip this iteration
          except Exception as e:
            logger.error(f"Unexpected error processing {tester_file}: {e}", exc_info=True)
            continue

          # Current camera location
          curr_sts = self.maze.sq_tile_size
          curr_camera = (int(math.ceil(curr_dict["x"]/curr_sts)), 
                         int(math.ceil(curr_dict["y"]/curr_sts))+1)
          curr_tile_det = self.maze.access_tile(curr_camera)

          # Initiating the s_mem
          world = curr_tile_det["world"]
          if curr_tile_det["world"] not in s_mem: 
            s_mem[world] = dict()

          # Iterating throughn the nearby tiles.
          nearby_tiles = self.maze.get_nearby_tiles(curr_camera, curr_vision)
          for i in nearby_tiles: 
            i_det = self.maze.access_tile(i)
            if (curr_tile_det["sector"] == i_det["sector"] 
                and curr_tile_det["arena"] == i_det["arena"]): 
              if i_det["sector"] != "": 
                if i_det["sector"] not in s_mem[world]: 
                  s_mem[world][i_det["sector"]] = dict()
              if i_det["arena"] != "": 
                if i_det["arena"] not in s_mem[world][i_det["sector"]]: 
                  s_mem[world][i_det["sector"]][i_det["arena"]] = list()
              if i_det["game_object"] != "": 
                if (i_det["game_object"] 
                    not in s_mem[world][i_det["sector"]][i_det["arena"]]):
                  s_mem[world][i_det["sector"]][i_det["arena"]] += [
                                                         i_det["game_object"]]

        # Incrementally outputting the s_mem and saving the json file. 
        # This print is for console feedback during path testing.
        print ("= " * 15) 
        out_file = fs_temp_storage + "/path_tester_out.json"
        try:
          with open(out_file, "w") as outfile: 
            outfile.write(json.dumps(s_mem, indent=2))
          # This print_tree is for direct console output.
          print_tree(s_mem) 
        except IOError as e:
            logger.error(f"IOError writing path_tester_out.json: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error writing path_tester_out.json: {e}", exc_info=True)


      except Exception as e: # Catching broader exceptions in the while True loop
        logger.error(f"An error occurred in path tester server loop: {e}", exc_info=True)
        # Pass to allow the loop to continue, or add specific error handling logic
        pass

      time.sleep(self.server_sleep * 10)


  def start_server(self, int_counter): 
    """
    The main backend server of Reverie. 
    This function retrieves the environment file from the frontend to 
    understand the state of the world, calls on each personas to make 
    decisions based on the world state, and saves their moves at certain step
    intervals. 
    INPUT
      int_counter: Integer value for the number of steps left for us to take
                   in this iteration. 
    OUTPUT 
      None
    """
    logger.info(f"Starting Reverie server for {int_counter} steps.")
    # <sim_folder> points to the current simulation folder.
    sim_folder = f"{fs_storage}/{self.sim_code}"

    # When a persona arrives at a game object, we give a unique event
    # to that object. 
    # e.g., ('double studio[...]:bed', 'is', 'unmade', 'unmade')
    # Later on, before this cycle ends, we need to return that to its 
    # initial state, like this: 
    # e.g., ('double studio[...]:bed', None, None, None)
    # So we need to keep track of which event we added. 
    # <game_obj_cleanup> is used for that. 
    game_obj_cleanup = dict()

    # The main while loop of Reverie. 
    while (True): 
      # Done with this iteration if <int_counter> reaches 0. 
      if int_counter == 0: 
        logger.info("Reached target step count. Server loop ending.")
        break
      
      env_retrieved = False # ensure env_retrieved is defined
      # <curr_env_file> file is the file that our frontend outputs. When the
      # frontend has done its job and moved the personas, then it will put a 
      # new environment file that matches our step count. That's when we run 
      # the content of this for loop. Otherwise, we just wait. 
      curr_env_file = f"{sim_folder}/environment/{self.step}.json"
      if check_if_file_exists(curr_env_file):
        logger.debug(f"Environment file found: {curr_env_file} for step {self.step}")
        # If we have an environment file, it means we have a new perception
        # input to our personas. So we first retrieve it.
        try: 
          # Try and save block for robustness of the while loop.
          with open(curr_env_file) as json_file:
            new_env = json.load(json_file)
            env_retrieved = True
            logger.debug(f"Successfully loaded environment from {curr_env_file}")
        except FileNotFoundError: # Should be caught by check_if_file_exists, but good for robustness
          logger.error(f"Error: Environment file not found at {curr_env_file} (should have been checked)", exc_info=True)
          pass # Or time.sleep(x) then continue
        except json.JSONDecodeError:
          logger.error(f"Error: Could not decode JSON from {curr_env_file}", exc_info=True)
          pass
        except IOError as e:
          logger.error(f"Error: Could not read file at {curr_env_file}. IO Error: {e}", exc_info=True)
          pass
        except Exception as e:
          logger.error(f"An unexpected error occurred while retrieving environment file: {e}", exc_info=True)
          pass
      
        if env_retrieved: 
          logger.debug(f"Processing step {self.step}")
          # This is where we go through <game_obj_cleanup> to clean up all 
          # object actions that were used in this cylce. 
          try:
            for key, val in game_obj_cleanup.items(): 
              # We turn all object actions to their blank form (with None). 
              self.maze.turn_event_from_tile_idle(key, val)
            # Then we initialize game_obj_cleanup for this cycle. 
            game_obj_cleanup = dict()

            # We first move our personas in the backend environment to match 
            # the frontend environment. 
            for persona_name, persona in self.personas.items(): 
              # <curr_tile> is the tile that the persona was at previously. 
              curr_tile = self.personas_tile[persona_name]
              # <new_tile> is the tile that the persona will move to right now,
              # during this cycle. 
              new_tile = (new_env[persona_name]["x"], 
                          new_env[persona_name]["y"])

              # We actually move the persona on the backend tile map here. 
              self.personas_tile[persona_name] = new_tile
              self.maze.remove_subject_events_from_tile(persona.name, curr_tile)
              self.maze.add_event_from_tile(persona.scratch
                                           .get_curr_event_and_desc(), new_tile)
              logger.debug(f"Moved {persona_name} from {curr_tile} to {new_tile}")

              # Now, the persona will travel to get to their destination. *Once*
              # the persona gets there, we activate the object action.
              if not persona.scratch.planned_path: 
                logger.debug(f"{persona_name} reached destination, activating object action.")
                # We add that new object action event to the backend tile map. 
                # At its creation, it is stored in the persona's backend. 
                game_obj_cleanup[persona.scratch
                                 .get_curr_obj_event_and_desc()] = new_tile
                self.maze.add_event_from_tile(persona.scratch
                                       .get_curr_obj_event_and_desc(), new_tile)
                # We also need to remove the temporary blank action for the 
                # object that is currently taking the action. 
                blank = (persona.scratch.get_curr_obj_event_and_desc()[0], 
                         None, None, None)
                self.maze.remove_event_from_tile(blank, new_tile)

            # Then we need to actually have each of the personas perceive and
            # move. The movement for each of the personas comes in the form of
            # x y coordinates where the persona will move towards. e.g., (50, 34)
            # This is where the core brains of the personas are invoked. 
            movements = {"persona": dict(), 
                         "meta": dict()}
            for persona_name, persona in self.personas.items(): 
              logger.debug(f"Requesting move for {persona_name} at {self.personas_tile[persona_name]}")
              # <next_tile> is a x,y coordinate. e.g., (58, 9)
              # <pronunciatio> is an emoji. e.g., "\ud83d\udca4"
              # <description> is a string description of the movement. e.g., 
              #   writing her next novel (editing her novel) 
              #   @ double studio:double studio:common room:sofa
              next_tile, pronunciatio, description = persona.move(
                self.maze, self.personas, self.personas_tile[persona_name], 
                self.curr_time)
              movements["persona"][persona_name] = {}
              movements["persona"][persona_name]["movement"] = next_tile
              movements["persona"][persona_name]["pronunciatio"] = pronunciatio
              movements["persona"][persona_name]["description"] = description
              movements["persona"][persona_name]["chat"] = (persona
                                                            .scratch.chat)
              logger.debug(f"{persona_name} move generated: to {next_tile}, emoji {pronunciatio}, desc: {description}")

            # Include the meta information about the current stage in the 
            # movements dictionary. 
            movements["meta"]["curr_time"] = (self.curr_time 
                                               .strftime("%B %d, %Y, %H:%M:%S"))

            # We then write the personas' movements to a file that will be sent 
            # to the frontend server. 
            # Example json output: 
            # {"persona": {"Maria Lopez": {"movement": [58, 9]}},
            #  "persona": {"Klaus Mueller": {"movement": [38, 12]}}, 
            #  "meta": {curr_time: <datetime>}}
            curr_move_file = f"{sim_folder}/movement/{self.step}.json"
            try:
              with open(curr_move_file, "w") as outfile: 
                outfile.write(json.dumps(movements, indent=2))
              logger.info(f"Movements for step {self.step} written to {curr_move_file}")
            except IOError as e:
              logger.error(f"IOError writing movements file {curr_move_file}: {e}", exc_info=True)
            except Exception as e:
              logger.error(f"Unexpected error writing movements file {curr_move_file}: {e}", exc_info=True)


            # After this cycle, the world takes one step forward, and the 
            # current time moves by <sec_per_step> amount. 
            self.step += 1
            self.curr_time += datetime.timedelta(seconds=self.sec_per_step)
            logger.debug(f"Advanced to step {self.step}, current time: {self.curr_time.strftime('%B %d, %Y, %H:%M:%S')}")

            int_counter -= 1
          except KeyError as e: # Catching potential KeyErrors from new_env accesses or persona dicts
            logger.error(f"KeyError during step processing: {e}. Likely an issue with environment data or persona state.", exc_info=True)
            # Depending on severity, might need to break or implement more robust recovery
          except Exception as e: # Catch-all for other unexpected errors during the core step processing
            logger.error(f"An unexpected error occurred during server step {self.step} processing: {e}", exc_info=True)
            # This might indicate a more serious issue, consider if loop should continue

      # Sleep so we don't burn our machines. 
      time.sleep(self.server_sleep)

  # COMMAND HANDLER METHODS START HERE
  def _handle_lifecycle_commands(self, sim_command, sim_folder):
    """Handles simulation lifecycle commands: fin, exit, save, run."""
    ret_str = ""
    should_break = False

    if sim_command.lower() in ["f", "fin", "finish", "save and finish"]: 
      logger.info("Command: Finish and Save. Saving simulation state...")
      self.save()
      logger.info("Simulation saved. Exiting.") # Internal log
      should_break = True

    elif sim_command.lower() == "exit": 
      logger.info("Command: Exit without saving.") # Internal log
      try:
        logger.info(f"Removing simulation folder: {sim_folder}") # Internal log
        shutil.rmtree(sim_folder)
        logger.info(f"Successfully removed {sim_folder}") # Internal log
      except OSError as e:
        logger.error(f"Error: Could not remove simulation folder {sim_folder}. OS Error: {e}", exc_info=True) # Internal log
      logger.info("Exiting.") # Internal log
      should_break = True

    elif sim_command.lower() == "save": 
      logger.info("Command: Save.") # Internal log
      self.save()
      ret_str = "模拟进度已保存。"

    elif sim_command.startswith("run"): # Using startswith for "run"
      logger.info(f"Command: Run. Input: {sim_command}") # Internal log
      try:
        parts = sim_command.split()
        if len(parts) > 1:
            int_count = int(parts[-1])
            logger.info(f"Starting server for {int_count} steps.") # Internal log
            self.start_server(int_count) 
            ret_str = f"已完成运行 {int_count} 个步骤。"
        else:
            logger.error(f"Error: Number of steps not specified. Command: '{sim_command}'") # Internal log
            ret_str = f"错误：未指定步骤数。"
      except ValueError:
        logger.error(f"Error: Invalid number of steps. Please provide an integer. Command: '{sim_command}'", exc_info=True) # Internal log
        ret_str = f"错误：步骤数无效。请输入一个整数。"
      except IndexError: # Should be caught by len(parts) check, but as a safeguard
        logger.error(f"Error: Number of steps not specified or command malformed. Command: '{sim_command}'", exc_info=True) # Internal log
        ret_str = f"错误：未指定步骤数或命令格式错误。"
        
    return ret_str, should_break

  def _handle_persona_info_commands(self, sim_command):
    """Handles commands for printing persona information."""
    ret_str = ""
    persona_name_parts = sim_command.split()[-2:]
    persona_name_str = " ".join(persona_name_parts)

    if "print persona schedule" in sim_command and "hourly org" not in sim_command and "all" not in sim_command :
      logger.info(f"Command: Print Persona Schedule for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += (self.personas[persona_name_str]
                    .scratch.get_str_daily_schedule_summary())
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona schedule'.") # User-facing via ret_str
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print all persona schedule" in sim_command:
      logger.info("Command: Print All Persona Schedules") # Internal log
      for p_name, persona in self.personas.items(): 
        ret_str += f"{p_name}\n"
        ret_str += f"{persona.scratch.get_str_daily_schedule_summary()}\n"
        ret_str += f"---\n"

    elif "print hourly org persona schedule" in sim_command:
      logger.info(f"Command: Print Hourly Org Persona Schedule for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += (self.personas[persona_name_str]
                    .scratch.get_str_daily_schedule_hourly_org_summary())
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print hourly org persona schedule'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona current tile" in sim_command:
      logger.info(f"Command: Print Persona Current Tile for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += str(self.personas[persona_name_str].scratch.curr_tile)
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona current tile'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona chatting with buffer" in sim_command:
      logger.info(f"Command: Print Persona Chatting With Buffer for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        curr_persona = self.personas[persona_name_str]
        for p_n, count in curr_persona.scratch.chatting_with_buffer.items(): 
          ret_str += f"{p_n}: {count}\n"
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona chatting with buffer'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona associative memory (event)" in sim_command:
      logger.info(f"Command: Print Persona Associative Memory (Event) for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += f'{self.personas[persona_name_str].name}\n'
        ret_str += (self.personas[persona_name_str].a_mem.get_str_seq_events())
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona associative memory (event)'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona associative memory (thought)" in sim_command:
      logger.info(f"Command: Print Persona Associative Memory (Thought) for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += f'{self.personas[persona_name_str].name}\n'
        ret_str += (self.personas[persona_name_str].a_mem.get_str_seq_thoughts())
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona associative memory (thought)'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona associative memory (chat)" in sim_command:
      logger.info(f"Command: Print Persona Associative Memory (Chat) for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        ret_str += f'{self.personas[persona_name_str].name}\n'
        ret_str += (self.personas[persona_name_str].a_mem.get_str_seq_chats())
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona associative memory (chat)'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "print persona spatial memory" in sim_command:
      logger.info(f"Command: Print Persona Spatial Memory for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        self.personas[persona_name_str].s_mem.print_tree() 
        ret_str = f"{persona_name_str} 的空间记忆已打印在上方。"
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'print persona spatial memory'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"
    return ret_str

  def _handle_world_info_commands(self, sim_command):
    """Handles commands for printing world/environment information."""
    ret_str = ""
    if "print current time" in sim_command:
      logger.info("Command: Print Current Time") # Internal log
      ret_str += f'{self.curr_time.strftime("%B %d, %Y, %H:%M:%S")}\n'
      ret_str += f'步骤: {self.step}'

    elif "print tile event" in sim_command:
      coords_str = sim_command[len("print tile event"):].strip()
      logger.info(f"Command: Print Tile Event for coordinates: {coords_str}") # Internal log
      try:
        cooordinate = [int(i.strip()) for i in coords_str.split(",")]
        if len(cooordinate) != 2: raise ValueError("Invalid coordinate format")
        for i in self.maze.access_tile(cooordinate)["events"]: 
          ret_str += f"{i}\n"
      except ValueError:
        logger.error(f"Error: Invalid coordinates for 'print tile event'. Expected format: X, Y. Received: {coords_str}", exc_info=True) # User-facing
        ret_str = f"错误：坐标无效。预期格式：X, Y。收到：{coords_str}"
      except IndexError: 
        logger.error(f"Error: Coordinates not specified or incomplete for 'print tile event'. Received: {coords_str}", exc_info=True) # User-facing
        ret_str = f"错误：未指定坐标或坐标不完整。收到：{coords_str}"

    elif "print tile details" in sim_command:
      coords_str = sim_command[len("print tile details"):].strip()
      logger.info(f"Command: Print Tile Details for coordinates: {coords_str}") # Internal log
      try:
        cooordinate = [int(i.strip()) for i in coords_str.split(",")]
        if len(cooordinate) != 2: raise ValueError("Invalid coordinate format")
        for key, val in self.maze.access_tile(cooordinate).items(): 
          ret_str += f"{key}: {val}\n"
      except ValueError:
        logger.error(f"Error: Invalid coordinates for 'print tile details'. Expected format: X, Y. Received: {coords_str}", exc_info=True) # User-facing
        ret_str = f"错误：坐标无效。预期格式：X, Y。收到：{coords_str}"
      except IndexError: 
        logger.error(f"Error: Coordinates not specified or incomplete for 'print tile details'. Received: {coords_str}", exc_info=True) # User-facing
        ret_str = f"错误：未指定坐标或坐标不完整。收到：{coords_str}"
    return ret_str

  def _handle_call_commands(self, sim_command):
    """Handles 'call' commands."""
    ret_str = ""
    if "call -- analysis" in sim_command:
      persona_name_str = sim_command[len("call -- analysis"):].strip() 
      logger.info(f"Command: Call -- Analysis for {persona_name_str}") # Internal log
      if persona_name_str in self.personas:
        self.personas[persona_name_str].open_convo_session("analysis") 
        ret_str = f"已为 {persona_name_str} 打开对话会话 'analysis'。"
      else:
        logger.warning(f"Persona '{persona_name_str}' not found for 'call -- analysis'.") # User-facing
        ret_str = f"错误：未找到角色 '{persona_name_str}'。"

    elif "call -- load history" in sim_command:
      file_path_str = sim_command[len("call -- load history"):].strip()
      logger.info(f"Command: Call -- Load History from file: {file_path_str}") # Internal log
      curr_file = maze_assets_loc + "/" + file_path_str
      try:
        rows = read_file_to_list(curr_file, header=True, strip_trail=True)[1]
        clean_whispers = []
        for row_idx, row in enumerate(rows): 
          if not row: 
            logger.debug(f"Skipping empty row {row_idx+1} in {curr_file}") # Internal log
            continue
          if len(row) < 2: 
            logger.warning(f"Skipping malformed row {row_idx+1} (length < 2) in {curr_file}: {row}") # Internal log
            continue
          agent_name = row[0].strip() 
          whispers_str = row[1] 
          whispers = whispers_str.split(";") if whispers_str else [] 
          whispers = [whisper.strip() for whisper in whispers if whisper.strip()]
          if not agent_name:
            logger.warning(f"Skipping row {row_idx+1} with empty agent name in {curr_file}") # Internal log
            continue
          if whispers:
             for whisper in whispers: 
               clean_whispers += [[agent_name, whisper]]
             logger.debug(f"Parsed {len(whispers)} whispers for agent {agent_name} from row {row_idx+1}") # Internal log
          else:
            logger.debug(f"No whispers found for agent {agent_name} in row {row_idx+1}") # Internal log
        if clean_whispers:
          load_history_via_whisper(self.personas, clean_whispers)
          ret_str = f"历史记录已从 {curr_file} 加载。"
          logger.info(f"Successfully loaded history from {curr_file}, {len(clean_whispers)} whispers processed.") # Internal log
        else:
          ret_str = f"未从 {curr_file} 中找到有效的耳语内容可供加载。"
          logger.info(f"No valid whispers found in {curr_file} to load.") # Internal log
      except FileNotFoundError:
        logger.error(f"Error: History file not found at {curr_file}", exc_info=True) # User-facing via ret_str
        ret_str = f"错误：在 {curr_file} 未找到历史记录文件。"
      except IOError as e:
        logger.error(f"Error: Could not read history file at {curr_file}. IO Error: {e}", exc_info=True) # User-facing via ret_str
        ret_str = f"错误：无法读取位于 {curr_file} 的历史记录文件。"
      except IndexError as e: 
        logger.error(f"Error: Malformed history file or data at {curr_file}. Error: {e}", exc_info=True) # User-facing via ret_str
        ret_str = f"错误：位于 {curr_file} 的历史记录文件或数据格式错误。"
      except Exception as e:
        logger.error(f"An unexpected error occurred while loading history from {curr_file}: {e}", exc_info=True) # User-facing via ret_str
        ret_str = f"从 {curr_file} 加载历史记录时发生意外错误。"
    return ret_str

  def _handle_path_tester_command(self, sim_command, sim_folder):
    """Handles the 'start path tester mode' command."""
    should_break = False
    if sim_command.lower() == "start path tester mode": 
      logger.info("Command: Start Path Tester Mode.") # Internal log
      try:
        logger.info(f"Removing simulation folder: {sim_folder}") # Internal log
        shutil.rmtree(sim_folder) 
        logger.info(f"Successfully removed {sim_folder}") # Internal log
      except OSError as e:
        logger.error(f"Error: Could not remove simulation folder {sim_folder}. OS Error: {e}", exc_info=True) # Internal log
      self.start_path_tester_server()
      logger.info("Exiting after path tester mode.") # Internal log
      should_break = True # Path tester mode is blocking and requires restart
    return "", should_break
  # COMMAND HANDLER METHODS END HERE

  def open_server(self): 
    """
    Open up an interactive terminal prompt that lets you run the simulation 
    step by step and probe agent state. 

    INPUT 
      None
    OUTPUT
      None
    """
    logger.info("--- 启动 Reverie 交互式服务器 ---")
    logger.info("注意：此模拟包中的代理是计算结构，")
    logger.info("由生成式代理架构和大型语言模型驱动。我们")
    logger.info("澄清这些代理不具备类人的能动性、意识，")
    logger.info("以及独立的决策能力。\n---")

    sim_folder = f"{fs_storage}/{self.sim_code}"

    while True: 
      sim_command = input("请输入选项: ")
      sim_command = sim_command.strip().lower() # Normalize command
      logger.info(f"Received command: {sim_command}") # Internal log
      ret_str = ""
      should_break = False

      try: 
        if sim_command in ["f", "fin", "finish", "save and finish", "exit", "save"] or \
           sim_command.startswith("run"):
            ret_str, should_break = self._handle_lifecycle_commands(sim_command, sim_folder)

        elif sim_command == "start path tester mode":
            ret_str, should_break = self._handle_path_tester_command(sim_command, sim_folder)
            if should_break: # Path tester mode implies exit after it's done or if it's blocking
                break

        elif sim_command.startswith("print persona"):
            ret_str = self._handle_persona_info_commands(sim_command)
        
        elif sim_command.startswith("print all persona schedule"): # Specific case before generic "print persona"
            ret_str = self._handle_persona_info_commands(sim_command)

        elif sim_command.startswith("print current time") or \
             sim_command.startswith("print tile event") or \
             sim_command.startswith("print tile details"):
            ret_str = self._handle_world_info_commands(sim_command)

        elif sim_command.startswith("call --"):
            ret_str = self._handle_call_commands(sim_command)
            
        else:
            if sim_command: # Avoid logging for empty input
                logger.warning(f"Unknown command: {sim_command}") # User-facing via ret_str
                ret_str = f"未知命令: {sim_command}"

        if ret_str: 
          print(ret_str)
        
        if should_break:
          break

      except KeyError as e:
        logger.error(f"Error: Persona name not found: {e}. Please check the persona name and try again.", exc_info=True) # User-facing via print
        print(f"错误：未找到角色名：{e}。请检查角色名后重试。")
      except ValueError as e:
        logger.error(f"Error: Invalid value in command. {e}", exc_info=True) # User-facing via print
        print(f"错误：命令中包含无效值。{e}")
      except FileNotFoundError as e: 
        logger.error(f"Error: File not found. {e}", exc_info=True) # User-facing via print
        print(f"错误：文件未找到。{e}")
      except IOError as e: 
        logger.error(f"Error: Input/Output error. {e}", exc_info=True) # User-facing via print
        print(f"错误：输入/输出错误。{e}")
      except OSError as e: 
        logger.error(f"Error: Operating system error. {e}", exc_info=True) # User-facing via print
        print(f"错误：操作系统错误。{e}")
      except Exception as e:
        logger.error(f"An unexpected error occurred in open_server command processing: {sim_command}. Error: {e}", exc_info=True) # User-facing via print
        print (f"发生意外错误。请查看日志了解详情。命令: {sim_command}")
        pass


if __name__ == '__main__':
  # Configure logger for the main execution as well if needed, or rely on module-level config
  # Basic config for when the script is run directly, to ensure logs are seen if not imported
  if not logger.handlers: # Avoid adding handlers multiple times if already configured
      main_handler = logging.StreamHandler()
      main_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
      main_handler.setFormatter(main_formatter)
      logging.basicConfig(handlers=[main_handler], level=logging.INFO)

  # rs = ReverieServer("base_the_ville_isabella_maria_klaus", 
  #                    "July1_the_ville_isabella_maria_klaus-step-3-1")
  # rs = ReverieServer("July1_the_ville_isabella_maria_klaus-step-3-20", 
  #                    "July1_the_ville_isabella_maria_klaus-step-3-21")
  # rs.open_server()
  try:
    origin = input("请输入源模拟的名称: ").strip()
    target = input("请输入新模拟的名称: ").strip()

    logger.info(f"Initializing ReverieServer with origin: {origin}, target: {target}") # Internal log
    rs = ReverieServer(origin, target) # rs is the instance of ReverieServer
    rs.open_server()
  except Exception as e:
    logger.critical(f"A critical error occurred at the main execution level: {e}", exc_info=True) # User-facing via print
    print(f"发生严重错误: {e}。请查看日志获取更多详情。")




















































