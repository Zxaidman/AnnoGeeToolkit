# -*- coding: utf-8 -*-
"""Stage C: what is actually in the model.

Like stage B, this had never executed outside Revit before the stub existed.
The assertions concentrate on the two things a sweep can most easily get wrong
and never notice: the SHAPE it reports for a member, and the SILENCE it keeps
about a member it could not read.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402
import _revit_stub as R                               # noqa: E402

elements_reader = _loader.load_revit("readers.revit_elements")
config, space = _loader.load("config", "space")

FT = 1.0 / 304.8


def space_1to1():
    return space.Space(1.0, [[FT, 0, 0, 0], [0, FT, 0, 0], [0, 0, FT, 0]],
                       method="link_transform")


def square(size_mm, at=(0.0, 0.0)):
    half = size_mm * FT / 2.0
    return [(at[0] - half, at[1] - half, 0.0), (at[0] + half, at[1] - half, 0.0),
            (at[0] + half, at[1] + half, 0.0), (at[0] - half, at[1] + half, 0.0)]


def turned(points, degrees):
    radians = math.radians(degrees)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return [(x * cos_a - y * sin_a, x * sin_a + y * cos_a, z) for x, y, z in points]


def sweep(by_category, extra_elements=()):
    document = R.Document("test model", by_category=by_category)
    for element in extra_elements:
        document.register(element)
    return elements_reader.read(document, space_1to1())


class FootprintTests(unittest.TestCase):
    """A bounding box is not a shape. These pin the difference."""

    def test_a_rotated_column_reports_its_real_section(self):
        """A 400x400 at 45 degrees measures 566x566 inside an axis-aligned box.

        Reported that way, the audit either flags every rotated column in the
        plan as 166 mm oversized or stops checking sizes at all.
        """
        column = R.shaped_column(1, turned(square(400), 45), b_mm=400, h_mm=400,
                                 rotation=math.radians(45))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertEqual(item.extra["footprint_source"], "planar_face")
        short, long_side = item.plan_size_mm
        self.assertAlmostEqual(short, 400.0, delta=0.5)
        self.assertAlmostEqual(long_side, 400.0, delta=0.5)

    def test_an_l_shaped_slab_reports_its_real_area(self):
        """Its enclosing rectangle is a third bigger than the slab."""
        outline = [(0, 0, 0), (6000 * FT, 0, 0), (6000 * FT, 3000 * FT, 0),
                   (3000 * FT, 3000 * FT, 0), (3000 * FT, 6000 * FT, 0),
                   (0, 6000 * FT, 0)]
        slab = R.floor(3, outline, thickness_mm=200)
        item = sweep({R.BuiltInCategory.OST_Floors: [slab]}).items[0]
        self.assertAlmostEqual(item.area_mm2 / 1.0e6, 27.0, places=1)

    def test_an_opening_is_counted_and_taken_out_of_the_area(self):
        """A hole in a slab is a hole in the thing, not in its hatching."""
        outline = square(6000)
        opening = square(1000, at=(1000 * FT, 1000 * FT))
        slab = R.floor(3, outline, openings=[opening], thickness_mm=200)
        item = sweep({R.BuiltInCategory.OST_Floors: [slab]}).items[0]
        self.assertEqual(item.extra["hole_count"], 1)
        self.assertAlmostEqual(item.extra["gross_area_mm2"] / 1.0e6, 36.0, places=1)
        self.assertAlmostEqual(item.extra["area_mm2"] / 1.0e6, 35.0, places=1)
        self.assertTrue(any("opening" in note for note in item.notes))

    def test_an_element_with_no_readable_geometry_falls_back_to_its_box(self):
        column = R.column(1, (0, 0, 0), (400 * FT, 400 * FT, 3000 * FT),
                          b_mm=400, h_mm=400)
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertEqual(item.extra["footprint_source"], "bounding_box")
        self.assertAlmostEqual(item.plan_size_mm[0], 400.0, delta=0.5)

    def test_a_fallback_box_on_a_rotated_member_says_it_cannot_be_trusted(self):
        column = R.column(1, (0, 0, 0), (566 * FT, 566 * FT, 3000 * FT),
                          b_mm=400, h_mm=400, rotation=math.radians(45))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertTrue(any("over-reports" in note for note in item.notes))

    def test_a_real_footprint_carries_no_such_caveat(self):
        column = R.shaped_column(1, turned(square(400), 45), b_mm=400, h_mm=400,
                                 rotation=math.radians(45))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertFalse([note for note in item.notes if "over-reports" in note])


class ElementFactTests(unittest.TestCase):

    def test_identity_and_type_are_recorded(self):
        level = R.level(70, "FIRST FLOOR")
        column = R.shaped_column(1, square(400), mark="C1", level=level,
                                 b_mm=400, h_mm=400)
        capture = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]},
                        extra_elements=[level])
        item = capture.items[0]
        self.assertEqual(item.handle, "1")
        self.assertEqual(item.mark, "C1")
        self.assertEqual(item.level, "FIRST FLOOR")
        self.assertEqual(item.type_name, "Concrete-Rectangular: C 400x400")
        self.assertEqual(item.extra["family"], "Concrete-Rectangular")
        self.assertEqual(item.extra["revit_category"], "Structural Columns")

    def test_section_comes_from_the_type_parameters(self):
        column = R.shaped_column(1, square(400), b_mm=400, h_mm=750)
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertAlmostEqual(item.extra["type_b_mm"], 400.0, places=3)
        self.assertAlmostEqual(item.extra["type_h_mm"], 750.0, places=3)

    def test_a_beam_takes_its_heading_from_its_location_curve(self):
        """A horizontal beam's box is degenerate in plan; its curve is not."""
        beam = R.beam(4, (0, 0, 0), (6000 * FT, 6000 * FT, 0))
        item = sweep({R.BuiltInCategory.OST_StructuralFraming: [beam]}).items[0]
        self.assertAlmostEqual(item.extra["rotation_deg"], 45.0, places=3)
        self.assertAlmostEqual(item.extra["length_mm"], 8485.3, delta=1.0)

    def test_a_column_takes_its_rotation_from_its_location_point(self):
        column = R.shaped_column(1, square(400), rotation=math.radians(30))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertAlmostEqual(item.extra["rotation_deg"], 30.0, places=3)

    def test_constraints_are_read_where_the_family_carries_them(self):
        """A member on the right storey with a 3 m offset is on the wrong one."""
        top = R.level(71, "SECOND FLOOR")
        column = R.shaped_column(1, square(400))
        column._builtins.update({
            R.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM:
                R.Parameter(top.Id, R.StorageType.ElementId),
            R.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM:
                R.Parameter(3000 * FT),
        })
        capture = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]},
                        extra_elements=[top])
        item = capture.items[0]
        self.assertEqual(item.extra["top_level"], "SECOND FLOOR")
        self.assertAlmostEqual(item.extra["base_offset_mm"], 3000.0, places=3)

    def test_positions_arrive_in_both_spaces(self):
        column = R.shaped_column(1, square(400, at=(3048.0 * FT, 0.0)))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [column]}).items[0]
        self.assertAlmostEqual(item.centroid_revit[0], 3048.0, delta=1.0)
        self.assertAlmostEqual(item.centroid_dxf[0], 3048.0, delta=1.0)


