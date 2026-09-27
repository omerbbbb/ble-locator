"""AR projection — maps 2D room coordinates onto camera screen space.

Pure math. No camera, no UI, no platform dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ProjectedPoint:
    screen_x: float
    screen_y: float
    distance: float
    angle_offset: float  # radians from camera centre, signed


def project(
    my_pos: Tuple[float, float],
    target_pos: Tuple[float, float],
    heading_rad: float,
    fov_h_rad: float,
    frame_w: int,
    frame_h: int,
    room_depth: float = 8.0,
) -> Optional[ProjectedPoint]:
    """Project a room-coordinate target onto camera screen coordinates.

    Returns None if the target is behind the camera or outside the FOV.
    """
    dx = target_pos[0] - my_pos[0]
    dy = target_pos[1] - my_pos[1]
    dist = math.hypot(dx, dy)
    if dist < 0.01:
        return None

    angle_world = math.atan2(dy, dx)
    angle_rel = (angle_world - heading_rad + math.pi) % (2 * math.pi) - math.pi

    if abs(angle_rel) > fov_h_rad / 2:
        return None

    focal = (frame_w / 2.0) / math.tan(fov_h_rad / 2.0)
    sx = frame_w / 2.0 + math.tan(angle_rel) * focal

    mid = frame_h / 2.0
    depth_frac = min(dist / max(room_depth, 0.1), 1.0)
    sy = mid + 0.25 * frame_h * (1.0 - 2.0 * depth_frac)

    return ProjectedPoint(screen_x=sx, screen_y=sy, distance=dist, angle_offset=angle_rel)


def circle_radius(distance: float, base: float = 40.0) -> float:
    """Screen radius for the AR circle — closer = bigger."""
    return max(15.0, min(80.0, base / max(distance, 0.3)))
