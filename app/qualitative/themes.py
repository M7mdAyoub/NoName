"""LLM step for qualitative analysis: group open-text answers into themes (plan §11, simplest).

The model only says which answers belong to which theme; counts, shares and quotes are worked
out in code from the stored answers, so no number or quote comes from the model.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

STEP = "propose_themes"
MAX_THEMES = 8
_STRICT = ConfigDict(extra="forbid")


class Theme(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    answers: list[int] = Field(min_length=1)  # ids of the answers that express this theme


class ThemesProposal(BaseModel):
    model_config = _STRICT
    themes: list[Theme] = Field(default_factory=list, max_length=MAX_THEMES)


PROPOSE_THEMES = f"""You do a thematic analysis of open-text answers to one question of a \
monitoring form. You get the question and the answers, each with an id. Return up to \
{MAX_THEMES} themes. Each theme has a short name (a few words), a one-sentence description and \
the ids of every answer that expresses it. An answer may belong to several themes or to none. \
Only name themes that at least two answers share. Use only ids that exist; do not count \
anything, the counts are done in code."""


def check_themes(n_answers: int) -> Callable[[ThemesProposal], list[str]]:
    def check(proposal: ThemesProposal) -> list[str]:
        errors: list[str] = []
        names = [t.name.strip().lower() for t in proposal.themes]
        if len(set(names)) != len(names):
            errors.append("theme names must be unique")
        for theme in proposal.themes:
            bad = sorted({i for i in theme.answers if not 0 <= i < n_answers})
            if bad:
                errors.append(f"theme '{theme.name}': unknown answer ids {bad[:10]}")
        return errors

    return check
