"""Prompt templates for AI model capabilities."""

from .species import SPECIES_PROMPTS
from .narrative import NARRATIVE_PROMPTS
from .pressure_response import PRESSURE_RESPONSE_PROMPTS

# 合并所有 prompt 模板
PROMPT_TEMPLATES: dict[str, str] = {}
PROMPT_TEMPLATES.update(SPECIES_PROMPTS)
PROMPT_TEMPLATES.update(NARRATIVE_PROMPTS)
PROMPT_TEMPLATES.update(PRESSURE_RESPONSE_PROMPTS)

__all__ = ["PROMPT_TEMPLATES", "SPECIES_PROMPTS", "NARRATIVE_PROMPTS", "PRESSURE_RESPONSE_PROMPTS"]

