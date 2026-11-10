"""ComfyUI's UI format → its API format (SPEC 6.4.4: the library stores the API format).

What people save from ComfyUI (and what its own workflow list holds) is the UI format: nodes
with ``widgets_values`` in screen order, links in a separate table. The API format names every
input. The widget names come from the running ComfyUI's ``/object_info``: a node's required
then optional inputs, in order, are widgets when their type is a value type or a list of
choices; links are everything else.

Handled the way ComfyUI's own "Export (API)" does:
- muted nodes (mode 2) are left out; bypassed nodes (mode 4) pass their input of the same type
  straight through; ``Reroute`` passes its one input through;
- ``PrimitiveNode`` puts its value into the inputs it feeds;
- a seed's "control after generate" value (``fixed`` / ``randomize`` …) is not an input;
- notes are dropped.

A node class ComfyUI does not know cannot be converted (its widget names are unknown):
``ConvertError`` lists them, and the user installs the pack or exports the API format.
Subgraphs (newer front ends) are not converted either.
"""

from __future__ import annotations

from typing import Any

VALUE_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
CONTROL_VALUES = {"fixed", "increment", "decrement", "randomize"}
UI_ONLY = {"Note", "MarkdownNote", "PrimitiveNode", "Reroute"}
MUTED, BYPASSED = 2, 4


class ConvertError(ValueError):
    def __init__(self, code: str, classes: list[str] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.classes = classes or []


def is_ui_format(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("nodes"), list) and "links" in data


def _widget_names(info: dict[str, Any]) -> list[tuple[str, bool]]:
    """Widget inputs in screen order, each with whether it may have a control value after it."""
    out = []
    spec = info.get("input") or {}
    for group in ("required", "optional"):
        for name, entry in (spec.get(group) or {}).items():
            kind = entry[0] if isinstance(entry, list) and entry else entry
            opts = entry[1] if isinstance(entry, list) and len(entry) > 1 else {}
            opts = opts if isinstance(opts, dict) else {}
            if opts.get("forceInput"):
                continue
            if isinstance(kind, list) or kind in VALUE_TYPES:
                control = kind == "INT" and (
                    opts.get("control_after_generate") or name in ("seed", "noise_seed")
                )
                out.append((name, bool(control)))
    return out


def ui_to_api(ui: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    if (ui.get("definitions") or {}).get("subgraphs"):
        raise ConvertError("workflow_subgraph")
    nodes = {int(n["id"]): n for n in ui["nodes"]}
    links = {int(lk[0]): (int(lk[1]), int(lk[2]), lk[5] if len(lk) > 5 else None)
             for lk in ui.get("links") or [] if isinstance(lk, list)}  # fmt: skip
    unknown = sorted({str(n["type"]) for n in nodes.values()} - UI_ONLY - set(object_info))
    if unknown:
        raise ConvertError("workflow_unknown_nodes", unknown)

    def source(link_id: int) -> Any:
        """Where a link really comes from: [node id, slot], or a primitive's value."""
        seen = 0
        while seen < 64:
            seen += 1
            from_id, slot, kind = links[link_id]
            node = nodes[from_id]
            if node["type"] == "PrimitiveNode":
                values = node.get("widgets_values") or [None]
                return values[0]
            passthrough = node["type"] == "Reroute" or node.get("mode") == BYPASSED
            if not passthrough:
                return [str(from_id), slot]
            ins = [i for i in node.get("inputs") or [] if i.get("link") is not None]
            same = [i for i in ins if kind is None or i.get("type") == kind or i.get("type") == "*"]
            nxt = (same or ins)[:1]
            if not nxt:
                return None
            link_id = int(nxt[0]["link"])
        return None

    api: dict[str, Any] = {}
    for node_id, node in sorted(nodes.items()):
        cls = str(node["type"])
        if cls in UI_ONLY or node.get("mode") in (MUTED, BYPASSED):
            continue
        info = object_info[cls]
        inputs: dict[str, Any] = {}
        values = node.get("widgets_values")
        if isinstance(values, dict):
            inputs.update({k: v for k, v in values.items() if not isinstance(v, dict)})
        elif isinstance(values, list):
            vals = list(values)
            for name, control in _widget_names(info):
                if not vals:
                    break
                inputs[name] = vals.pop(0)
                if control and vals and vals[0] in CONTROL_VALUES:
                    vals.pop(0)
        for slot in node.get("inputs") or []:
            if slot.get("link") is None:
                continue
            value = source(int(slot["link"]))
            if value is not None:
                inputs[str(slot["name"])] = value
        title = node.get("title") or info.get("display_name") or cls
        api[str(node_id)] = {"inputs": inputs, "class_type": cls, "_meta": {"title": title}}
    # A link from a left-out node (muted, unresolvable) would make ComfyUI reject the prompt.
    for node in api.values():
        for name in [
            k
            for k, v in node["inputs"].items()
            if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int) and v[0] not in api
        ]:
            del node["inputs"][name]
    return api
