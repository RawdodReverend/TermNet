import time
from dataclasses import dataclass, field
from typing import Any, Dict

class StepType:
    PLAN = "plan"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    ERROR = "error"

@dataclass
class MemoryStep:
    step_type: str
    content: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
