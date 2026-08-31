# -*- coding: utf-8 -*-
"""The legend's SUNK depths reaching the slab and the beam.

A sheet that hatches everything sunk says two different things with one legend
line. test14's is "INDICATES SLAB/BEAM SUNK BY 150MM." over one routed layer,
and under it sit BAYS of floor that step and STRIPS the width of a beam that
mean the member hangs lower. Everything here is pinned to that drawing:

  * the sunk bay at (85310, 43519), 3550 wide, in a 125 THK loop, which is the
    150 case -- and therefore the only one of the three depths that leaves a
    void for a support to fill;
  * the sunk strip at (92111, 33891), 149 x 1718, lying along the 300-wide beam
    whose centreline runs up x = 92261.6 -- a strip that does NOT contain the
    beam's centreline and is claimed by area, which is why the rule is areal;
  * the ANSI37 legend swatch at (101558.9, 14567.3), 1050 x 500 on HAT, which
    is a hatch on the routed layer carrying a priced pattern and must still
    build nothing;
  * the ANSI37 sunk BAY at (11801, 37519)-(14226, 38969), drawn from the far
    face of one 200-wide beam to the far face of the other, which is how a bay
    hatch says its beams go down with the floor.

The synthetic cases carry what the fixture cannot show: the void rule either
side of its own threshold, a member the segmentation cut into pieces under one
strip, and a beam two strips claim at two different depths.
"""

import ast
import os
import unittest

import _loader


fold_plan, layers = _loader.load("fold_plan", "classify.layers")

_MM = 304.8
_HERE = os.path.dirname(os.path.abspath(__file__))
_BUILDERS = os.path.normpath(os.path.join(_HERE, "..", "run_builders.py"))
_BEAMS = os.path.normpath(os.path.join(_HERE, "..", "builders", "beams.py"))
_SLABS = os.path.normpath(os.path.join(_HERE, "..", "builders", "slabs.py"))


def _ft(points):
    return [(x / _MM, y / _MM) for x, y in points]


def _mm(ring):
    return [(round(p[0] * _MM, 1), round(p[1] * _MM, 1)) for p in ring]


class _Hatch(object):
    """A hatch as the classifier leaves it: feet, a category and a pattern."""

    def __init__(self, points_mm, pattern, category=None):
        self.points = [(x / _MM, y / _MM, 0.0) for x, y in points_mm]
        self.pattern = pattern
        self.category = layers.CATEGORY_SUNK if category is None else category
        self.layer_key = "HAT"


def _box(x0, y0, x1, y1, pattern="ANGLE", category=None):
    return _Hatch([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], pattern, category)


def _loop(points_mm, thickness, mark=None):
    return {"ring": _ft(points_mm), "thickness_mm": thickness, "mark": mark,
            "arcs": []}


def _rect_loop(x0, y0, x1, y1, thickness, mark=None):
    return _loop([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], thickness, mark)


def _beam(x0, y0, x1, y1, width):
    return {"start": [x0 / _MM, y0 / _MM, 0.0], "end": [x1 / _MM, y1 / _MM, 0.0],
            "width_mm": width, "length_mm": abs(x1 - x0) + abs(y1 - y0)}


# The legend's own table, as `legend.legend_steps` returns it for test14:
# negative is down, and the fold machinery wants the magnitude.
_TEST14_DEPTHS = {"ANSI37": -75.0, "ANGLE": -150.0, "HONEY": -50.0}

# The bay at the north-west of test14's middle plan and the slab loop the beam
# faces gave it, both as drawn.
_BAY_85310 = [(85310.1, 44743.9), (88860.1, 44743.9), (88860.1, 44058.9),
              (88810.1, 44058.9), (88810.1, 43868.9), (88610.5, 43868.9),
              (88610.1, 43518.9), (85310.1, 43518.9)]
_LOOP_85860 = [(85860.1, 43518.9), (88410.9, 43518.9), (88810.1, 43518.9),
               (88810.1, 44058.9), (88810.1, 44693.9), (85360.1, 44693.9),
               (85360.1, 43518.9)]

