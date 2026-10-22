"""Run Qt tests without depending on the desktop or system clipboard."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
