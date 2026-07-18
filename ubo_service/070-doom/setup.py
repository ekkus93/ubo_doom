"""Ubo v2 external service integration for the embedded Doom engine.

The current Ubo architecture keeps services in the headless Redux core and
renders serializable views in a separate GUI client. Doom therefore publishes
RGB888 frames through Ubo's generic ``frame_stream`` view instead of importing
Kivy or writing directly to the ST7789 display.
"""

from __future__ import annotations

import os