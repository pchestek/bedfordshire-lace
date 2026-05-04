"""Base class for all lace design elements."""
import uuid


def _rot(cx, cy, c, s, x, y):
    """Rotate (x, y) around (cx, cy). Positive angle = CW on screen (Y-down)."""
    dx, dy = x - cx, y - cy
    return (cx + dx * c - dy * s,
            cy + dx * s + dy * c)


class LaceElement:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.element_type = "base"