# The strip up the east face of the same plan, and the beam it lies on.
_STRIP_92111 = [(92111.4, 33890.7), (92260.7, 33890.7), (92260.8, 35608.9),
                (92111.6, 35608.9)]
_BEAM_92261 = _beam(92261.6, 35608.9, 92261.6, 33897.4, 300.0)

# The ANSI37 row's demonstration swatch, in the legend block below the plans.
_SWATCH_ANSI37 = [(101558.9, 15067.3), (101558.9, 14567.3),
                  (102608.9, 14567.3), (102608.9, 15067.3)]


class WhatTheDrawingCalls(unittest.TestCase):
    """The bay/strip split, on the fixture's own rectangles."""

    def test_the_3550_wide_bay_is_a_bay(self):
        split = fold_plan.sunk_split([_Hatch(_BAY_85310, "ANGLE")],
                                     _TEST14_DEPTHS)
        self.assertEqual(len(split["bays"]), 1)
        self.assertEqual(split["strips"], [])

    def test_the_149_wide_strip_is_a_strip_and_keeps_its_depth(self):
        split = fold_plan.sunk_split([_Hatch(_STRIP_92111, "ANSI37")],
                                     _TEST14_DEPTHS)
        self.assertEqual(split["bays"], [])
        self.assertEqual([depth for _region, depth in split["strips"]], [75.0])

    def test_the_split_lands_between_the_two_measured_clusters(self):
        # 350 is the widest strip and 1007.4 the narrowest bay on test14; the
        # threshold has to separate them and nothing in between exists to
        # argue about.
        wide_strip = fold_plan.sunk_split([_box(0, 0, 4000, 350)],
                                          _TEST14_DEPTHS)
        narrow_bay = fold_plan.sunk_split([_box(0, 0, 4000, 1007.4)],
                                          _TEST14_DEPTHS)
        self.assertEqual(len(wide_strip["strips"]), 1)
        self.assertEqual(len(narrow_bay["bays"]), 1)

    def test_a_pattern_the_legend_does_not_price_is_refused_by_name(self):
        # test14's HAT layer also carries 72 GOST_GLASS hatches meaning "SLAB
        # AT BEAM BOTTOM", which is not a step at all.
        split = fold_plan.sunk_split(
            [_box(0, 0, 4000, 4000, pattern="GOST_GLASS"),
             _box(0, 0, 4000, 4000, pattern="GOST_GLASS")], _TEST14_DEPTHS)
        self.assertEqual(split["bays"], [])
        self.assertEqual(split["strips"], [])
        self.assertEqual(len(split["skipped"]), 1)
        self.assertIn("GOST_GLASS", split["skipped"][0])
        self.assertIn("2 hatch(es)", split["skipped"][0])

    def test_a_hatch_on_no_routed_layer_is_not_a_step_at_all(self):
        # The pattern says how deep; the CATEGORY says whether this layer was
        # routed as sunk in the first place. A column fill carrying a priced
        # pattern is neither.
        split = fold_plan.sunk_split(
            [_box(0, 0, 4000, 4000, category=layers.CATEGORY_COLUMN)],
            _TEST14_DEPTHS)
        self.assertEqual(split["bays"], [])
        self.assertEqual(split["strips"], [])
        self.assertEqual(split["skipped"], [])


