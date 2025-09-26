import json
import pathlib
from typing import List, Tuple, Dict, Any

DATA_FILE = pathlib.Path(__file__).parent / "scratchpad.json"


class Scratchpad:
    def __init__(self):
        self._notes: List[str] = []
        self._load_notes()

    def _load_notes(self):
        """Load notes from disk if the file exists"""
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self._notes = json.load(f)
            except Exception:
                # If the file is corrupted or unreadable, reset
                self._notes = []

    def _save_notes(self):
        """Save notes to disk"""
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Failed to save scratchpad: {e}")

    async def start(self) -> bool:
        return True

    async def stop(self):
        return

    async def run(self, action: str, content: str = "") -> Tuple[str, int, bool]:
        # Normalize action names
        action = action.strip().lower().replace(" ", "_")

        if action == "write":
            self._notes.append(content)
            self._save_notes()
            return f"📝 Note added: \"{content}\"", 0, True

        elif action in ("read_all", "read", "read_all_notes"):
            if not self._notes:
                return "📖 Scratchpad is empty.", 0, True
            notes_text = "\n".join(f"{i+1}. {n}" for i, n in enumerate(self._notes))
            return f"📖 Scratchpad contents:\n{notes_text}", 0, True

        elif action == "clear":
            self._notes.clear()
            self._save_notes()
            return "🗑️ Scratchpad cleared.", 0, True

        else:
            return f"❌ Unknown action: {action}", 1, False

    # ✅ Alias so TermNetAgent can find a method named "scratchpad"
    async def scratchpad(self, **kwargs):
        return await self.run(**kwargs)

    def get_context_info(self) -> Dict[str, Any]:
        return {
            "notes_count": len(self._notes),
            "last_note": self._notes[-1] if self._notes else None
        }
