"""
Tests for cool_cli.banner.

The banner module contains helper functions to produce a colour
gradient and print an ASCII banner.  We test that the colour
interpolator returns endpoints correctly and that it blends
intermediate values smoothly.
"""

import cool_cli.coolcli.banner as banner


def test_interpolate_color_endpoints():
    stops = [(0, 0, 0), (255, 255, 255)]
    # At t=0, expect first colour
    assert banner.interpolate_color(stops, 0) == (0, 0, 0)
    # At t=1, expect last colour
    assert banner.interpolate_color(stops, 1) == (255, 255, 255)


def test_interpolate_color_midpoint():
    stops = [(0, 0, 0), (255, 255, 255)]
    # At t=0.5, expect approximate midpoint
    mid = banner.interpolate_color(stops, 0.5)
    # Each component should be roughly half of 255
    for c in mid:
        assert 120 <= c <= 135