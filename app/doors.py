"""Deprecated - superseded by `app.modules.user_mode`.

The four entry points of specification section 4 are now a user-mode selector over a
single workflow rather than four parallel panels: the door sets vocabulary and
defaults, not capability, which is what design rule 1 actually asks for. Four copies
of the same workflow was the wrong reading.

Kept only so an old import fails loudly with this explanation instead of an
unexplained ImportError. Delete once nothing references it.
"""

from app.modules.user_mode import CHOICES, MODES  # noqa: F401

DOORS = MODES
