# Browser Automation

## Approach: Firefox via Playwright

Launch a visible Firefox window using Playwright's `launch_persistent_context`, which manages the browser lifecycle natively. No subprocess spawning, no port polling, no singleton issues.

### Why Firefox over Chrome?

Chrome has an unfixable singleton problem on Linux: when the user's Chrome is already running, spawning `google-chrome --remote-debugging-port=9222` results in the new process either exiting silently (delegating via IPC) or hanging as a zombie — port 9222 never opens. Firefox via Playwright avoids this entirely.

## Launching Firefox

```python
from playwright.async_api import async_playwright

pw = await async_playwright().__aenter__()
context = await pw.firefox.launch_persistent_context(
    user_data_dir or "",       # Empty string = temp profile
    headless=False,            # Visible window
    timeout=30000,             # Launch timeout (ms)
)
page = context.pages[0] if context.pages else await context.new_page()
```

Key points:
- `launch_persistent_context` returns a `BrowserContext` directly (no separate `Browser` object)
- `headless=False` ensures a visible browser window opens
- Persistent profile via `user_data_dir` preserves bookmarks, history, login sessions
- Empty `user_data_dir` creates a temporary profile

## Cleanup

```python
await context.close()    # Closes browser process too
await pw.stop()          # Stops Playwright server
```

Unlike Chrome/CDP where you must `disconnect()` to keep the browser alive, with Playwright-managed Firefox, `context.close()` cleanly shuts down the browser process.

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
- Switch between tabs periodically (Ctrl+Tab or click)
- Close completed tabs
- Leave documentation tabs open during coding phases

## Wayland Notes

Firefox auto-detects Wayland when `WAYLAND_DISPLAY` is set. The `MOZ_ENABLE_WAYLAND=1` environment variable can be set explicitly but is rarely needed on modern systems. Playwright's browser management is display-server agnostic.

## Browser Extensions (Future Enhancement)

A custom WebExtension could provide richer control via Native Messaging:

```
Work4Me daemon  ←→  Native Messaging Host  ←→  WebExtension
                     (stdin/stdout JSON)         (tabs, scripting APIs)
```

**APIs available:** `browser.tabs`, `browser.windows`, `browser.scripting`, `browser.webNavigation`, `browser.history`

## Pydoll Library (Reference)

`pydoll` — Python library for realistic browser interactions:
- Variable keystroke timing (30-120ms)
- Simulated typos (~2% error rate)
- Physics-based scrolling
- Can be used as reference implementation for behavior simulation
