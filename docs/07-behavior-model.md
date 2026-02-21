# Human-Like Behavior Model

## Activity Distribution (4-Hour Session)

| Activity | Time | Percentage |
|---|---|---|
| Active coding (IDE) | 45-60 min | 19-25% |
| Reading code / reviewing | 30-40 min | 13-17% |
| Terminal commands (build, test, git) | 20-30 min | 8-13% |
| Browser (docs, Stack Overflow) | 25-35 min | 10-15% |
| Idle/thinking pauses | 40-60 min | 17-25% |
| Context switching transitions | 15-20 min | 6-8% |
| Micro-pauses (15-60 sec organic breaks) | Scattered | Integrated into idle time |

Sources: Microsoft "Today Was a Good Day" study of 5,971 developers; multiple developer productivity studies.

## Session Structure

```
Single continuous session (full time budget)
  Micro-pauses (15-60 sec) scattered between activities
  No formal 5-8 minute breaks
```

The scheduler produces a single continuous work session. Organic micro-pauses (15-60 seconds with mouse micro-movements) are inserted between activities, replacing the previous formal break model. This produces more natural-looking activity patterns without long idle gaps.

Within the session, activities follow the natural development cycle:
1. **Research phase** (5-15 min): Browser + reading code in IDE
2. **Coding phase** (15-30 min): Active typing, occasional terminal
3. **Testing phase** (5-10 min): Terminal + IDE (fixing failures)
4. **Cleanup phase** (5-10 min): Refactoring, comments, git commit

All durations have Gaussian noise (σ = 15-20% of mean) to prevent detectable periodicity.

---

## Typing Simulation

### Parameters

| Parameter | Value | Source |
|---|---|---|
| Code typing speed | 55-70 WPM | Developer average studies |
| Prose typing speed | 70-90 WPM | |
| Inter-key delay (base) | 50-120ms + Gaussian noise (σ=15ms) | 136M keystrokes study (Aalto University) |
| Burst pattern | 3-8 chars at 1.5x speed, then pause | |
| Error rate | 5-8% (backspace + retype 1-4 chars) | |
| Think pause | 1-5 sec, probability 3% per character | |
| Line boundary pause | 0.5-2 sec | |

### Typing Model

```python
class HumanTyper:
    def inter_key_delay(self, prev_char: str, next_char: str) -> float:
        """
        Accounts for:
        - Key distance on keyboard layout (farther = slower)
        - Same-hand vs alternating-hand pairs
        - Common bigrams are faster (th, er, in, etc.)
        - Shift-key overhead
        - Gaussian noise on every delay
        """

    def should_make_error(self) -> bool:
        """5-8% chance, modulated by typing speed and character difficulty."""

    def think_pause_probability(self, context: str) -> float:
        """Higher at line starts, after complex expressions, at function boundaries."""
```

### Keystroke Dynamics (Research-Backed)

From the 136M keystroke study:
- Fast typists use 8.4 fingers on average; slow typists use 5.3
- Typing is bursty: fast bursts of 10-15 seconds followed by variable pauses
- Inter-key intervals follow a distribution with a long tail (not uniform)
- Error correction (backspace) is frequent in real typing

### Code-Specific Adjustments

- Special characters (brackets, semicolons) are slower than letters
- Indentation (Tab or spaces) is fast (muscle memory)
- Variable names are faster after first typing (repetition)
- Auto-complete acceptance: occasional instant bursts (simulate accepting suggestion)

---

## Mouse Simulation

### Bezier Curve Movement

```python
class HumanMouse:
    def bezier_path(self, start: Point, end: Point) -> list[Point]:
        """
        Cubic Bezier with 2-4 control points.
        Control points offset perpendicular to straight line
        by random amount proportional to distance.
        """

    def fitts_duration(self, distance: float, target_width: float) -> float:
        """Fitts's law: T = a + b * log2(D/W + 1)"""

    def add_overshoot(self, path: list[Point], target: Point) -> list[Point]:
        """10-20% of moves overshoot, then correct."""
```

### Parameters

| Parameter | Value |
|---|---|
| Control points | 2-4 random |
| Overshoot probability | 15% |
| Overshoot distance | 5-20 pixels past target |
| Micro-adjustments near target | 1-3 small corrections |
| Step interval | 8-16ms between cursor positions |
| Velocity model | Fitts's Law (faster for long distance, slower near target) |

### Developer Mouse Usage

- Developers are keyboard-heavy; mouse is for:
  - Clicking file tree entries in IDE
  - Scrolling through code
  - Browser navigation (tabs, links)
  - Selecting text for copy/paste
- During coding: 2-5 mouse events per minute
- During browsing: 10-20 mouse events per minute

---

## Idle / Thinking Patterns

### Time Tracker Idle Thresholds

| Tracker | Idle Threshold |
|---|---|
| Hubstaff | Configurable: 5, 10, or 20 min |
| Time Doctor | Per-minute monitoring |
| Common default | 5-10 min no input |

### Natural Developer Idle Patterns

| Pattern | Duration |
|---|---|
| Reading without scrolling | 15-45 sec |
| Thinking pause (no input) | 5-30 sec |
| Brief distraction (check phone) | 30-90 sec |
| Coffee/bathroom break | 3-8 min |
| Extended break | 10-15 min (1-2 per 4-hour session) |

### Anti-Idle Strategy