class TheLegendsOwnSwatches(unittest.TestCase):
    """1050 x 500 on the routed layer, carrying a priced pattern -- and inert."""

    def test_the_swatch_is_dropped_before_anything_looks_at_it(self):
        swatch = _Hatch(_SWATCH_ANSI37, "ANSI37")
        split = fold_plan.sunk_split([swatch], _TEST14_DEPTHS,
                                     swatch_ids={id(swatch)})
        self.assertEqual(split["bays"], [])
        self.assertEqual(split["strips"], [])
        self.assertEqual(split["skipped"], [])

    def test_without_the_id_lock_the_swatch_would_read_as_a_strip(self):
        # 500 is under the bay threshold, so identity is what excludes it --
        # the same lock legend._plan_layers uses, and the reason it is passed
        # through rather than guessed at from the size.
        split = fold_plan.sunk_split([_Hatch(_SWATCH_ANSI37, "ANSI37")],
                                     _TEST14_DEPTHS)
        self.assertEqual(len(split["strips"]), 1)

    def test_the_second_lock_is_that_a_swatch_reaches_nothing(self):
        # Even unrecognised, a swatch sits in the legend block where there is
        # no slab loop to host it and no beam to claim.
        swatch = _Hatch(_SWATCH_ANSI37, "ANSI37")
        drops = fold_plan.beam_drops([_BEAM_92261], [(swatch, 75.0)])
        self.assertEqual(drops["drops"], {})
        steps = fold_plan.plan_steps(
            [_rect_loop(85360.1, 43518.9, 88810.1, 44693.9, 125.0)],
            [swatch], depths=_TEST14_DEPTHS)
        self.assertEqual(steps["steps"], [])
        self.assertEqual(len(steps["skipped"]), 1)
        self.assertIn("sits inside no outline", steps["skipped"][0])

    def test_plan_steps_refuses_a_swatch_by_id_as_well(self):
        swatch = _Hatch(_SWATCH_ANSI37, "ANSI37")
        steps = fold_plan.plan_steps(
            [_rect_loop(100000.0, 14000.0, 104000.0, 16000.0, 125.0)],
            [swatch], depths=_TEST14_DEPTHS, skip_ids={id(swatch)})
        self.assertEqual(steps["steps"], [])
        self.assertEqual(steps["skipped"], [])


