import unittest
from unittest.mock import patch, mock_open, MagicMock, call
import os
import sys
import json
import datetime

# Add the parent directory to sys.path to allow imports from reverie.backend_server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Attempt to pre-patch the problematic global variable at the earliest point.
# This is to address the NameError for 'openai_api_key' in gpt_structure.py during import.
patched_openai_api_key = False
try:
    # Ensure the module path exists for import
    import reverie.backend_server.persona.prompt_template.gpt_structure as gpt_module
    gpt_module.openai_api_key = "sk-dummy-test-key-early-set"
    # print("DEBUG: Successfully set openai_api_key in gpt_structure module.")
    patched_openai_api_key = True
except Exception as e:
    # print(f"DEBUG: Error setting openai_api_key directly: {e}")
    # Fallback to trying a patch if direct set fails or module not found yet.
    # This patch will only work if the module is loaded *after* this line.
    # The NameError happens *inside* gpt_structure.py, so the module must exist for patch to target it.
    pass

if not patched_openai_api_key:
    # If direct set failed, try to use patch. This is less likely to solve an import-time NameError
    # for the variable itself, but it's here as a fallback attempt.
    # The core issue is when gpt_structure.py is first executed.
    # print("DEBUG: Attempting patch for openai_api_key as direct set might have failed.")
    gpt_structure_patcher = patch('reverie.backend_server.persona.prompt_template.gpt_structure.openai_api_key', 'sk-dummy-via-patch', create=True)
    try:
        gpt_structure_patcher.start()
        # print("DEBUG: Started patch for openai_api_key.")
        patched_openai_api_key = True # Record that patch was attempted
    except Exception as e:
        # print(f"DEBUG: Failed to start patch for openai_api_key: {e}")
        pass


# Continue with other imports
import unittest
from unittest.mock import patch, mock_open, MagicMock, call # unittest.mock.patch is already imported by name 'patch'
import json # Already imported in ReverieServer, but good practice for clarity if used here
import datetime # Already imported in ReverieServer

# Now import the class to be tested
from reverie.backend_server.reverie import ReverieServer

# Mock global variables that ReverieServer expects
# These would normally be imported from global_methods or utils
# For testing, we define them or mock them as needed.
global_fs_storage = "mock_storage"
global_fs_temp_storage = "mock_temp_storage"
global_maze_assets_loc = "mock_maze_assets"

