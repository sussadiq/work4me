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

### Auth via Persistent Profiles

Set `user_data_dir` in config to maintain login sessions across runs:

```toml
[browser]
user_data_dir = "/home/user/.work4me/firefox-profile"
```

The persistent context preserves cookies, localStorage, and session data — no need to re-authenticate on every run.

## Cleanup

```python
await context.close()    # Closes browser process too
await pw.stop()          # Stops Playwright server
```

Unlike Chrome/CDP where you must `disconnect()` to keep the browser alive, with Playwright-managed Firefox, `context.close()` cleanly shuts down the browser process.

## Architecture: BrowserMouse

Mouse movements in the browser use the existing `HumanMouse` class (Bezier curves + Fitts's law) routed through Playwright's `page.mouse` API — NOT system-level input.

```
HumanMouse (behavior/mouse.py)
    ├── bezier_path(start, end) → list[Point]
    └── fitts_duration(distance, target_width) → seconds
         │
         ▼
BrowserMouse (controllers/browser_mouse.py)
    ├── move_to(page, x, y)       → Bezier path → page.mouse.move() per step
    ├── click_at(page, x, y)      → move_to + page.mouse.click()
    ├── click_element(page, sel)   → bounding_box → center + jitter → click_at
    └── micro_movement(page)       → small idle jitter
         │
         ▼
Playwright page.mouse API
    └── Moves mouse within page coordinate system
```

**Why page.mouse, not system mouse?** System-level input (ydotool/dotool) would require knowing the browser window's screen position and would break if the window moves. Playwright's API moves the mouse within the page coordinate system — simpler and more reliable.

### Configuration

```toml
[browser.mouse]
step_interval_min = 0.008   # Min delay between Bezier steps (seconds)
step_interval_max = 0.016   # Max delay between Bezier steps
overshoot_probability = 0.15 # Chance of overshooting the target
click_delay_min = 0.05      # Pre-click delay min
click_delay_max = 0.15      # Pre-click delay max
```

## CAPTCHA Detection and Solving

CAPTCHAs are detected by checking known selectors, then solved via Claude vision API.

### Detection Flow

```
CaptchaDetector.detect(page)
    ├── Check iframe[src*='recaptcha']
    ├── Check iframe[src*='hcaptcha']
    ├── Check #cf-turnstile-container
    ├── Check .g-recaptcha / .h-captcha
    └── Check [data-sitekey]
    → Returns CaptchaInfo(kind, selector, box) or None
```

### Solving Flow

```
CaptchaSolver.solve(page, browser_mouse, captcha)
    1. Screenshot the CAPTCHA region (page.screenshot with clip)
    2. Base64-encode screenshot → Claude vision API
    3. Claude returns JSON: {steps: [{action, x?, y?, text?, selector?}]}
    4. Execute each step using BrowserMouse for human-like clicks
    5. Retry up to max_attempts on failure
```

The `anthropic` package is an optional dependency (`pip install work4me[captcha]`). CAPTCHA solving is disabled if not installed.

### Configuration

```toml
[browser.captcha]
enabled = true
anthropic_model = "claude-sonnet-4-20250514"
max_attempts = 3
screenshot_timeout = 5000.0
```

## Cookie Banner Dismissal

Brute-force approach: try a prioritized list of common selectors. Most cookie banners use standard text.

```python
COOKIE_SELECTORS = [
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
    "button:has-text('OK')",
    "[id*='accept']",
    "[class*='accept']",
    "button:has-text('Got it')",
    "button:has-text('Allow')",
]
```

If none match, silently continue (not all pages have banners). Clicks use BrowserMouse for human-like movement.

## Method Inventory

### Navigation
| Method | Description |
|--------|-------------|
| `navigate(url)` | Navigate to URL |
| `navigate_with_captcha_check(url)` | Navigate + dismiss cookies + handle CAPTCHA |
| `go_back()` / `go_forward()` | Browser history navigation |
| `current_url()` | Return current page URL |
| `search(query, engine)` | Search via Google/StackOverflow |

### Element Interaction
| Method | Description |
|--------|-------------|
| `click(selector)` | Click element using BrowserMouse |
| `click_link(text)` | Find link by visible text, click |
| `fill_field(selector, text)` | Click field, clear, type with delay |
| `submit_form(selector?)` | Find and click submit button |
| `type_in_search(selector, query)` | Type in search bar char by char |

### Element Queries
| Method | Description |
|--------|-------------|
| `wait_for(selector, timeout)` | Wait for element to appear |
| `get_element_text(selector)` | Get text content |
| `get_attribute(selector, attr)` | Get attribute value |
| `is_visible(selector)` | Check visibility |
| `get_page_text()` | Get full page text |

### Page Actions
| Method | Description |
|--------|-------------|
| `scroll_down(pixels)` | Scroll with natural variation |
| `screenshot(path?, clip?)` | Full page or clipped screenshot |
| `dismiss_cookie_banner()` | Try common cookie selectors |
| `handle_captcha()` | Detect + solve CAPTCHA |

### Tab & Cookie Management
| Method | Description |
|--------|-------------|
| `new_tab(url)` | Open new tab |
| `close_tab()` | Close current tab |
| `get_cookies()` / `set_cookies(cookies)` | Cookie management |

## Human-Like Browsing Patterns

### Typing in Search Bars

```python
await page.type('#search-input', query, delay=85)  # ms per character
```

### Scrolling

```python
# Scroll in increments with pauses
for _ in range(scroll_steps):
    delta = random.randint(80, 150)  # pixels
    await page.mouse.wheel(0, delta)
    pause = random.uniform(0.2, 0.5)  # seconds
    await asyncio.sleep(pause)
```

### Search Pattern (Complete Flow)

1. Navigate to search engine (Google, Stack Overflow)
2. Dismiss cookie banner automatically
3. Check for CAPTCHA, solve if present
4. Click search result heading (h3) with BrowserMouse
5. Dismiss cookie banner on result page
6. Read the page (scroll gradually, pause at sections)
7. Navigate back to results
8. Click another result or refine search

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
