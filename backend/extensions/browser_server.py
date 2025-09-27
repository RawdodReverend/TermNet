import asyncio
import json
import websockets
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright
import logging

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

connected_clients = set()

# Global browser state - persists across all connections
global_browser = None
global_context = None
global_page = None
global_history = []
global_current_url = None
global_forms = []
browser_lock = asyncio.Lock()

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def initialize_browser():
    """Initialize the global browser instance with anti-bot measures"""
    global global_browser, global_context, global_page
    if global_browser is None:
        playwright = await async_playwright().__aenter__()

        global_browser = await playwright.chromium.launch(
            headless=False,  # headless=False can reduce bot detection in some cases
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )

        global_context = await global_browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/116.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            color_scheme='light',
        )

        global_page = await global_context.new_page()

        # Apply stealth measures
        await stealth_async(global_page)

        global_page.set_default_timeout(10000)

def clean_text(text):
    """Clean and normalize text content"""
    if not text:
        return ""
    # Remove extra whitespace and normalize
    text = re.sub(r'\s+', ' ', text.strip())
    # Remove any remaining unwanted characters
    text = re.sub(r'[^\w\s\.,!?;:()\-"\'@#$%&*+=<>/\\|`~\[\]{}]', '', text)
    return text

def extract_readable_content(soup):
    """Extract the main readable content from HTML"""
    # Remove unwanted elements
    for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 
                     'noscript', 'iframe', 'object', 'embed']):
        tag.decompose()
    
    # Try to find main content areas in order of preference
    main_selectors = [
        'main', 'article', '[role="main"]', '.content', '#content',
        '.post', '.entry', '.article-body', '.story-body'
    ]
    
    main_content = None
    for selector in main_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break
    
    # Fallback to body if no main content found
    if not main_content:
        main_content = soup.body or soup
    
    # Extract text with better formatting
    text_parts = []
    for element in main_content.descendants:
        if isinstance(element, NavigableString):
            text = clean_text(str(element))
            if text and text not in text_parts[-5:]:  # Avoid immediate duplicates
                text_parts.append(text)
        elif element.name in ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text_parts.append('\n')
    
    return ' '.join(text_parts).strip()

