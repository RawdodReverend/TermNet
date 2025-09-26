import re
from typing import Tuple

class SafetyChecker:
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/?(\s|$)',
        r'dd\s+if=.*\s+of=/dev/',
        r'mkfs\.',
        r'\bshutdown\b',
        r'\breboot\b',
        r'\bhalt\b',
        r'\bpoweroff\b',
        r'\binit\s+[06]\b',
        r':\(\)\{.*\}'
    ]
    RISKY_COMMANDS = {
        'rm','rmdir','chmod','chown','mv','dd','fdisk',
        'mkfs','format','del','rd','attrib','cacls'
    }

    @classmethod
    def is_safe(cls, command: str) -> Tuple[bool, str]:
        if not command or not command.strip():
            return True, ""
        low = command.lower().strip()
        for pat in cls.DANGEROUS_PATTERNS:
            if re.search(pat, low):
                return False, "Dangerous pattern detected."
        head = low.split()[0]
        if head in cls.RISKY_COMMANDS:
            return True, "⚠️ Caution: risky command."
        return True, ""
