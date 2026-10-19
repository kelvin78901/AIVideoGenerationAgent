"""Two-layer prompts (SPEC 8).

- **Intent**: the user's own words, model independent (``product_version.intent``).
- **Compiled**: the instructions sent to a model, rendered from
  ``templates/<component>/<family>.j2`` (``default.j2`` when the family has none). It holds only
  instructions; the data a run reads (novel paragraphs, bible …) is appended as titled blocks at
  send time, so a hand-edited compiled layer never drops or freezes the data.

The full text actually sent is stored with each version as a blob (``files[]`` role
``prompt``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

TEMPLATES = Path(__file__).resolve().parent / "templates"
LANGS = ("zh-CN", "en")


@dataclass(frozen=True)
class Block:
    """One titled data block after the instructions, e.g. ``原文`` with numbered paragraphs."""

    title: str
    text: str


def model_family(model_key: str) -> str:
    """``deepseek/v4-pro`` → ``deepseek``: templates may differ per provider family."""
    return model_key.split("/", 1)[0] if "/" in model_key else model_key


class PromptCompiler:
    def __init__(self, roots: Sequence[Path] | None = None) -> None:
        self.roots = [Path(r) for r in (roots or [TEMPLATES])]
        self._env = Environment(
            loader=FileSystemLoader([str(r) for r in self.roots]),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def has(self, component_id: str) -> bool:
        return any((root / component_id / "default.j2").is_file() for root in self.roots)

    def compile(self, component_id: str, intent: str, model_key: str, **context: Any) -> str:
        family = model_family(model_key)
        try:
            template = self._env.select_template(
                [f"{component_id}/{family}.j2", f"{component_id}/default.j2"]
            )
        except TemplateNotFound:
            raise KeyError(f"no prompt template for {component_id}") from None
        text = template.render(intent=intent.strip(), model_key=model_key, family=family, **context)
        return text.strip()

    def default_intent(self, component_id: str, lang: str = "zh-CN") -> str:
        """The intent a product starts with, in the series' language."""
        for name in (f"intent.{lang}.txt", "intent.zh-CN.txt"):
            for root in self.roots:
                path = root / component_id / name
                if path.is_file():
                    return path.read_text(encoding="utf-8").strip()
        return ""

    def messages(self, compiled: str, blocks: Sequence[Block]) -> list[dict[str, Any]]:
        """Instructions as the system message, the data blocks as the user message."""
        data = "\n\n".join(f"[{b.title}]\n{b.text.strip()}" for b in blocks)
        out: list[dict[str, Any]] = [{"role": "system", "content": compiled}]
        if data:
            out.append({"role": "user", "content": data})
        return out

    def render(self, name: str, **context: Any) -> str:
        """A fixed internal prompt (``<component>/<name>.j2``), e.g. a second call of a run."""
        return self._env.get_template(name).render(**context).strip()

    def fix_json(self, errors: str) -> str:
        """The follow-up that asks once for corrected JSON after a validation failure."""
        return self._env.get_template("_shared/fix_json.j2").render(errors=errors).strip()

    @staticmethod
    def full_text(messages: Sequence[dict[str, Any]]) -> str:
        """What was sent, for the version's ``prompt`` file."""
        return "\n\n".join(f"### {m['role']}\n{m['content']}" for m in messages)
