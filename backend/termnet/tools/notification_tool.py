import aiohttp
from typing import Optional, List, Dict



class NotificationTool:
    """Manage notifications via a standalone notification server."""

    def __init__(self, server_url: str = "http://localhost:5003"):
        self.server_url = server_url

    async def add(self, title: str, message: str, reminder_time: Optional[float] = None) -> Dict:
        payload = {
            "title": title,
            "message": message,
            "reminder_time": reminder_time
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.server_url}/new_notification", json=payload) as r:
                return await r.json()

    async def list(self) -> List[Dict]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.server_url}/list_notifications") as r:
                return await r.json()

    async def dismiss(self, index: int) -> Dict:
        payload = {"index": index}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.server_url}/dismiss_notification", json=payload) as r:
                return await r.json()