async def get_structured_data(page, url):
    """Extract structured data from a webpage"""
    try:
        # Wait for content to load
        await page.wait_for_load_state('networkidle', timeout=5000)
    except:
        pass  # Continue if timeout
    
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title
    title = "No Title"
    if soup.title and soup.title.string:
        title = clean_text(soup.title.string)
    elif soup.find('h1'):
        title = clean_text(soup.find('h1').get_text())
    
    # Extract main text content
    text = extract_readable_content(soup)
    
    # Extract links with better filtering
    links = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:')):
            continue
            
        full_url = urljoin(url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        link_text = clean_text(a.get_text())
        if not link_text:
            link_text = href[:50] + "..." if len(href) > 50 else href
        
        # Filter out common unwanted links
        unwanted_patterns = [
            r'privacy.*policy', r'terms.*service', r'cookie.*policy',
            r'\.css$', r'\.js$', r'\.jpg$', r'\.png$', r'\.gif$'
        ]
        
        if not any(re.search(pattern, full_url, re.I) for pattern in unwanted_patterns):
            links.append({
                "text": link_text[:100],
                "url": full_url,
                "domain": urlparse(full_url).netloc
            })
    
    # Extract buttons
    buttons = []
    for b in soup.find_all(["button", "input[type='button']", "input[type='submit']"]):
        button_text = clean_text(b.get_text() or b.get('value', 'Button'))
        if button_text:
            buttons.append({
                "text": button_text[:100],
                "attrs": {k: v for k, v in b.attrs.items() if k in ['type', 'id', 'class', 'name']},
                "clickable": True
            })
    
    # Extract forms with better field detection
    forms = []
    for i, form in enumerate(soup.find_all("form")):
        action = form.get("action", "")
        if action:
            action = urljoin(url, action)
        else:
            action = url
            
        method = form.get("method", "GET").upper()
        
        inputs = []
        for inp in form.find_all(["input", "textarea", "select"]):
            input_type = inp.get("type", inp.name).lower()
            input_name = inp.get("name", "")
            
            if input_type in ['hidden', 'submit', 'button']:
                continue
                
            input_info = {
                "name": input_name,
                "type": input_type,
                "placeholder": inp.get("placeholder", ""),
                "value": inp.get("value", ""),
                "required": inp.has_attr("required")
            }
            
            # Handle select options
            if inp.name == "select":
                options = [opt.get("value", opt.get_text()) for opt in inp.find_all("option")]
                input_info["options"] = options
            
            inputs.append(input_info)
        
        if inputs:  # Only include forms with inputs
            forms.append({
                "id": i,
                "action": action,
                "method": method,
                "inputs": inputs
            })
    
    return {
        "title": title,
        "url": page.url,
        "text": text[:2000],  # Increased text limit
        "links": links[:50],  # Increased link limit
        "buttons": buttons[:20],
        "forms": forms,
        "page_info": {
            "domain": urlparse(page.url).netloc,
            "path": urlparse(page.url).path,
            "has_forms": len(forms) > 0,
            "link_count": len(links),
            "text_length": len(text)
        }
    }

async def handle_single_command(websocket):
    """Handle a single command from a WebSocket connection"""
    global global_history, global_current_url, global_forms
    
    async with browser_lock:
        await initialize_browser()
        
        try:
            # Wait for the command
            command = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            command = command.strip()
            response = {}
            
            logger.info(f"Processing command: {command}")
            
            # Navigate to URL
            if command.startswith(("url:", "go:", "open:")):
                url = command.split(":", 1)[1].strip()
                if not url.startswith(('http://', 'https://')):
                    url = "https://" + url
                
                try:
                    await global_page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    content = await get_structured_data(global_page, global_page.url)
                    global_current_url = global_page.url
                    global_forms = content["forms"]
                    global_history.append(global_current_url)
                    response = content
                except Exception as e:
                    response = {"error": f"Failed to load {url}: {str(e)}"}
            
            # Follow link by index
            elif command.startswith("link:"):
                try:
                    idx = int(command.split(":", 1)[1].strip())
                    current_content = await get_structured_data(global_page, global_page.url)
                    if 0 <= idx < len(current_content["links"]):
                        target_url = current_content["links"][idx]["url"]
                        await global_page.goto(target_url, wait_until='domcontentloaded', timeout=15000)
                        content = await get_structured_data(global_page, global_page.url)
                        global_current_url = global_page.url
                        global_forms = content["forms"]
                        global_history.append(global_current_url)
                        response = content
                    else:
                        response = {"error": f"Link index {idx} out of range"}
                except (ValueError, IndexError) as e:
                    response = {"error": f"Invalid link command: {str(e)}"}
            
            # Search on page
            elif command.startswith("search:"):
                search_term = command.split(":", 1)[1].strip()
                html = await global_page.content()
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text().lower()
                
                if search_term.lower() in text:
                    # Find context around the search term
                    sentences = re.split(r'[.!?]+', soup.get_text())
                    matches = []
                    for i, sentence in enumerate(sentences):
                        if search_term.lower() in sentence.lower():
                            # Get surrounding context
                            start = max(0, i-1)
                            end = min(len(sentences), i+2)
                            context = ' '.join(sentences[start:end]).strip()
                            matches.append(clean_text(context))
                    
                    response = {
                        "search_results": matches[:5],
                        "total_matches": len(matches),
                        "search_term": search_term
                    }
                else:
                    response = {"error": f"'{search_term}' not found on page"}
            
            # Fill and submit form
            elif command.startswith("form"):
                try:
                    if ":" not in command:
                        # List available forms
                        if global_forms:
                            form_list = []
                            for i, form in enumerate(global_forms):
                                fields = ", ".join([f['name'] for f in form['inputs'] if f['name']])
                                form_list.append({
                                    "id": i,
                                    "action": form['action'],
                                    "method": form['method'],
                                    "fields": fields
                                })
                            response = {"available_forms": form_list}
                        else:
                            response = {"error": "No forms found on this page"}
                    else:
                        form_part, data_part = command.split(":", 1)
                        form_id = int(form_part.strip().split()[-1])
                        
                        if 0 <= form_id < len(global_forms):
                            selected_form = global_forms[form_id]
                            
                            # Parse form data
                            form_data = {}
                            if data_part.strip():
                                data_pairs = [pair.strip() for pair in data_part.split(",")]
                                for pair in data_pairs:
                                    if "=" in pair:
                                        name, value = pair.split("=", 1)
                                        form_data[name.strip()] = value.strip()
                            
                            # Fill form fields
                            for field in selected_form["inputs"]:
                                field_name = field["name"]
                                if field_name in form_data:
                                    try:
                                        element = await global_page.query_selector(f'[name="{field_name}"]')
                                        if element:
                                            await element.fill(form_data[field_name])
                                    except Exception as e:
                                        logger.warning(f"Could not fill field {field_name}: {e}")
                            
                            # Submit form
                            submit_btn = await global_page.query_selector('input[type="submit"], button[type="submit"]')
                            if submit_btn:
                                await submit_btn.click()
                            else:
                                # Try to submit the form directly
                                form_element = await global_page.query_selector('form')
                                if form_element:
                                    await form_element.evaluate('form => form.submit()')
                            
                            await global_page.wait_for_load_state('domcontentloaded', timeout=10000)
                            content = await get_structured_data(global_page, global_page.url)
                            global_current_url = global_page.url
                            global_forms = content["forms"]
                            global_history.append(global_current_url)
                            response = content
                        else:
                            response = {"error": f"Form {form_id} not found"}
                            
                except Exception as e:
                    response = {"error": f"Form error: {str(e)}"}
            
            # Navigation commands
            elif command == "back":
                if len(global_history) >= 2:
                    await global_page.go_back(wait_until='domcontentloaded', timeout=10000)
                    content = await get_structured_data(global_page, global_page.url)
                    global_current_url = global_page.url
                    global_forms = content["forms"]
                    response = content
                else:
                    response = {"error": "No previous page in history"}
            
            elif command == "forward":
                try:
                    await global_page.go_forward(wait_until='domcontentloaded', timeout=10000)
                    content = await get_structured_data(global_page, global_page.url)
                    global_current_url = global_page.url
                    global_forms = content["forms"]
                    response = content
                except:
                    response = {"error": "No forward page available"}
            
            elif command in ["reload", "refresh"]:
                await global_page.reload(wait_until='domcontentloaded', timeout=10000)
                content = await get_structured_data(global_page, global_page.url)
                global_current_url = global_page.url
                global_forms = content["forms"]
                response = content
            
            # Show current page info
            elif command in ["info", "status"]:
                if global_current_url:
                    content = await get_structured_data(global_page, global_page.url)
                    response = {
                        "current_url": global_current_url,
                        "title": content.get("title", "Unknown"),
                        "page_info": content.get("page_info", {}),
                        "history_length": len(global_history)
                    }
                else:
                    response = {"error": "No page loaded"}
            
            # Help command
            elif command in ["help", "commands"]:
                response = {
                    "commands": [
                        "url:example.com - Navigate to URL",
                        "link:N - Follow link N",
                        "search:term - Search for text on page",
                        "form - List available forms",
                        "form N:field=value,field2=value2 - Fill and submit form",
                        "back - Go back",
                        "forward - Go forward",
                        "reload - Reload current page",
                        "info - Show current page info",
                        "help - Show this help"
                    ]
                }
            
            else:
                response = {"error": f"Unknown command: {command}. Type 'help' for available commands."}
            
            # Send response
            await websocket.send(json.dumps(response))
            
        except asyncio.TimeoutError:
            await websocket.send(json.dumps({"error": "Command timeout"}))
        except json.JSONDecodeError as e:
            await websocket.send(json.dumps({"error": f"JSON error: {str(e)}"}))
        except Exception as e:
            logger.error(f"Command error: {str(e)}")
            await websocket.send(json.dumps({"error": f"Command failed: {str(e)}"}))

async def websocket_handler(websocket, path=None):
    """Handle WebSocket connections - one command per connection"""
    connected_clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(connected_clients)}")
    
    try:
        await handle_single_command(websocket)
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"Session error: {str(e)}")
    finally:
        connected_clients.remove(websocket)
        logger.info(f"Client removed. Total clients: {len(connected_clients)}")

async def main():
    """Start the WebSocket server"""
    
    async with websockets.serve(websocket_handler, "localhost", 8765, ping_interval=20, reuse_address=True, ping_timeout=60):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())