import importlib
import pathlib
import json
from typing import Dict, Any, List

BASE_DIR = pathlib.Path(__file__).parent

# Load registry once
with open(BASE_DIR / "toolregistry.json", "r") as f:
    TOOL_REGISTRY = json.load(f)


class ToolLoader:
    def __init__(self):
        self.tools: Dict[str, Any] = {}

    def load_tools(self):
        """Dynamically import tool classes defined in toolregistry.json"""
        for tool in TOOL_REGISTRY:
            fn = tool["function"]
            module_name = fn.get("module")
            class_name = fn.get("class")

            try:
                module = importlib.import_module(f"termnet.tools.{module_name}")
                cls = getattr(module, class_name)
                instance = cls()
                self.tools[fn["name"]] = instance
                #print(f"✅ Loaded tool: {fn['name']} ({module_name}.{class_name})")
            except Exception as e:
                print(f"❌ Failed to load tool {fn['name']}: {e}")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return JSON schema tool definitions (for LLM)"""
        return TOOL_REGISTRY

    def get_tool_instance(self, name: str):
        return self.tools.get(name)
