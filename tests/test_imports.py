"""
Every module the simulation and the evaluation load, imported once.
"""

import importlib

import pytest

BACKEND_MODULES = [
    "global_methods",
    "llm_trace",
    "maze",
    "path_finder",
    "reverie",
    "run_livetown",
    "persona.persona",
    "persona.cognitive_modules.perceive",
    "persona.cognitive_modules.retrieve",
    "persona.cognitive_modules.plan",
    "persona.cognitive_modules.reflect",
    "persona.cognitive_modules.execute",
    "persona.cognitive_modules.converse",
    "persona.memory_structures.associative_memory",
    "persona.memory_structures.scratch",
    "persona.memory_structures.spatial_memory",
    "persona.prompt_template.gpt_structure",
    "persona.prompt_template.run_gpt_prompt",
    "persona.prompt_template.print_prompt",
    "memory_ext.retention",
    "memory_ext.retrieval",
    "memory_ext.longevity",
    "memory_ext.persona",
    "world_ext.needs",
    "world_ext.emotion",
    "world_ext.relationships",
    "world_ext.snapshot",
]

EVALUATION_MODULES = [
    "evaluation.administer",
    "evaluation.probes",
    "evaluation.score",
    "evaluation.persona_score",
    "evaluation.agreement",
    "evaluation.run",
]


@pytest.mark.parametrize("name", BACKEND_MODULES + EVALUATION_MODULES)
def test_module_imports(name):
    importlib.import_module(name)
