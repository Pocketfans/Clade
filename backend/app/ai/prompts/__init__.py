"""Prompt templates for AI model capabilities."""

from .species import SPECIES_PROMPTS
from .narrative import NARRATIVE_PROMPTS
from .terrain import TERRAIN_EVOLUTION_PROMPT

# 合并所有 prompt 模板
PROMPT_TEMPLATES: dict[str, str] = {}
PROMPT_TEMPLATES.update(SPECIES_PROMPTS)
PROMPT_TEMPLATES.update(NARRATIVE_PROMPTS)
PROMPT_TEMPLATES["terrain_evolution"] = TERRAIN_EVOLUTION_PROMPT

__all__ = ["PROMPT_TEMPLATES", "SPECIES_PROMPTS", "NARRATIVE_PROMPTS", "TERRAIN_EVOLUTION_PROMPT"]

