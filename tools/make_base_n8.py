"""
Build `base_the_ville_n8`: the eight-character starter town, derived from the 25-character base.
The live town offers three cast sizes (3, 8, 25) so a run can be sized to the machine at hand. The
three- and twenty-five-character starters ship with the upstream repository; this script derives
the eight-character one from the larger base by keeping the chosen cast's persona folders, listing
only them in the metadata, and filtering them out of the starting environment file. Everything
else (map, clock, step counter) is copied unchanged. Run from the repository root:

    python tools/make_base_n8.py

Idempotent: it rebuilds the folder from the 25-character base every time.
"""

import json
import os
import shutil

CAST = [
    "Isabella Rodriguez",
    "Klaus Mueller",
    "Maria Lopez",
    "Abigail Chen",
    "John Lin",
    "Eddy Lin",
    "Hailey Johnson",
    "Wolfgang Schulz",
]

STORAGE = "environment/frontend_server/storage"
SOURCE = f"{STORAGE}/base_the_ville_n25"
TARGET = f"{STORAGE}/base_the_ville_n8"


def main():
    if os.path.exists(TARGET):
        shutil.rmtree(TARGET)
    os.makedirs(f"{TARGET}/personas")
    shutil.copytree(f"{SOURCE}/reverie", f"{TARGET}/reverie")
    shutil.copytree(f"{SOURCE}/environment", f"{TARGET}/environment")
    for name in CAST:
        shutil.copytree(f"{SOURCE}/personas/{name}", f"{TARGET}/personas/{name}")

    meta_path = f"{TARGET}/reverie/meta.json"
    with open(meta_path) as f:
        meta = json.load(f)
    missing = [n for n in CAST if n not in meta["persona_names"]]
    if missing:
        raise SystemExit(f"not in the 25-character base: {missing}")
    meta["persona_names"] = CAST
    with open(meta_path, "w") as f:
        f.write(json.dumps(meta, indent=2))

    env_path = f"{TARGET}/environment/{meta['step']}.json"
    with open(env_path) as f:
        positions = json.load(f)
    with open(env_path, "w") as f:
        f.write(json.dumps({n: positions[n] for n in CAST}, indent=2))

    print(f"built {TARGET}: {len(CAST)} characters at step {meta['step']}")


if __name__ == "__main__":
    main()
