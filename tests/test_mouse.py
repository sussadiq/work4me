# tests/test_mouse.py
import math
import pytest
from work4me.behavior.mouse import HumanMouse, Point

def test_point_distance():
    a = Point(0, 0)
    b = Point(3, 4)
    assert abs(a.distance_to(b) - 5.0) < 0.001

def test_bezier_path_has_endpoints():
    mouse = HumanMouse()
    start = Point(0, 0)
    end = Point(100, 200)
    path = mouse.bezier_path(start, end)
    assert len(path) >= 2
    assert abs(path[0].x - start.x) < 1
    assert abs(path[0].y - start.y) < 1
    assert abs(path[-1].x - end.x) < 5  # allow overshoot correction
    assert abs(path[-1].y - end.y) < 5

def test_bezier_path_length_scales_with_distance():
    mouse = HumanMouse()
    short_path = mouse.bezier_path(Point(0, 0), Point(10, 10))
    long_path = mouse.bezier_path(Point(0, 0), Point(1000, 1000))
    assert len(long_path) > len(short_path)

def test_fitts_duration_positive():
    mouse = HumanMouse()
    dur = mouse.fitts_duration(distance=500, target_width=50)
    assert dur > 0

def test_fitts_duration_larger_for_small_targets():
    mouse = HumanMouse()
    dur_small = mouse.fitts_duration(distance=500, target_width=10)
    dur_large = mouse.fitts_duration(distance=500, target_width=100)
    assert dur_small > dur_large

def test_micro_movement_small():
    mouse = HumanMouse()
    p = mouse.micro_movement(Point(500, 500))
    assert abs(p.x - 500) < 20
    assert abs(p.y - 500) < 20