class TheBayThatSteps(unittest.TestCase):
    """test14's 150 drop into a 125 slab: parent cut, floor dropped, void filled."""

    def _plan(self):
        return fold_plan.plan_steps([_loop(_LOOP_85860, 125.0)],
                                    [_Hatch(_BAY_85310, "ANGLE")],
                                    depths=_TEST14_DEPTHS)

    def test_the_bay_steps_at_the_legends_own_depth(self):
        steps = self._plan()["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["depth_mm"], 150.0)
        self.assertEqual(steps[0]["kind"], fold_plan.SUNK)

    def test_the_dropped_slab_hangs_by_the_depth_at_the_loops_thickness(self):
        dropped = self._plan()["steps"][0]["dropped"]
        self.assertEqual(dropped["offset_mm"], -150.0)
        self.assertEqual(dropped["thickness_mm"], 125.0)
        self.assertEqual(_mm(dropped["ring"]), [(round(x, 1), round(y, 1))
                                                for x, y in _BAY_85310])

    def test_the_parent_is_cut_where_the_bay_sits(self):
        step = self._plan()["steps"][0]
        self.assertIsNotNone(step["opening"])
        self.assertEqual(step["host_index"], 0)

    def test_the_150_drop_off_a_125_slab_leaves_a_void_to_fill(self):
        # d + T_dropped - T_parent = 150 + 125 - 125, hung at -T_parent. The
        # only one of test14's three depths deeper than the slab is thick.
        supports = self._plan()["steps"][0]["supports"]
        self.assertEqual(len(supports), 1)
        self.assertEqual(supports[0]["thickness_mm"], 150.0)
        self.assertEqual(supports[0]["offset_mm"], -125.0)


class TheVoidRuleEitherSideOfItself(unittest.TestCase):
    """75 and 50 into a 125 slab have nothing to fill; 150 has."""

    def _supports(self, depth):
        bay = _box(2000, 2000, 6000, 5000, pattern="ANGLE")
        plans = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        steps = fold_plan.plan_steps(plans, [bay], depths={"ANGLE": -depth})
        self.assertEqual(len(steps["steps"]), 1)
        return steps["steps"][0]["supports"]

    def test_a_75_drop_into_a_125_slab_gets_no_support(self):
        self.assertEqual(self._supports(75.0), [])

    def test_a_50_drop_into_a_125_slab_gets_no_support(self):
        self.assertEqual(self._supports(50.0), [])

    def test_a_150_drop_into_a_125_slab_gets_one_collar_round_the_bay(self):
        supports = self._supports(150.0)
        self.assertEqual(len(supports), 1)
        self.assertEqual(supports[0]["thickness_mm"], 150.0)
        self.assertEqual(supports[0]["offset_mm"], -125.0)
        # a closed collar: the bay itself is the hollow in it
        self.assertEqual(len(supports[0]["holes"]), 1)


class TheStripThatDropsABeam(unittest.TestCase):

    def test_the_strip_at_92111_drops_the_beam_it_lies_along(self):
        strip = _Hatch(_STRIP_92111, "ANSI37")
        drops = fold_plan.beam_drops([_BEAM_92261], [(strip, 75.0)])
        self.assertEqual(drops["drops"], {0: 75.0})
        self.assertEqual(drops["skipped"], [])

    def test_the_strip_does_not_contain_the_beams_centreline(self):
        # Why the claim is areal and not "the centreline runs through it": the
        # 300-wide beam's centreline sits at x = 92261.6 and the strip stops at
        # 92260.8, eight tenths of a millimetre short of it.
        xs = [x for x, _y in _STRIP_92111]
        self.assertLess(max(xs), 92261.6)

    def test_a_strip_over_part_of_a_beam_still_drops_all_of_it(self):
        # The user ruled out splitting the member, so a strip covering a metre
        # of a six-metre beam drops the whole six metres.
        beam = _beam(0, 0, 6000, 0, 300.0)
        strip = _box(1000, -150, 2000, 150, pattern="ANGLE")
        drops = fold_plan.beam_drops([beam], [(strip, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0})

    def test_a_strip_claims_every_segment_of_the_run_it_covers(self):
        # A member cut at its columns arrives as several segments, and the
        # strip over it holds only HALF of itself on each -- exactly on the
        # strip-share threshold, where a coin toss decides. The beam's own
        # share is what answers this: each segment is covered end to end.
        segments = [_beam(0, 0, 3000, 0, 300.0), _beam(3000, 0, 6000, 0, 300.0)]
        strip = _box(0, -150, 6000, 150, pattern="ANGLE")
        drops = fold_plan.beam_drops(segments, [(strip, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0, 1: 150.0})

    def test_a_strip_over_a_third_of_a_run_still_claims_every_piece(self):
        segments = [_beam(0, 0, 2000, 0, 300.0), _beam(2000, 0, 4000, 0, 300.0),
                    _beam(4000, 0, 6000, 0, 300.0)]
        strip = _box(0, -150, 6000, 150, pattern="ANGLE")
        drops = fold_plan.beam_drops(segments, [(strip, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0, 1: 150.0, 2: 150.0})

    def test_a_strip_beside_a_beam_claims_nothing_and_says_so(self):
        # The 150x100 patches left where a strip meets a column: touching the
        # beam's face, lying on none of it.
        beam = _beam(0, 0, 6000, 0, 200.0)
        patch = _box(1000, 100, 1150, 200, pattern="ANGLE")
        drops = fold_plan.beam_drops([beam], [(patch, 150.0)])
        self.assertEqual(drops["drops"], {})
        self.assertEqual(len(drops["skipped"]), 1)
        self.assertIn("lie on no beam", drops["skipped"][0])
        self.assertIn("ANGLE", drops["skipped"][0])

    def test_a_junction_clip_is_not_a_claim(self):
        # A strip running along one beam crosses the beam it tees into. The
        # crossing is a fifteenth of the strip; the desert this sits in runs
        # from 0.127 to 0.869.
        along = _beam(0, 0, 6000, 0, 200.0)
        crossing = _beam(3000, -3000, 3000, 3000, 200.0)
        strip = _box(0, -100, 3000, 100, pattern="ANGLE")
        drops = fold_plan.beam_drops([along, crossing], [(strip, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0})

    def test_a_beam_claimed_at_two_depths_takes_the_deeper_and_says_so(self):
        beam = _beam(0, 0, 6000, 0, 300.0)
        shallow = _box(0, -150, 2000, 150, pattern="ANSI37")
        deep = _box(4000, -150, 6000, 150, pattern="ANGLE")
        drops = fold_plan.beam_drops([beam], [(shallow, 75.0), (deep, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0})
        self.assertEqual(len(drops["skipped"]), 1)
        self.assertIn("two depths", drops["skipped"][0])

    def test_a_beam_with_no_width_has_no_body_to_claim(self):
        drops = fold_plan.beam_drops(
            [{"start": [0.0, 0.0, 0.0], "end": [0.0, 0.0, 0.0],
              "width_mm": 0.0}],
            [(_box(0, -150, 2000, 150, pattern="ANGLE"), 150.0)])
        self.assertEqual(drops["drops"], {})
        self.assertEqual(len(drops["skipped"]), 1)


class TheBayHatchThatDropsItsBeams(unittest.TestCase):
    """BUG-15's other half: "SLAB/BEAM SUNK BY 150MM" is one sentence.

    A sunk BAY's hatch is drawn OUT OVER the members bounding the bay rather
    than stopping at their faces, and since v0.84.0 made the bay's own ring the
    dropped slab, that overhang informs nothing else. Asked, it drops 249 more
    of test14's beams -- 12 by strips alone before this, 261 after.

    The bay is asked the BEAM's share only: it is many times any beam's area,
    so the strip's own share can never be true there.
    """

    def test_test14s_ANSI37_bay_at_11801_37519_drops_both_its_beams(self):
        # Verbatim from the fixture: a 2425 x 1450 sunk hatch drawn from the
        # far face of one 200-wide beam to the far face of the other, so each
        # beam lies WHOLLY inside it (share 1.0000, both).
        bay = _Hatch([(14225.8, 38968.9), (14225.8, 37518.9),
                      (11800.8, 37518.9), (11800.8, 38968.9)], "ANSI37")
        beams = [_beam(14125.8, 38968.9, 14125.8, 37518.9, 200.0),
                 _beam(11900.8, 38968.9, 11900.8, 37518.9, 200.0)]
        drops = fold_plan.beam_drops(beams, [], [(bay, 75.0)])
        self.assertEqual(drops["drops"], {0: 75.0, 1: 75.0})
        self.assertEqual(drops["skipped"], [])

    def test_a_bay_hatch_grazing_the_beam_next_door_claims_nothing(self):
        # 124 of the 385 overlapping (bay, beam) pairs on test14 are this: the
        # hatch's edge touching a beam's corner, 0.0000 .. 0.0005 of it.
        bay = _box(0, 0, 4000, 3000, pattern="ANGLE")
        outside = _beam(-2000, 3000, 6000, 3000, 200.0)   # touching the top
        drops = fold_plan.beam_drops([outside], [], [(bay, 150.0)])
        self.assertEqual(drops["drops"], {})

    def test_a_fifth_of_a_beam_under_a_bay_is_below_the_line(self):
        # The rims of the measured desert: 0.2012 refused, 0.6251 claimed,
        # with _BEAM_CLAIM_SHARE (0.3) between them.
        beam = _beam(0, 0, 5000, 0, 200.0)
        bay = _box(0, -100, 1000, 100, pattern="ANGLE")     # a fifth of it
        self.assertEqual(fold_plan.beam_drops([beam], [], [(bay, 150.0)])
                         ["drops"], {})
        bay = _box(0, -100, 3125, 100, pattern="ANGLE")     # 0.625 of it
        self.assertEqual(fold_plan.beam_drops([beam], [], [(bay, 150.0)])
                         ["drops"], {0: 150.0})

    def test_a_bay_that_claims_no_beam_is_not_reported_as_stranded(self):
        # A strip on no member is a strip nobody read; a bay hatch over no
        # member is an ordinary bay in the middle of a plate. Only the strip
        # is named.
        bay = _box(0, 0, 4000, 3000, pattern="ANGLE")
        drops = fold_plan.beam_drops([_beam(9000, 9000, 12000, 9000, 200.0)],
                                     [], [(bay, 150.0)])
        self.assertEqual(drops["skipped"], [])

    def test_the_strip_and_the_bay_reach_the_same_beam_and_it_drops_once(self):
        beam = _beam(0, 0, 6000, 0, 200.0)
        strip = _box(0, -100, 6000, 100, pattern="ANSI37")
        bay = _box(0, -100, 6000, 3000, pattern="ANSI37")
        drops = fold_plan.beam_drops([beam], [(strip, 75.0)], [(bay, 75.0)])
        self.assertEqual(drops["drops"], {0: 75.0})
        self.assertEqual(drops["skipped"], [])

    def test_a_beam_a_strip_and_a_bay_price_differently_takes_the_deeper(self):
        beam = _beam(0, 0, 6000, 0, 200.0)
        strip = _box(0, -100, 6000, 100, pattern="ANSI37")
        bay = _box(0, -100, 6000, 3000, pattern="ANGLE")
        drops = fold_plan.beam_drops([beam], [(strip, 75.0)], [(bay, 150.0)])
        self.assertEqual(drops["drops"], {0: 150.0})
        self.assertEqual(len(drops["skipped"]), 1)
        self.assertIn("two depths", drops["skipped"][0])

    def test_no_bays_at_all_is_the_call_the_old_one_made(self):
        strip = _Hatch(_STRIP_92111, "ANSI37")
        self.assertEqual(fold_plan.beam_drops([_BEAM_92261], [(strip, 75.0)]),
                         fold_plan.beam_drops([_BEAM_92261], [(strip, 75.0)],
                                              None))


class TheProfilesTheBuilderGets(unittest.TestCase):
    """`slab_defs_with_steps`: what Floor.Create is finally handed."""

    def _stepped(self, bay, loops):
        steps = fold_plan.plan_steps(loops, [bay], depths=_TEST14_DEPTHS)
        return fold_plan.slab_defs_with_steps(loops, steps["steps"])

    def test_a_bay_inside_its_loop_becomes_a_hole_and_a_dropped_floor(self):
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        defs, notes = self._stepped(_box(2000, 2000, 6000, 5000), loops)
        parents = [d for d in defs if not d.get("part")]
        self.assertEqual(len(parents), 1)
        self.assertEqual(len(parents[0]["holes"]), 1)
        self.assertEqual(notes, [])
        parts = [d for d in defs if d.get("part")]
        self.assertEqual([d["part"] for d in parts], ["sunk", "support"])
        self.assertEqual([d["offset_mm"] for d in parts], [-150.0, -125.0])
        self.assertEqual([d["mark"] for d in parts], ["S1-SUNK", "S1-SUPPORT"])

    def test_a_bay_reaching_the_loops_edge_divides_it_instead(self):
        # A hole sharing two edges with its outline is a profile Floor.Create
        # refuses; the concrete truth is two pieces with the drop between.
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        defs, notes = self._stepped(_box(0, 3000, 8000, 5000), loops)
        parents = [d for d in defs if not d.get("part")]
        self.assertEqual(len(parents), 2)
        self.assertEqual(len(notes), 1)
        self.assertIn("divided into 2 piece(s)", notes[0])

    def test_a_loop_the_bay_covers_end_to_end_is_not_placed_flat(self):
        loops = [_rect_loop(100, 100, 7900, 7900, 125.0, mark="S1")]
        defs, notes = self._stepped(_box(0, 0, 8000, 8000), loops)
        self.assertEqual([d for d in defs if not d.get("part")], [])
        self.assertEqual(len(notes), 1)
        self.assertIn("wholly covered", notes[0])

    def test_a_loop_the_drawing_marks_sunk_entire_drops_whole(self):
        # The region IS the loop: there is nothing to cut, and placing the
        # parent flat as well would be a second floor in the same place.
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        defs, _notes = self._stepped(_box(0, 0, 8000, 8000), loops)
        self.assertEqual([d for d in defs if not d.get("part")], [])
        self.assertEqual([d["part"] for d in defs], ["sunk"])
        self.assertEqual(defs[0]["offset_mm"], -150.0)

    def test_a_loop_no_bay_touches_comes_through_untouched(self):
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1"),
                 _rect_loop(9000, 0, 17000, 8000, 125.0, mark="S2")]
        defs, _notes = self._stepped(_box(2000, 2000, 6000, 5000), loops)
        self.assertIs([d for d in defs if d.get("mark") == "S2"][0], loops[1])

    def test_a_divided_piece_drops_the_arcs_of_the_ring_it_is_not(self):
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        loops[0]["arcs"] = [((0.0, 0.0), (1.0, 1.0), (2.0, 0.0))]
        defs, _notes = self._stepped(_box(0, 3000, 8000, 5000), loops)
        for parent in [d for d in defs if not d.get("part")]:
            self.assertEqual(parent["arcs"], [])

    def test_the_step_parts_never_carry_a_stale_arc(self):
        loops = [_rect_loop(0, 0, 8000, 8000, 125.0, mark="S1")]
        loops[0]["arcs"] = [((0.0, 0.0), (1.0, 1.0), (2.0, 0.0))]
        defs, _notes = self._stepped(_box(2000, 2000, 6000, 5000), loops)
        for part in [d for d in defs if d.get("part")]:
            self.assertEqual(part["arcs"], [])


class TheFoundationPathIsUntouched(unittest.TestCase):
    """`plan_steps` without `depths` still reads the host's own note."""

    def test_a_note_still_gives_the_depth_when_no_table_is_handed_in(self):
        plan = {"ring": _ft([(0, 0), (8000, 0), (8000, 8000), (0, 8000)]),
                "thickness_mm": 750.0, "mark": "F3",
                "steps": [{"step_mm": 1000.0, "step_kind": fold_plan.SUNK,
                           "point": (4000 / _MM, 3500 / _MM, 0.0)}]}
        steps = fold_plan.plan_steps([plan], [_box(2000, 2000, 6000, 5000,
                                                   category=layers.CATEGORY_SUNK)])
        self.assertEqual(len(steps["steps"]), 1)
        self.assertEqual(steps["steps"][0]["depth_mm"], 1000.0)

    def test_the_pattern_is_ignored_entirely_when_no_table_is_handed_in(self):
        # A foundation drawing names its layers; the pattern on its hatches is
        # whatever the drafter picked and must not start refusing steps.
        plan = {"ring": _ft([(0, 0), (8000, 0), (8000, 8000), (0, 8000)]),
                "thickness_mm": 750.0, "mark": "F3",
                "steps": [{"step_mm": 300.0, "step_kind": fold_plan.FOLD,
                           "point": (4000 / _MM, 3500 / _MM, 0.0)}]}
        fold = _box(2000, 2000, 6000, 5000, pattern="A-PATTERN-NOBODY-PRICED",
                    category=layers.CATEGORY_FOLD)
        steps = fold_plan.plan_steps([plan], [fold])
        self.assertEqual(len(steps["steps"]), 1)
        self.assertEqual(steps["skipped"], [])

    def test_step_regions_still_answers_in_pairs(self):
        rows = fold_plan.step_regions([_box(0, 0, 100, 100)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 2)


def _source(path):
    with open(path) as handle:
        return handle.read()


def _function(source, name):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


class TheWiringOnTheRevitSide(unittest.TestCase):
    """builders/* import Revit at module level, so these are static reads.

    Everything below is a seam that only fails inside Revit: a builder that
    never receives the drops, or a step part quietly nested as somebody's
    hole, looks exactly like a correct run from out here.
    """

    def test_place_beams_takes_the_drops_and_sinks_by_z_offset_value(self):
        source = _source(_BEAMS)
        node = _function(source, "place_beams")
        self.assertIsNotNone(node)
        self.assertIn("drops", [argument.arg for argument in node.args.args])
        self.assertIn("problem = _sink(instance, drop_mm)", source)

    def test_the_driving_line_stays_on_the_level(self):
        # The owner's instruction, verbatim: "its sunk value should use Z
        # Offset Value only for sunk or rise not the Start/End Level Offset."
        # A curve laid below the level IS the Start/End Level Offset pair
        # their properties palette showed at 0.000, so it must not come back.
        source = _source(_BEAMS)
        self.assertIn("Line.CreateBound(XYZ(sx, sy, elevation),", source)
        self.assertNotIn("elevation - mm_to_internal(drop_mm)", source)

    def test_the_sink_is_negative_so_the_beam_goes_DOWN(self):
        # z Offset Value counts along the model's +Z from whatever datum z
        # Justification names -- Top in the owner's screenshot -- so down is
        # negative and a legend row pricing a RISE comes out positive.
        source = _source(_BEAMS)
        node = _function(source, "_sink")
        self.assertIsNotNone(node)
        self.assertIn("BuiltInParameter.Z_OFFSET_VALUE", source)
        self.assertIn("parameter.Set(-mm_to_internal(drop_mm))", source)

    def test_a_z_offset_that_will_not_take_is_reported_not_swallowed(self):
        # A beam left at its level looks placed and is a step too high.
        source = _source(_BEAMS)
        self.assertIn('result["skipped"].append(problem)', source)
        self.assertIn("could not sink a beam by", source)

    def test_the_beam_pass_hands_the_drops_to_the_builder(self):
        source = _source(_BUILDERS)
        self.assertIn("beams.place_beams(doc, segments, beam_id, level_id, "
                      "drops=drops)", source)

    def test_the_beam_pass_asks_the_bay_hatches_as_well_as_the_strips(self):
        source = _source(_BUILDERS)
        self.assertIn('fold_plan.beam_drops(segments, split["strips"], '
                      'split["bays"])', source)

    def test_the_slab_stop_pass_is_handed_the_sheets_texts(self):
        # The CUTOUT label lives on its own layer, and the slab-note routing
        # cannot be trusted to still hold it (BUG-16).
        source = _source(_BUILDERS)
        self.assertIn("sheet_texts=sheet_texts", source)

    def test_the_beam_pass_takes_the_hatches_and_the_sheets_texts(self):
        node = _function(_source(_BUILDERS), "_create_beams")
        self.assertIsNotNone(node)
        names = [argument.arg for argument in node.args.args]
        self.assertIn("regions", names)
        self.assertIn("texts", names)

    def test_the_slab_pass_takes_the_hatches_and_the_sheets_texts(self):
        node = _function(_source(_BUILDERS), "_create_slabs")
        self.assertIsNotNone(node)
        names = [argument.arg for argument in node.args.args]
        self.assertIn("regions", names)
        self.assertIn("sheet_texts", names)

    def test_the_slab_builder_keeps_the_step_parts_out_of_the_nesting(self):
        # A dropped slab lies wholly inside its parent, which is the shape of
        # a stair void: nested, the floor at the bottom of the step becomes a
        # hole in the floor above it.
        source = _source(_SLABS)
        self.assertIn('_nest_openings([s for s in slabs if not s.get("part")])',
                      source)

    def test_the_slab_builder_offsets_what_carries_an_offset(self):
        source = _source(_SLABS)
        self.assertIn('_offset(instance, slab.get("offset_mm"))', source)
        self.assertIn("FLOOR_HEIGHTABOVELEVEL_PARAM", source)

    def test_the_slab_builder_cuts_the_holes_the_plan_worked_out(self):
        source = _source(_SLABS)
        self.assertIn('slab.get("holes")', source)

    def test_both_passes_read_the_dialogs_table_before_the_legend(self):
        source = _source(_BUILDERS)
        self.assertIn('selections.get("hatch_step_depths")', source)
        node = _function(source, "_sunk_depths")
        self.assertIsNotNone(node)


if __name__ == "__main__":
    unittest.main()
