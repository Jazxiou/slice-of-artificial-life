"""
Shared test setup.
The simulation is written to be started from inside `reverie/backend_server/` with flat imports
(`from utils import *`, `import llm_trace`), so the tests put that directory on the import path rather
than restructuring the package to suit them.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "reverie" / "backend_server"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The repository root too, so `evaluation` imports as a package. It is deliberately not inside
# `reverie/backend_server`: the batteries are instruments applied *to* the simulation, and keeping them
# outside it is a reminder that they never run as part of one.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# `utils.py` is gitignored, because it can hold a real API key, so a fresh checkout has only the
# committed template. The tests need importable configuration and nothing else, so when the real file
# is absent the template is loaded under the name `utils`. Nothing is written to disk: running an
# actual simulation still needs the documented `cp utils_template.py utils.py` step. The template
# ships with every flag on (the town configuration), so the suite never assumes a default: every
# test pins the flags it depends on, and the frozen-baseline tests force theirs off explicitly.
if not (BACKEND / "utils.py").exists():
    spec = importlib.util.spec_from_file_location("utils", BACKEND / "utils_template.py")
    utils = importlib.util.module_from_spec(spec)
    sys.modules["utils"] = utils
    spec.loader.exec_module(utils)
