"""DramaStudio nodes for ComfyUI (AI Drama Studio, SPEC 6.4.3 and 14.2).

Installed by the studio's setup into ``ComfyUI/custom_nodes/comfyui-dramastudio``.
"""

from .nodes import NODES

NODE_CLASS_MAPPINGS = {name: cls for name, (cls, _title) in NODES.items()}
NODE_DISPLAY_NAME_MAPPINGS = {name: title for name, (_cls, title) in NODES.items()}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