class TestReverieServer(unittest.TestCase):

    def setUp(self):
        """
        Set up for test methods. This method is called before each test method.
        It involves mocking all external dependencies of ReverieServer.__init__
        """
        self.fork_sim_code = "test_fork_sim"
        self.sim_code = "test_sim"

        # Mock meta.json data
        self.mock_reverie_meta = {
            "fork_sim_code": self.fork_sim_code,
            "start_date": "January 1, 2023",
            "curr_time": "January 1, 2023, 00:00:00",
            "sec_per_step": 60,
            "maze_name": "test_maze",
            "persona_names": ["Alice", "Bob"],
            "step": 0
        }

        # Mock initial environment file data
        self.mock_init_env = {
            "Alice": {"x": 10, "y": 20},
            "Bob": {"x": 15, "y": 25}
        }

        # Patch 'copyanything'
        self.patch_copyanything = patch('reverie.backend_server.reverie.copyanything')
        self.mock_copyanything = self.patch_copyanything.start()

        # Patch 'open' for meta.json and environment.json
        # Need to handle multiple open calls with different behaviors
        def mock_open_side_effect(filepath, *args, **kwargs):
            if f"{global_fs_storage}/{self.sim_code}/reverie/meta.json" in filepath and args[0] == 'r':
                return mock_open(read_data=json.dumps(self.mock_reverie_meta))()
            elif f"{global_fs_storage}/{self.sim_code}/reverie/meta.json" in filepath and args[0] == 'w':
                return mock_open()() # For writing meta
            elif f"{global_fs_storage}/{self.sim_code}/environment/{self.mock_reverie_meta['step']}.json" in filepath:
                return mock_open(read_data=json.dumps(self.mock_init_env))()
            elif f"{global_fs_temp_storage}/curr_sim_code.json" in filepath and args[0] == 'w':
                return mock_open()()
            elif f"{global_fs_temp_storage}/curr_step.json" in filepath and args[0] == 'w':
                return mock_open()()
            # Fallback for other open calls if any
            return mock_open()()

        self.patch_open = patch('builtins.open', side_effect=mock_open_side_effect)
        self.mock_builtin_open = self.patch_open.start()
        
        # Patch json.load and json.dump if necessary, though mock_open handles read_data for load
        self.patch_json_dump = patch('json.dump')
        self.mock_json_dump = self.patch_json_dump.start()

        # Patch Maze class
        self.patch_maze = patch('reverie.backend_server.reverie.Maze')
        self.MockMazeClass = self.patch_maze.start()
        self.mock_maze_instance = self.MockMazeClass.return_value
        self.mock_maze_instance.access_tile.return_value = {"events": []} # Default
        self.mock_maze_instance.tiles = [[{"events": set()} for _ in range(50)] for _ in range(50)] # Mock a basic tile structure

        # Patch Persona class
        self.patch_persona = patch('reverie.backend_server.reverie.Persona')
        self.MockPersonaClass = self.patch_persona.start()
        self.mock_alice_persona = MagicMock()
        self.mock_alice_persona.name = "Alice"
        self.mock_alice_persona.scratch.get_curr_event_and_desc.return_value = ("Alice_event", "Alice_desc")
        self.mock_bob_persona = MagicMock()
        self.mock_bob_persona.name = "Bob"
        self.mock_bob_persona.scratch.get_curr_event_and_desc.return_value = ("Bob_event", "Bob_desc")
        
        # Side effect for Persona instantiation
        def persona_side_effect(name, folder):
            if name == "Alice":
                return self.mock_alice_persona
            elif name == "Bob":
                return self.mock_bob_persona
            return MagicMock()
        self.MockPersonaClass.side_effect = persona_side_effect

        # Patch logger
        self.patch_logger = patch('reverie.backend_server.reverie.logger')
        self.mock_logger = self.patch_logger.start()

        # Patch shutil.rmtree
        self.patch_shutil_rmtree = patch('shutil.rmtree')
        self.mock_shutil_rmtree = self.patch_shutil_rmtree.start()
        
        # Patch global storage variables as they are used to construct paths
        self.patch_fs_storage = patch('reverie.backend_server.reverie.fs_storage', global_fs_storage)
        self.mock_fs_storage = self.patch_fs_storage.start()

        self.patch_fs_temp_storage = patch('reverie.backend_server.reverie.fs_temp_storage', global_fs_temp_storage)
        self.mock_fs_temp_storage = self.patch_fs_temp_storage.start()

        self.patch_maze_assets_loc = patch('reverie.backend_server.reverie.maze_assets_loc', global_maze_assets_loc)
        self.mock_maze_assets_loc = self.patch_maze_assets_loc.start()
        
        # Patch datetime.datetime.strptime
        self.patch_strptime = patch('datetime.datetime')
        self.mock_datetime = self.patch_strptime.start()
        self.mock_datetime.strptime.return_value = datetime.datetime(2023, 1, 1, 0, 0, 0)
        self.mock_datetime.now.return_value = datetime.datetime(2023, 1, 1, 0, 0, 0) # If needed
        self.mock_datetime.timedelta = datetime.timedelta # Use real timedelta

        # Patch time.sleep
        self.patch_time_sleep = patch('time.sleep', return_value=None)
        self.mock_time_sleep = self.patch_time_sleep.start()

        # Patch read_file_to_list (assuming it's in utils or global_methods)
        # This needs to point to the correct module where read_file_to_list is defined.
        # Assuming it's in 'reverie.backend_server.reverie' for now if it's a global method there
        # Or 'reverie.backend_server.utils.read_file_to_list' if it's in utils.py
        # For now, let's assume it's available in reverie.py's scope
        self.patch_read_file = patch('reverie.backend_server.reverie.read_file_to_list')
        self.mock_read_file_to_list = self.patch_read_file.start()

        # Patch load_history_via_whisper
        self.patch_load_history = patch('reverie.backend_server.reverie.load_history_via_whisper')
        self.mock_load_history_via_whisper = self.patch_load_history.start()

        # Patch check_if_file_exists, assuming it's available in reverie.py's scope
        # (e.g., imported from utils or global_methods)
        self.patch_check_file = patch('reverie.backend_server.reverie.check_if_file_exists')
        self.mock_check_if_file_exists = self.patch_check_file.start()
        # Default to file not existing, tests can change this per case
        self.mock_check_if_file_exists.return_value = False

        # Patch openai_api_key in gpt_structure.py to prevent NameError during import chain
        # This needs to be active *before* ReverieServer and its imports are fully processed.
        # One way is to patch it in the module where it's accessed.
        self.patch_openai_api_key = patch('reverie.backend_server.persona.prompt_template.gpt_structure.openai_api_key', 'sk-testkey')
        # Start it early, before ReverieServer is potentially re-imported or its modules fully loaded by tests.
        # However, setUp runs *after* the test module (and ReverieServer) is imported.
        # This patch is tricky due to import-time error.
        # A better place might be at the class level or module level of the test file.
        # For now, let's try starting it here. If it fails, will move to class level.
        try:
            self.mock_openai_api_key = self.patch_openai_api_key.start()
        except AttributeError: # Handle if already started or module not loaded yet in a way patch expects
             # This can happen if tests are run in a way that gpt_structure isn't fully on sys.modules yet for patching
             # For now, we'll assume this will work or adjust.
             pass


        # Instantiate the server
        # We need to ensure that all global variables like fs_storage are patched *before* this.
        self.server = ReverieServer(self.fork_sim_code, self.sim_code)
        
        # Clear mock calls from setup to have clean slate for each test
        self.mock_logger.reset_mock()
        self.mock_copyanything.reset_mock()
        self.mock_builtin_open.reset_mock()
        self.MockMazeClass.reset_mock()
        self.MockPersonaClass.reset_mock()
        self.mock_shutil_rmtree.reset_mock()
        self.mock_json_dump.reset_mock()
        self.mock_load_history_via_whisper.reset_mock()
        self.mock_read_file_to_list.reset_mock()
        self.mock_check_if_file_exists.reset_mock()


    def tearDown(self):
        """
        Clean up after test methods. This method is called after each test method.
        """
        self.patch_copyanything.stop()
        self.patch_open.stop()
        self.patch_json_dump.stop()
        self.patch_maze.stop()
        self.patch_persona.stop()
        self.patch_logger.stop()
        self.patch_shutil_rmtree.stop()
        self.patch_fs_storage.stop()
        self.patch_fs_temp_storage.stop()
        self.patch_maze_assets_loc.stop()
        self.patch_strptime.stop()
        self.patch_time_sleep.stop()
        self.patch_read_file.stop()
        self.patch_load_history.stop()
        self.patch_check_file.stop()
        # Stop the openai_api_key patch if it was started
        if hasattr(self, 'mock_openai_api_key') and self.patch_openai_api_key.is_started:
            self.patch_openai_api_key.stop()

    # --- Test _handle_lifecycle_commands ---
    def test_handle_lifecycle_fin_command(self):
        self.server.save = MagicMock()
        ret_str, should_break = self.server._handle_lifecycle_commands("fin", self.server.sim_code)
        self.server.save.assert_called_once()
        self.mock_logger.info.assert_any_call("Simulation saved. Exiting.")
        self.assertEqual(ret_str, "")
        self.assertTrue(should_break)

    def test_handle_lifecycle_exit_command(self):
        ret_str, should_break = self.server._handle_lifecycle_commands("exit", f"{global_fs_storage}/{self.server.sim_code}")
        self.mock_shutil_rmtree.assert_called_once_with(f"{global_fs_storage}/{self.server.sim_code}")
        self.mock_logger.info.assert_any_call("Exiting.")
        self.assertEqual(ret_str, "")
        self.assertTrue(should_break)

    def test_handle_lifecycle_save_command(self):
        self.server.save = MagicMock()
        ret_str, should_break = self.server._handle_lifecycle_commands("save", self.server.sim_code)
        self.server.save.assert_called_once()
        self.assertEqual(ret_str, "Simulation progress saved.")
        self.assertFalse(should_break)

    def test_handle_lifecycle_run_command_valid(self):
        self.server.start_server = MagicMock()
        ret_str, should_break = self.server._handle_lifecycle_commands("run 100", self.server.sim_code)
        self.server.start_server.assert_called_once_with(100)
        self.assertEqual(ret_str, "Finished running 100 steps.")
        self.assertFalse(should_break)

    def test_handle_lifecycle_run_command_invalid_steps(self):
        self.server.start_server = MagicMock()
        ret_str, should_break = self.server._handle_lifecycle_commands("run abc", self.server.sim_code)
        self.server.start_server.assert_not_called()
        self.assertEqual(ret_str, "Error: Invalid number of steps. Please provide an integer.")
        self.mock_logger.error.assert_called_with(
            "Error: Invalid number of steps. Please provide an integer. Command: 'run abc'",
            exc_info=True
        )
        self.assertFalse(should_break)

    def test_handle_lifecycle_run_command_missing_steps(self):
        self.server.start_server = MagicMock()
        ret_str, should_break = self.server._handle_lifecycle_commands("run", self.server.sim_code)
        self.server.start_server.assert_not_called()
        self.assertEqual(ret_str, "Error: Number of steps not specified.")
        self.mock_logger.error.assert_called_with(
            "Error: Number of steps not specified. Command: 'run'"
        ) # exc_info might not be True here based on current code in handler
        self.assertFalse(should_break)

    # --- Test _handle_persona_info_commands ---
    def test_handle_persona_info_schedule_existing_persona(self):
        self.mock_alice_persona.scratch.get_str_daily_schedule_summary.return_value = "Alice's schedule"
        ret_str = self.server._handle_persona_info_commands("print persona schedule Alice")
        self.assertEqual(ret_str, "Alice's schedule")
        self.mock_alice_persona.scratch.get_str_daily_schedule_summary.assert_called_once()

    def test_handle_persona_info_schedule_non_existing_persona(self):
        ret_str = self.server._handle_persona_info_commands("print persona schedule Charlie")
        self.assertEqual(ret_str, "Error: Persona 'Charlie' not found.")
        self.mock_logger.warning.assert_called_with("Persona 'Charlie' not found for 'print persona schedule'.")

    def test_handle_persona_info_all_schedules(self):
        self.mock_alice_persona.scratch.get_str_daily_schedule_summary.return_value = "Alice's schedule"
        self.mock_bob_persona.scratch.get_str_daily_schedule_summary.return_value = "Bob's schedule"
        ret_str = self.server._handle_persona_info_commands("print all persona schedule")
        self.assertIn("Alice\nAlice's schedule\n---\n", ret_str)
        self.assertIn("Bob\nBob's schedule\n---\n", ret_str)

    def test_handle_persona_info_spatial_memory_existing_persona(self):
        self.mock_alice_persona.s_mem.print_tree = MagicMock()
        ret_str = self.server._handle_persona_info_commands("print persona spatial memory Alice")
        self.assertEqual(ret_str, "Spatial memory for Alice printed above.")
        self.mock_alice_persona.s_mem.print_tree.assert_called_once()

    def test_handle_persona_info_hourly_org_schedule_existing_persona(self):
        self.mock_alice_persona.scratch.get_str_daily_schedule_hourly_org_summary.return_value = "Alice's hourly schedule"
        ret_str = self.server._handle_persona_info_commands("print hourly org persona schedule Alice")
        self.assertEqual(ret_str, "Alice's hourly schedule")
        self.mock_alice_persona.scratch.get_str_daily_schedule_hourly_org_summary.assert_called_once()

    def test_handle_persona_info_current_tile_non_existing_persona(self):
        ret_str = self.server._handle_persona_info_commands("print persona current tile Charlie")
        self.assertEqual(ret_str, "Error: Persona 'Charlie' not found.")
        self.mock_logger.warning.assert_called_with("Persona 'Charlie' not found for 'print persona current tile'.")
        
    def test_handle_persona_info_chatting_with_buffer_existing_persona(self):
        self.mock_bob_persona.scratch.chatting_with_buffer = {"Alice": 5}
        ret_str = self.server._handle_persona_info_commands("print persona chatting with buffer Bob")
        self.assertEqual(ret_str, "Alice: 5\n")

    def test_handle_persona_info_associative_memory_event_non_existing(self):
        ret_str = self.server._handle_persona_info_commands("print persona associative memory (event) Charlie")
        self.assertEqual(ret_str, "Error: Persona 'Charlie' not found.")
        self.mock_logger.warning.assert_called_with("Persona 'Charlie' not found for 'print persona associative memory (event)'.")

    def test_handle_persona_info_associative_memory_thought_existing(self):
        self.mock_alice_persona.a_mem.get_str_seq_thoughts.return_value = "Alice's thoughts"
        ret_str = self.server._handle_persona_info_commands("print persona associative memory (thought) Alice")
        self.assertEqual(ret_str, "Alice\nAlice's thoughts") # Assumes self.mock_alice_persona.name is "Alice"
        self.mock_alice_persona.a_mem.get_str_seq_thoughts.assert_called_once()

    def test_handle_persona_info_associative_memory_chat_existing(self):
        self.mock_bob_persona.a_mem.get_str_seq_chats.return_value = "Bob's chats"
        ret_str = self.server._handle_persona_info_commands("print persona associative memory (chat) Bob")
        self.assertEqual(ret_str, "Bob\nBob's chats") # Assumes self.mock_bob_persona.name is "Bob"
        self.mock_bob_persona.a_mem.get_str_seq_chats.assert_called_once()


    # --- Test _handle_world_info_commands ---
    def test_handle_world_info_current_time(self):
        # server.curr_time is datetime(2023,1,1) and server.step is 0 from setup
        expected_time_str = datetime.datetime(2023, 1, 1, 0, 0, 0).strftime("%B %d, %Y, %H:%M:%S")
        expected_ret_str = f"{expected_time_str}\nsteps: 0"
        ret_str = self.server._handle_world_info_commands("print current time")
        self.assertEqual(ret_str, expected_ret_str)

    def test_handle_world_info_tile_event_valid_coords(self):
        self.server.maze.access_tile.return_value = {"events": ["event1", "event2"]}
        ret_str = self.server._handle_world_info_commands("print tile event 10, 20")
        self.server.maze.access_tile.assert_called_once_with([10, 20])
        self.assertEqual(ret_str, "event1\nevent2\n")

    def test_handle_world_info_tile_event_invalid_coords_format(self):
        ret_str = self.server._handle_world_info_commands("print tile event 10_20") # Normalized to lowercase in open_server
        self.assertEqual(ret_str, "Error: Invalid coordinates. Expected format: X, Y. Received: 10_20")
        self.mock_logger.error.assert_called_with(
            "Error: Invalid coordinates for 'print tile event'. Expected format: X, Y. Received: 10_20",
            exc_info=True
        )
    
    def test_handle_world_info_tile_event_incomplete_coords(self):
        ret_str = self.server._handle_world_info_commands("print tile event 10") # Normalized
        self.assertEqual(ret_str, "Error: Invalid coordinates. Expected format: X, Y. Received: 10")
        self.mock_logger.error.assert_called_with(
            "Error: Invalid coordinates for 'print tile event'. Expected format: X, Y. Received: 10",
            exc_info=True 
        )

    def test_handle_world_info_tile_details_valid_coords(self):
        self.server.maze.access_tile.return_value = {"name": "TileA", "state": "active"}
        ret_str = self.server._handle_world_info_commands("print tile details 30, 40")
        self.server.maze.access_tile.assert_called_once_with([30, 40])
        self.assertIn("name: TileA\n", ret_str)
        self.assertIn("state: active\n", ret_str)

    def test_handle_world_info_tile_details_invalid_coords(self):
        ret_str = self.server._handle_world_info_commands("print tile details invalid")
        self.assertEqual(ret_str, "Error: Invalid coordinates. Expected format: X, Y. Received: invalid")
        self.mock_logger.error.assert_called_with(
            "Error: Invalid coordinates for 'print tile details'. Expected format: X, Y. Received: invalid",
            exc_info=True
        )

    # --- Test _handle_call_commands ---
    def test_handle_call_analysis_existing_persona(self):
        self.mock_alice_persona.open_convo_session = MagicMock()
        ret_str = self.server._handle_call_commands("call -- analysis Alice")
        self.mock_alice_persona.open_convo_session.assert_called_once_with("analysis")
        self.assertEqual(ret_str, "Conversation session 'analysis' opened for Alice.")

    def test_handle_call_analysis_non_existing_persona(self):
        ret_str = self.server._handle_call_commands("call -- analysis Charlie") # Normalized
        self.assertEqual(ret_str, "Error: Persona 'Charlie' not found.")
        self.mock_logger.warning.assert_called_with("Persona 'Charlie' not found for 'call -- analysis'.")

    def test_handle_call_load_history_valid_file(self):
        self.mock_read_file_to_list.return_value = (
            ["header1", "header2"], # Mock header row
            [["Alice", "whisper1;whisper2"], ["Bob", "whisper3"]] # Mock data rows
        )
        ret_str = self.server._handle_call_commands("call -- load history test_history.csv") # Normalized
        
        expected_clean_whispers = [
            ["Alice", "whisper1"],
            ["Alice", "whisper2"],
            ["Bob", "whisper3"]
        ]
        self.mock_load_history_via_whisper.assert_called_once_with(self.server.personas, expected_clean_whispers)
        self.assertEqual(ret_str, f"History loaded from {global_maze_assets_loc}/test_history.csv.")
        self.mock_logger.info.assert_any_call(f"Successfully loaded history from {global_maze_assets_loc}/test_history.csv, 3 whispers processed.")

    def test_handle_call_load_history_file_not_found(self):
        self.mock_read_file_to_list.side_effect = FileNotFoundError("File not found")
        ret_str = self.server._handle_call_commands("call -- load history non_existent.csv") # Normalized
        self.assertEqual(ret_str, f"Error: History file not found at {global_maze_assets_loc}/non_existent.csv")
        self.mock_logger.error.assert_called_with(
            f"Error: History file not found at {global_maze_assets_loc}/non_existent.csv",
            exc_info=True
        )
        
    def test_handle_call_load_history_io_error(self):
        self.mock_read_file_to_list.side_effect = IOError("Cannot read file")
        ret_str = self.server._handle_call_commands("call -- load history bad_perms.csv") # Normalized
        self.assertEqual(ret_str, f"Error: Could not read history file at {global_maze_assets_loc}/bad_perms.csv.")
        self.mock_logger.error.assert_called_with(
            f"Error: Could not read history file at {global_maze_assets_loc}/bad_perms.csv. IO Error: Cannot read file",
            exc_info=True
        )

    def test_handle_call_load_history_malformed_row_index_error(self):
        # Simulate a row that's too short, causing IndexError when accessing row[1]
        self.mock_read_file_to_list.return_value = (
            ["header"],
            [["Alice"]] # Malformed row, missing whisper string
        )
        ret_str = self.server._handle_call_commands("call -- load history malformed.csv") # Normalized
        self.assertEqual(ret_str, f"Error: Malformed history file or data at {global_maze_assets_loc}/malformed.csv.")
        self.mock_logger.error.assert_any_call( # Check if any error log matches this, as exact error details might vary
            f"Error: Malformed history file or data at {global_maze_assets_loc}/malformed.csv.",
            exc_info=True
        )


    # --- Test _handle_path_tester_command ---
    def test_handle_path_tester_command(self):
        self.server.start_path_tester_server = MagicMock()
        sim_folder_path = f"{global_fs_storage}/{self.sim_code}"
        
        ret_str, should_break = self.server._handle_path_tester_command("start path tester mode", sim_folder_path)
        
        self.mock_shutil_rmtree.assert_called_once_with(sim_folder_path)
        self.server.start_path_tester_server.assert_called_once()
        self.assertTrue(should_break)
        self.assertEqual(ret_str, "") # Path tester command doesn't return a string to print
        self.mock_logger.info.assert_any_call("Exiting after path tester mode.")

    # --- Test open_server main loop dispatch ---
    @patch('builtins.input', side_effect=["save", "fin"]) # Simulate user inputs
    def test_open_server_dispatch_save_and_fin(self, mock_input):
        # Mock handler methods to check if they are called
        self.server._handle_lifecycle_commands = MagicMock(side_effect=[
            ("Simulation progress saved.", False), # for "save"
            ("", True)  # for "fin"
        ])
        
        # No need to catch SystemExit if loop breaks normally
        self.server.open_server()

        self.server._handle_lifecycle_commands.assert_any_call("save", f"{global_fs_storage}/{self.sim_code}")
        self.server._handle_lifecycle_commands.assert_any_call("fin", f"{global_fs_storage}/{self.sim_code}")
        self.assertEqual(self.server._handle_lifecycle_commands.call_count, 2)
        # Check that print was called with the ret_str from "save"
        # This requires patching 'print' or capturing stdout, which can be complex.
        # For now, we trust ret_str is handled by open_server's print call.

    @patch('builtins.input', side_effect=["print persona schedule Alice", "unknown command", "f"])
    def test_open_server_dispatch_persona_unknown_fin(self, mock_input):
        self.server._handle_persona_info_commands = MagicMock(return_value="Alice's schedule")
        self.server._handle_lifecycle_commands = MagicMock(return_value=("", True)) # for "f" (fin)

        self.server.open_server()

        self.server._handle_persona_info_commands.assert_called_once_with("print persona schedule alice") # Normalized
        self.mock_logger.warning.assert_called_with("Unknown command: unknown command")
        self.server._handle_lifecycle_commands.assert_called_once_with("f", f"{global_fs_storage}/{self.sim_code}")
        
if __name__ == '__main__':
    # Need to redefine these globals here if running the test file directly
    # or ensure they are available in the scope where ReverieServer is imported
# This is a bit of a hack for the direct execution environment.
# Ideally, tests are run by a test runner that handles paths correctly.
import reverie.backend_server.reverie as reverie_module_for_globals

# Global mocks for fs_storage etc. for when ReverieServer module is loaded.
reverie_module_for_globals.fs_storage = global_fs_storage
reverie_module_for_globals.fs_temp_storage = global_fs_temp_storage
reverie_module_for_globals.maze_assets_loc = global_maze_assets_loc

# If patch was started, ensure it's stopped
def tearDownModule():
    if patched_openai_api_key and 'gpt_structure_patcher' in globals() and gpt_structure_patcher.is_started:
        # print("DEBUG: Stopping patch for openai_api_key.")
        gpt_structure_patcher.stop()

    unittest.main(argv=['first-arg-is-ignored'], exit=False)
