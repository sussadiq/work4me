# Browser Automation

## Approach: Chromium via Chrome DevTools Protocol (CDP)

Launch a visible Chromium window and control it via CDP, either directly or through Playwright.

## Launching Chromium

```bash
chromium --remote-debugging-port=9222 \
         --ozone-platform=wayland \
         --no-first-run \
         --no-default-browser-check
```

Key flags:
- `--remote-debugging-port=9222` — enables CDP WebSocket access
- `--ozone-platform=wayland` — required on Wayland (without it, headed mode may fail)
- Chrome outputs: `DevTools listening on ws://127.0.0.1:9222/devtools/browser/<id>`

## Connecting via Playwright

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp('http://localhost:9222')
    context = browser.contexts[0]
    page = context.pages[0]

    await page.goto('https://stackoverflow.com')
    # ... interact with page ...

    # IMPORTANT: disconnect, don't close (or you kill the visible browser)
    await browser.disconnect()  # NOT browser.close()
```

## Connecting via Puppeteer (Node.js alternative)

```javascript
const browser = await puppeteer.connect({
  browserWSEndpoint: 'ws://127.0.0.1:9222/devtools/browser/<id>'
});
const pages = await browser.pages();
```

## CDP Domains for Work4Me

| Domain | Capabilities |
|---|---|
| `Page` | Navigation, screenshots, lifecycle events |
| `Input` | Mouse events (click, move, drag), keyboard events (keyDown/keyUp) |
| `DOM` | Query/modify DOM elements |
| `Runtime` | Execute JavaScript in page context |
| `Target` | Tab/window management (create, close, activate) |
| `Network` | Request interception, monitoring |

## Human-Like Browsing Patterns

### Typing in Search Bars

```python
# Type character by character with variable delay
for char in query:
    delay = random.gauss(0.085, 0.015)  # 50-120ms range
    await page.keyboard.press(char, delay=delay * 1000)
```

Or via Playwright's built-in delay:
```python
await page.type('#search-input', query, delay=85)  # ms per character
```

### Scrolling

```python
# Scroll in increments with pauses
for _ in range(scroll_steps):
    delta = random.randint(100, 300)  # pixels
    await page.mouse.wheel(0, delta)
    pause = random.uniform(0.2, 0.5)  # seconds
    await asyncio.sleep(pause)
```

### Reading Time

```python
# Calculate expected reading time from visible text
text = await page.inner_text('body')
words = len(text.split())
reading_wpm = random.uniform(200, 250)
reading_time = (words / reading_wpm) * 60  # seconds
reading_time *= random.uniform(0.8, 1.2)  # ±20% variance
await asyncio.sleep(reading_time)
```

### Search Pattern (Complete Flow)

1. Navigate to search engine (Google, Stack Overflow)
2. Click search bar (mouse move via Bezier → click)
3. Type query character by character (50-120ms per key)
4. Wait 1-3 seconds "reviewing results"
5. Scroll through results (100-300px increments)
6. Click a result link
7. Read the page (scroll gradually, pause at sections)
8. Navigate back or open new tab
9. Refine search or click another result

### Tab Management

- Open 3-5 tabs during a research session
- Switch between tabs periodically (Ctrl+Tab or click via CDP)
- Close completed tabs
- Leave documentation tabs open during coding phases

## Firefox Marionette (Alternative)

Firefox supports remote debugging via `--marionette` flag (port 2828). Also supports WebDriver BiDi protocol. Playwright abstracts both Chrome and Firefox with the same API.

**For Work4Me:** Chrome/Chromium is the pragmatic choice — CDP is more mature, more widely documented.

## Browser Extensions (Future Enhancement)

A custom WebExtension could provide richer control via Native Messaging:

```
Work4Me daemon  ←→  Native Messaging Host  ←→  WebExtension
                     (stdin/stdout JSON)         (tabs, scripting APIs)
```

**APIs available:** `chrome.tabs`, `chrome.windows`, `chrome.scripting`, `chrome.webNavigation`, `chrome.history`

**Auto-install:** Chrome `--load-extension=/path/to/extension` (unpacked)

## Pydoll Library (Reference)

`pydoll` — Python library for realistic CDP interactions:
- Variable keystroke timing (30-120ms)
- Simulated typos (~2% error rate)
- Physics-based scrolling
- Can be used as reference implementation for behavior simulation

## Wayland-Specific Notes

- The `--ozone-platform=wayland` flag is required for native Wayland rendering
- Without it, Chromium may try X11/XWayland and fail or render incorrectly
- CDP WebSocket protocol itself is display-server agnostic
- PipeWire integration for screen sharing works in Chromium on Wayland