class SweepTests(unittest.TestCase):

    def test_categories_map_onto_the_audit_s_own_vocabulary(self):
        column = R.shaped_column(1, square(400))
        beam = R.beam(2, (0, 0, 0), (1, 0, 0))
        slab = R.floor(3, square(3000))
        capture = sweep({
            R.BuiltInCategory.OST_StructuralColumns: [column],
            R.BuiltInCategory.OST_StructuralFraming: [beam],
            R.BuiltInCategory.OST_Floors: [slab],
        })
        self.assertEqual(sorted(item.category for item in capture.items),
                         ["beam", "column", "slab_edge"])

    def test_grids_and_levels_are_datums_rather_than_members(self):
        capture = sweep({R.BuiltInCategory.OST_Grids: [R.level(1, "A")],
                         R.BuiltInCategory.OST_Levels: [R.level(2, "L1")]})
        self.assertEqual(set(item.kind for item in capture.items), {"datum"})

    def test_a_category_absent_from_this_revit_version_is_skipped_not_fatal(self):
        capture = elements_reader.read(R.Document(), space_1to1(),
                                       categories=("OST_NoSuchThing",))
        self.assertEqual(capture.items, [])
        self.assertIn("OST_NoSuchThing", capture.skipped)
        self.assertEqual(capture.errors, [])

    def test_the_swept_categories_are_recorded_for_the_report(self):
        capture = sweep({})
        self.assertEqual(capture.meta["categories_swept"],
                         list(config.MODEL_CATEGORIES))

    def test_no_document_is_an_error_row_not_a_crash(self):
        capture = elements_reader.read(None, space_1to1())
        self.assertEqual(len(capture.errors), 1)

    def test_an_unreadable_element_still_gets_a_row_and_admits_it(self):
        """Guarded to the point that nothing is dropped -- which is right.

        But guarded that thoroughly, a total failure would otherwise look like a
        successful read of an empty element. The row exists to say the element
        is there; the note says not to believe anything else on it.
        """
        class Broken(object):
            @property
            def Id(self):
                raise Exception("boom")
        good = R.shaped_column(1, square(400))
        capture = sweep({R.BuiltInCategory.OST_StructuralColumns: [good, Broken()]})
        self.assertEqual(len(capture.items), 2)
        unreadable = [item for item in capture.items if item.handle is None]
        self.assertEqual(len(unreadable), 1)
        self.assertTrue(any("id could not be read" in note
                            for note in unreadable[0].notes))

    def test_a_readable_element_carries_no_such_warning(self):
        good = R.shaped_column(1, square(400))
        item = sweep({R.BuiltInCategory.OST_StructuralColumns: [good]}).items[0]
        self.assertEqual(item.handle, "1")
        self.assertFalse([n for n in item.notes if "id could not be read" in n])


if __name__ == "__main__":
    unittest.main()
