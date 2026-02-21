"""Human-like typing simulation.

Models realistic keystroke timing based on research:
- 55-70 WPM for code, 70-90 WPM for prose
- Variable inter-key delay with Gaussian noise
- Burst patterns (3-8 chars fast, then pause)
- Error injection (~6% backspace rate)
- Think pauses at natural boundaries
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass

import numpy as np

from work4me.config import TypingConfig

# Common fast bigrams (same-hand or common sequences)
FAST_BIGRAMS = {
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
}

# Characters that slow down typing (need shift or are rare)
SLOW_CHARS = set("{}[]|\\~`@#$%^&*()_+=<>?/")

# Characters adjacent on keyboard (for realistic typos)
ADJACENT_KEYS: dict[str, str] = {
    "a": "sqwz", "b": "vngh", "c": "xvdf", "d": "sfce", "e": "wrsd",
    "f": "dgcv", "g": "fhbv", "h": "gjbn", "i": "uojk", "j": "hknm",
    "k": "jli,", "l": "k;.o", "m": "n,jk", "n": "bmhj", "o": "iplk",
    "p": "o[l;", "q": "wa", "r": "etdf", "s": "adwx", "t": "ryfg",
    "u": "yihj", "v": "cfgb", "w": "qeas", "x": "zsdc", "y": "tugh",
    "z": "xas",
}


@dataclass
class TypedChar:
    """A character with its timing metadata."""

    char: str
    delay_before: float  # seconds to wait before typing this char
    is_error: bool = False  # True if this should be followed by backspace + retype


class HumanTyper:
    """Generates human-like keystroke timing."""

    def __init__(self, config: TypingConfig) -> None:
        self.config = config
        self.rng = np.random.default_rng()
        self._burst_remaining = 0
        self._in_burst = False

    def generate_sequence(self, text: str, is_code: bool = True) -> list[TypedChar]:
        """Generate a sequence of TypedChar with realistic timing.

        Args:
            text: The text to type.
            is_code: Whether this is code (slower) or prose (faster).

        Returns:
            List of TypedChar objects with delays and error flags.
        """
        result: list[TypedChar] = []
        prev_char = ""
        cfg = self.config

        base_wpm = cfg.wpm_code if is_code else cfg.wpm_prose
        # WPM → average chars per second (assuming 5 chars per word)
        base_cps = (base_wpm * 5) / 60.0
        base_delay = 1.0 / base_cps

        for i, char in enumerate(text):
            delay = self._compute_delay(char, prev_char, base_delay, is_code)

            # Think pause at natural boundaries
            if self._should_think_pause(char, i, text):
                pause = self.rng.uniform(cfg.think_pause_min, cfg.think_pause_max)
                delay += pause

            # Line boundary pause
            if char == "\n" and prev_char != "\n":
                delay += self.rng.uniform(0.3, 1.5)

            # Error injection
            is_error = (
                char in string.ascii_letters
                and random.random() < cfg.error_rate
            )

            result.append(TypedChar(char=char, delay_before=delay, is_error=is_error))
            prev_char = char

        return result

    def _compute_delay(
        self, char: str, prev_char: str, base_delay: float, is_code: bool
    ) -> float:
        cfg = self.config
        delay = base_delay

        # Fast bigrams
        bigram = (prev_char + char).lower()
        if bigram in FAST_BIGRAMS:
            delay *= 0.75

        # Slow characters (shift key, uncommon)
        if char in SLOW_CHARS:
            delay *= 1.4

        # Space after word — slight pause
        if char == " ":
            delay *= 1.1

        # Tab (indentation) — fast muscle memory
        if char == "\t":
            delay *= 0.5

        # Burst typing
        if self._burst_remaining > 0:
            delay /= cfg.burst_speed_multiplier
            self._burst_remaining -= 1
        elif random.random() < 0.15:
            # Start a new burst
            self._burst_remaining = random.randint(
                cfg.burst_length_min, cfg.burst_length_max
            )
            self._in_burst = True

        # Gaussian noise
        noise = self.rng.normal(0, cfg.inter_key_delay_sigma)
        delay += noise

        # Clamp to sane range
        delay = max(cfg.inter_key_delay_min, min(delay, cfg.inter_key_delay_max * 2))

        return delay

    def _should_think_pause(self, char: str, index: int, text: str) -> bool:
        """Determine if we should insert a think pause before this character."""
        if random.random() > self.config.think_pause_probability:
            return False

        # More likely at line starts
        if index > 0 and text[index - 1] == "\n":
            return True

        # More likely after opening braces (entering a block)
        if index > 0 and text[index - 1] in "{(:":
            return True

        return True

    def get_typo_char(self, intended: str) -> str:
        """Get a realistic typo character (adjacent key on keyboard)."""
        lower = intended.lower()
        if lower in ADJACENT_KEYS:
            adjacent = ADJACENT_KEYS[lower]
            typo = random.choice(adjacent)
            if intended.isupper():
                typo = typo.upper()
            return typo
        # Fallback: random letter
        return random.choice(string.ascii_lowercase)
