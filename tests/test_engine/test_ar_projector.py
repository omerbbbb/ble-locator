import math
import pytest
from engine.ar_projector import ProjectedPoint, circle_radius, project


def test_project_in_front():
    p = project(
        my_pos=(0.0, 0.0),
        target_pos=(3.0, 0.0),
        heading_rad=0.0,
        fov_h_rad=math.radians(60),
        frame_w=640,
        frame_h=480,
    )
    assert p is not None
    assert abs(p.screen_x - 320) < 1
    assert abs(p.distance - 3.0) < 0.01
    assert abs(p.angle_offset) < 0.01


def test_project_behind_returns_none():
    p = project(
        my_pos=(0.0, 0.0),
        target_pos=(-3.0, 0.0),
        heading_rad=0.0,
        fov_h_rad=math.radians(60),
        frame_w=640,
        frame_h=480,
    )
    assert p is None


def test_project_outside_fov_returns_none():
    p = project(
        my_pos=(0.0, 0.0),
        target_pos=(1.0, 5.0),
        heading_rad=0.0,
        fov_h_rad=math.radians(60),
        frame_w=640,
        frame_h=480,
    )
    assert p is None


def test_project_very_close_returns_none():
    p = project(
        my_pos=(1.0, 1.0),
        target_pos=(1.0, 1.0),
        heading_rad=0.0,
        fov_h_rad=math.radians(60),
        frame_w=640,
        frame_h=480,
    )
    assert p is None


def test_project_off_center():
    p = project(
        my_pos=(0.0, 0.0),
        target_pos=(3.0, 1.0),
        heading_rad=0.0,
        fov_h_rad=math.radians(90),
        frame_w=640,
        frame_h=480,
    )
    assert p is not None
    assert p.screen_x > 320
    assert p.angle_offset > 0


def test_circle_radius_closer_is_bigger():
    r_close = circle_radius(0.5)
    r_far = circle_radius(5.0)
    assert r_close > r_far


def test_circle_radius_bounds():
    assert circle_radius(0.01) <= 80.0
    assert circle_radius(100.0) >= 15.0


def test_projected_point_fields():
    pp = ProjectedPoint(screen_x=100, screen_y=200, distance=3.0, angle_offset=0.1)
    assert pp.screen_x == 100
    assert pp.distance == 3.0
