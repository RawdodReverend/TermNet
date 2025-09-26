import asyncio
import json
import websockets
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)

class BrowserSearchTool:
    def __init__(self, websocket_url="ws://localhost:8765"):
        self.websocket_url = websocket_url

    async def _connect(self):
        """No longer needed - using fresh connections"""
        pass

    async def _send_command(self, command: str, timeout: float = 15.0) -> dict:
        """Send a command to the browser server and get response - creates new connection each time"""
        try:
            # Create fresh connection for each command (matches server design)
            websocket = await asyncio.wait_for(
                websockets.connect(
                    self.websocket_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5
                ),
                timeout=5.0
            )
            
            try:
                # Send command and wait for response
                await websocket.send(command)
                response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                return json.loads(response)
            finally:
                await websocket.close()
                
        except asyncio.TimeoutError:
            logger.error(f"Command '{command}' timed out after {timeout}s")
            return {"error": f"Command timed out after {timeout}s"}
        except ConnectionRefusedError:
            return {"error": "Cannot connect to browser server. Is it running?"}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            return {"error": f"Invalid response format: {e}"}
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return {"error": f"Connection failed: {str(e)}"}

    async def search(self, url: str, max_results: int = 20) -> dict:
        """
        Navigate to a URL and collect structured interactive elements using the WebSocket server.
        Returns both structured data and a human-readable summary.
        """
        try:
            # Navigate to the URL with fresh connection
            response = await self._send_command(f"url:{url}")
            
            if "error" in response:
                summary = f"Error loading {url}: {response['error']}\n\nNext step:\n- Try a different URL or check if the site is accessible."
                return {"url": url, "elements": [], "summary": summary}

            # Extract elements from the server response
            elements = []
            
            # Process links
            if "links" in response:
                for i, link in enumerate(response["links"][:max_results]):
                    elements.append({
                        "type": "link",
                        "text": link.get("text", ""),
                        "url": link.get("url", ""),
                        "domain": link.get("domain", ""),
                        "index": i,
                        "score": self._score_text(link.get("text", ""))
                    })

            # Process buttons
            if "buttons" in response:
                for button in response["buttons"]:
                    elements.append({
                        "type": "button",
                        "text": button.get("text", ""),
                        "attributes": button.get("attrs", {}),
                        "clickable": button.get("clickable", False),
                        "score": self._score_text(button.get("text", ""))
                    })

            # Process forms
            if "forms" in response:
                for form in response["forms"]:
                    elements.append({
                        "type": "form",
                        "action": form.get("action", ""),
                        "method": form.get("method", "GET"),
                        "inputs": form.get("inputs", []),
                        "id": form.get("id", 0),
                        "score": 0.5
                    })

            # Sort elements by score (highest first)
            elements.sort(key=lambda x: x.get("score", 0), reverse=True)
            elements = elements[:max_results]

            # Build summary string
            if not elements:
                summary = (
                    "❌ No useful interactive elements found.\n\n"
                    "💡 Next step:\n"
                    "- Try refining your query or checking a different site."
                )
                return {"url": url, "elements": [], "summary": summary, "page_info": response.get("page_info", {})}

            results_text = "\n".join(
                f"{i+1}. [{e['type']}] {e.get('text', '(no text)')[:100]} "
                f"-> {e.get('url', e.get('action', ''))[:60]}... "
                f"(score: {e.get('score', 0):.2f})"
                for i, e in enumerate(elements)
            )

            page_info = response.get("page_info", {})
            summary = f"""🔍 Extracted interactive elements from {url}:
Title: {response.get('title', 'Unknown')}
Domain: {page_info.get('domain', 'Unknown')}
Links found: {page_info.get('link_count', 0)}
Forms available: {len(response.get('forms', []))}

{results_text}

💡 Next step:
- To follow a link, use: link:<index_number>
- To search page content, use: search:<search_term>
- To interact with forms, use: form or form <id>:<field=value>
- To get page content, use the click_and_collect method
- Otherwise, if you got what you needed, respond to the user.
"""
            
            return {
                "url": url, 
                "elements": elements, 
                "summary": summary,
                "page_info": page_info,
                "title": response.get("title", ""),
                "text_preview": response.get("text", "")[:500] + "..." if response.get("text") else ""
            }

        except Exception as e:
            logger.error(f"Search error: {e}")
            summary = f"❌ Error during search: {str(e)}\n\n💡 Next step:\n- Check if the browser server is running at {self.websocket_url}"
            return {"url": url, "elements": [], "summary": summary}

    async def click_and_collect(self, url: str = None, link_index: int = None, search_term: str = None) -> str:
        """
        Navigate to a URL, follow a link, or search for content.
        Returns cleaned text content from the page.
        """
        try:
            if url and not link_index:
                # Navigate to new URL
                response = await self._send_command(f"url:{url}")
            elif link_index is not None:
                # Follow a link by index
                response = await self._send_command(f"link:{link_index}")
            else:
                # Get current page info
                response = await self._send_command("info")

            if "error" in response:
                return f"❌ Error: {response['error']}"

            # Get the main text content
            text_content = response.get("text", "")
            
            if search_term:
                # Search for specific content on the page
                search_response = await self._send_command(f"search:{search_term}")
                if "search_results" in search_response:
                    results = search_response["search_results"]
                    return f"🔍 Search results for '{search_term}':\n\n" + "\n\n".join(results)
                else:
                    return f"❌ Search term '{search_term}' not found on page"

            if not text_content:
                return "❌ No readable content found on this page"

            # Clean and format the text
            lines = [line.strip() for line in text_content.splitlines() if len(line.split()) > 3]
            cleaned = "\n".join(lines)
            
            # Add page context
            title = response.get("title", "Unknown Page")
            current_url = response.get("url", url or "Unknown URL")
            
            result = f"📄 Content from: {title}\n🔗 URL: {current_url}\n\n{cleaned[:8000]}"
            
            if len(cleaned) > 8000:
                result += "\n\n... (content truncated)"
                
            return result

        except Exception as e:
            logger.error(f"Click and collect error: {e}")
            return f"❌ Error retrieving content: {str(e)}"

    async def follow_link(self, link_index: int) -> str:
        """Follow a link by index from previous search results"""
        try:
            response = await self._send_command(f"link:{link_index}")
            
            if "error" in response:
                return f"Error: {response['error']}"
            
            # Format the response like click_and_collect does
            title = response.get("title", "Unknown Page")
            current_url = response.get("url", "Unknown URL")
            text_content = response.get("text", "No readable content found on this page")
            
            # Clean and format the text
            lines = [line.strip() for line in text_content.splitlines() if len(line.split()) > 3]
            cleaned = "\n".join(lines)
            
            result = f"Content from: {title}\nURL: {current_url}\n\n{cleaned[:8000]}"
            
            if len(cleaned) > 8000:
                result += "\n\n... (content truncated)"
                
            return result

        except Exception as e:
            logger.error(f"Follow link error: {e}")
            return f"Error following link: {str(e)}"
        """Go back to the previous page"""
        return await self._send_command("back")

    async def navigate_forward(self) -> dict:
        """Go forward to the next page"""
        return await self._send_command("forward")

    async def reload_page(self) -> dict:
        """Reload the current page"""
        return await self._send_command("reload")

    async def search_page(self, search_term: str) -> dict:
        """Search for text on the current page"""
        return await self._send_command(f"search:{search_term}")

    async def fill_form(self, form_id: int = 0, form_data: dict = None) -> dict:
        """Fill and submit a form"""
        if form_data:
            data_str = ",".join([f"{k}={v}" for k, v in form_data.items()])
            return await self._send_command(f"form {form_id}:{data_str}")
        else:
            return await self._send_command("form")

    async def get_page_info(self) -> dict:
        """Get current page information"""
        return await self._send_command("info")

    async def get_help(self) -> dict:
        """Get available commands"""
        return await self._send_command("help")

    def _score_text(self, text: str) -> float:
        """Score text based on length and content quality"""
        if not text:
            return 0
        words = len(text.split())
        return min(1.0, words / 10.0)

    async def close(self):
        """No longer needed - using fresh connections for each command"""
        pass


# --- Demo usage ---
async def main():
    tool = BrowserSearchTool()
    
    try:
        # Example: search for elements on a news site
        url = "https://news.ycombinator.com"
        print(f"🔍 Searching {url}...")
        
        results = await tool.search(url, max_results=10)
        print(results["summary"])
        
        # Example: get content from the first link
        if results["elements"]:
            first_link = next((e for e in results["elements"] if e["type"] == "link"), None)
            if first_link and "index" in first_link:
                print(f"\n📄 Getting content from link {first_link['index']}...")
                content = await tool.click_and_collect(link_index=first_link["index"])
                print(content[:1000] + "..." if len(content) > 1000 else content)
        
    except Exception as e:
        print(f"❌ Demo error: {e}")
    finally:
        await tool.close()


if __name__ == "__main__":
    asyncio.run(main())