```python
async def idle_think(self, duration_seconds: float):
    """
    During "thinking" periods:
    - Small mouse micro-movement every 45-90 seconds
    - Occasional scroll events
    - No keyboard activity
    """

async def micro_pause(self, min_sec=15, max_sec=60):
    """
    Organic micro-breaks between activities:
    - Duration: random 15-60 seconds (configurable)
    - Mouse micro-movements every 8-20 seconds
    - Respects speed_multiplier for time scaling
    - Replaces formal 5-8 minute breaks
    """
```

---

## Anti-Detection Constraints (Time Trackers)

### Hubstaff Detection Heuristics (CRITICAL)

| What Hubstaff Flags | Threshold | Our Constraint |
|---|---|---|
| Unusually high activity | ≥95% for 30+ min | Stay below 85% sustained |
| Unusually consistent activity | Fluctuation ≤4% for 90+ min | Ensure variance >5% |
| Keyboard/mouse imbalance | Keyboard ~0% while mouse active 50+ min | Always mix both |
| Robotic mouse patterns | Repetitive movement detected | Use Bezier curves with randomness |
| Known fraud applications | Watches for jiggler apps | Don't register as known tool |

### Activity Ratio Targets

```
                ┌─────────────────────────────────┐
  0%            │         TARGET ZONE             │          100%
  ├─────────────┤40%                          70%├──────────┤
  Red           │     Green/Yellow                │  FLAGGED
  (too low)     │     (normal developer)          │  (too high)
                └─────────────────────────────────┘
```

- **Per 10-minute window:** 40-70% activity ratio
- **Per 90-minute window:** variance >4%
- **Maximum continuous high (>80%) activity:** 30 minutes, then must drop

### Activity Monitor Implementation

```python
class ActivityMonitor:
    def activity_ratio(self, window_seconds: int = 600) -> float:
        """Active seconds / window seconds. Target: 0.40-0.70"""

    def variance(self, window_seconds: int = 5400) -> float:
        """Activity ratio variance over 90-min window. Must be >0.04"""

    def keyboard_mouse_balance(self, window_seconds: int = 3000) -> tuple[float, float]:
        """(keyboard_ratio, mouse_ratio). Flag if imbalanced."""

    def is_within_bounds(self) -> ActivityHealth:
        """Check all constraints. Returns warnings/adjustments."""

    def recommended_adjustment(self) -> BehaviorAdjustment:
        """Suggest: slow down, speed up, add idle, add mouse."""
```

### Feedback Loop

```
ActivityMonitor → health check every 60 sec → Orchestrator → BehaviorEngine adjustments
```

If activity too high → insert extra thinking pauses
If activity too low → speed up slightly
If variance too low → add intentional fluctuation
If keyboard/mouse imbalanced → add mouse movements during coding

---

## Context Switching Patterns

### Realistic Triggers

| Trigger | From → To | Duration in Target |
|---|---|---|
| Need API docs | IDE → Browser | 30-120 sec |
| Run tests | IDE → Terminal | 10-60 sec (watching output) |
| Test failure | Terminal → IDE | 2-10 min (debugging) |
| Check PR review | IDE → Browser | 1-5 min |
| Commit changes | IDE → Terminal | 30-60 sec |
| Search error message | Terminal → Browser | 1-3 min |
| Copy code example | Browser → IDE | 15-30 sec |

Switch frequency: **3-8 per 25-minute focused work period**.

Research shows:
- Developers switch tasks or get interrupted 59% of the day
- 29% of interrupted tasks are never resumed
- Work sessions fragment into 15-30 minute bursts
- 23 min 15 sec to regain focus after interruption

---

## Critical Timing Constants

```python
# Typing
TYPING_WPM_CODE = (55, 70)
TYPING_WPM_PROSE = (70, 90)
INTER_KEY_DELAY_BASE = (0.050, 0.120)  # seconds
INTER_KEY_DELAY_SIGMA = 0.015
BURST_LENGTH = (3, 8)                   # characters
BURST_SPEED_MULTIPLIER = 1.5
ERROR_RATE = (0.05, 0.08)               # per character
THINK_PAUSE_DURATION = (1.0, 5.0)       # seconds
THINK_PAUSE_PROBABILITY = 0.03          # per character

# Mouse
MOUSE_STEP_INTERVAL = (0.008, 0.016)    # seconds
BEZIER_CONTROL_POINTS = (2, 4)
OVERSHOOT_PROBABILITY = 0.15
OVERSHOOT_DISTANCE = (5, 20)            # pixels
MICRO_ADJUSTMENT_COUNT = (1, 3)

# Activity
ACTIVITY_RATIO_TARGET = (0.40, 0.70)    # per 10-min window
ACTIVITY_VARIANCE_MIN = 0.04             # over 90-min window
IDLE_MICRO_MOVEMENT_INTERVAL = (45, 90)  # seconds
MAX_CONTINUOUS_HIGH_ACTIVITY = 1800      # seconds (30 min)

# Sessions (single continuous session, no formal breaks)
SESSION_DURATION_MEAN = 52               # minutes (unused — single session covers budget)
SESSION_DURATION_SIGMA = 5
BREAK_DURATION_MEAN = 0.0               # no formal breaks
BREAK_DURATION_SIGMA = 0.0
SESSIONS_PER_4_HOURS = 1                # single continuous session

# Micro-pauses (replace formal breaks)
MICRO_PAUSE_MIN_SECONDS = 15
MICRO_PAUSE_MAX_SECONDS = 60
MICRO_PAUSE_FREQUENCY = 0.3            # probability per activity transition

# Time split targets
TIME_SPLIT = {
    "coding": 0.25,
    "reading": 0.15,
    "terminal": 0.10,
    "browser": 0.12,
    "thinking": 0.20,
    "transitions": 0.08,
    "micro_pauses": 0.10,
}
```
