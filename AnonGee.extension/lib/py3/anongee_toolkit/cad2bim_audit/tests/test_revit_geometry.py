# -*- coding: utf-8 -*-
"""Stage B: what Revit made of the linked DXF.

Run against the stub in `_revit_stub.py`, which is the only way this module can
be exercised anywhere but inside Revit -- and before the stub existed it had
never executed at all, which is exactly backwards: the reader that cannot be run
on a developer's machine is the one most in need of a test.

The assertions fall into two groups. What the reader must SEE (solids, meshes,
points, nested instances, unbound curves) and what it must SAY about it -- the
notes are load-bearing here, because for stage B the finding is usually not
"this is missing" but "cad2bim never looked at this".
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402
import _revit_stub as R                               # noqa: E402

geometry_reader = _loader.load_revit("readers.revit_geometry")
config, space, model = _loader.load("config", "space", "model")

FT = 1.0 / 304.8            # millimetres to Revit's internal feet


def space_1to1():
    """A link whose DXF millimetres map straight onto Revit feet."""
    return space.Space(1.0, [[FT, 0, 0, 0], [0, FT, 0, 0], [0, 0, FT, 0]],
                       method="link_transform")


def read(objects, doc=None):
    doc = doc or R.Document()
    link = R.ImportInstance(objects, transform=R.Transform())
    return geometry_reader.read_raw(doc, link, space_1to1())


class CurveTests(unittest.TestCase):

    def test_a_line_keeps_its_two_endpoints(self):
        capture = read([R.line((0, 0, 0), (10, 0, 0))])
        item = capture.items[0]
        self.assertEqual(item.kind, "curve")
        self.assertEqual(len(item.points), 2)
        self.assertIs(item.extra["cad2bim_reads"], True)

    def test_an_arc_keeps_start_mid_and_end(self):
        """The same three points cad2bim keeps, so lengths stay comparable."""
        capture = read([R.arc((0, 0, 0), (1, 1, 0), (2, 0, 0))])
        self.assertEqual(len(capture.items[0].points), 3)

    def test_a_polyline_keeps_every_vertex(self):
        capture = read([R.polyline([(0, 0, 0), (1, 0, 0), (1, 1, 0)])])
        self.assertEqual(len(capture.items[0].points), 3)

    def test_a_closed_unbound_curve_is_tessellated_not_dropped(self):
        """A full circle has no endpoints; it is still a column footprint."""
        circle = R.unbound_circle([(0, 0, 0), (1, 1, 0), (2, 0, 0), (1, -1, 0)])
        capture = read([circle])
        self.assertEqual(len(capture.items[0].points), 4)

    def test_an_infinite_line_is_recorded_as_one_cad2bim_skips(self):
        capture = read([R.unbound_line()])
        item = capture.items[0]
        self.assertEqual(item.points, [])
        self.assertIs(item.extra["cad2bim_reads"], False)
        self.assertTrue(any("unbound" in note for note in item.notes))

    def test_coordinates_arrive_in_both_spaces(self):
        capture = read([R.line((0, 0, 0), (10, 0, 0))])
        item = capture.items[0]
        self.assertEqual(item.native_space, "revit")
        self.assertAlmostEqual(item.points_revit[1][0], 3048.0)   # 10 ft in mm
        self.assertAlmostEqual(item.points_dxf[1][0], 3048.0)     # 1:1 link


class IgnoredGeometryTests(unittest.TestCase):
    """The heart of stage B: what cad2bim's geometry_reader never looks at."""

    def test_solids_meshes_and_points_are_read_and_marked_as_lost(self):
        capture = read([
            R.solid_box((0, 0, 0), (2, 3, 1), volume=6.0),
            R.Mesh(vertices=[(0, 0, 0), (1, 0, 0), (1, 1, 0)], triangles=1),
            R.Point((5, 5, 0)),
        ])
        self.assertEqual([item.kind for item in capture.items],
                         ["solid", "mesh", "point"])
        for item in capture.items:
            self.assertIs(item.extra["cad2bim_reads"], False)
            self.assertTrue(any("intentionally ignored" in note
                                for note in item.notes))

    def test_a_mesh_reports_its_triangle_count(self):
        capture = read([R.Mesh(vertices=[(0, 0, 0)] * 6, triangles=2)])
        self.assertEqual(capture.items[0].extra["triangle_count"], 2)


class ImportedHatchTests(unittest.TestCase):
    """An imported hatch is a flat solid, and its shape has to survive."""

    def _hatch(self, holes=()):
        outline = [(0, 0, 0), (3000 * FT, 0, 0),
                   (3000 * FT, 3000 * FT, 0), (0, 3000 * FT, 0)]
        return R.flat_solid(outline, holes=holes, volume=0.0)

    def test_the_footprint_is_a_ring_in_order_not_a_cloud_of_edges(self):
        """Four vertices, once each. The edge fallback returns eight, unordered.

        The distinction matters because the whole point of reading the solid is
        to compare its SHAPE against the hatch boundary that produced it, and a
        cloud of points has no shape.
        """
        item = read([self._hatch()]).items[0]
        self.assertEqual(item.extra["outline_source"], "planar_face")
        self.assertEqual(len(item.points), 4)
        self.assertAlmostEqual(item.area_mm2, 9.0e6, delta=1.0)

    def test_a_flat_solid_is_identified_as_a_face_rather_than_a_body(self):
        item = read([self._hatch()]).items[0]
        self.assertIs(item.extra["is_flat"], True)
        body = read([R.solid_box((0, 0, 0), (2, 3, 1), volume=6.0)]).items[0]
        self.assertIs(body.extra["is_flat"], False)

    def test_holes_in_the_footprint_are_counted(self):
        """The Revit-side counterpart of a DXF hatch's islands."""
        hole = [(1000 * FT, 1000 * FT, 0), (2000 * FT, 1000 * FT, 0),
                (2000 * FT, 2000 * FT, 0), (1000 * FT, 2000 * FT, 0)]
        item = read([self._hatch(holes=[hole])]).items[0]
        self.assertEqual(item.extra["hole_count"], 1)
        self.assertEqual(item.extra["loop_count"], 2)
        self.assertTrue(any("hole" in note for note in item.notes))

    def test_a_solid_with_no_planar_face_says_its_outline_is_unusable(self):
        item = read([R.solid_box((0, 0, 0), (2, 3, 1), volume=6.0)]).items[0]
        self.assertEqual(item.extra["outline_source"], "edge_cloud")
        self.assertTrue(any("cannot be compared" in note for note in item.notes))


class NestingTests(unittest.TestCase):

    def test_nested_instance_geometry_is_read(self):
        capture = read([R.GeometryInstance([R.line((20, 0, 0), (21, 0, 0))])])
        self.assertEqual(len(capture.items), 1)
        self.assertEqual(capture.items[0].extra["depth"], 1)
        self.assertEqual(capture.meta["max_depth_seen"], 1)

    def test_nesting_recurses_more_than_one_level(self):
        deep = R.GeometryInstance([R.GeometryInstance([
            R.line((0, 0, 0), (1, 0, 0))])])
        capture = read([deep])
        self.assertEqual(capture.items[0].extra["depth"], 2)


class LayerTests(unittest.TestCase):

    def test_the_cad_layer_resolves_through_the_graphics_style(self):
        doc = R.Document()
        style = doc.register_layer("S-COLS")
        capture = read([R.line((0, 0, 0), (1, 0, 0), style_id=style)], doc)
        self.assertEqual(capture.items[0].layer, "S-COLS")

    def test_geometry_with_no_style_reports_no_layer_rather_than_failing(self):
        capture = read([R.line((0, 0, 0), (1, 0, 0))])
        self.assertIsNone(capture.items[0].layer)
        self.assertEqual(capture.items[0].layer_key, model.NO_LAYER)


class RobustnessTests(unittest.TestCase):

    def test_a_missing_document_or_link_is_an_error_row_not_a_crash(self):
        capture = geometry_reader.read_raw(None, None, space_1to1())
        self.assertEqual(capture.items, [])
        self.assertEqual(len(capture.errors), 1)

    def test_a_link_with_no_geometry_is_recorded(self):
        class Empty(object):
            def get_Geometry(self, _options):
                return None
        capture = geometry_reader.read_raw(R.Document(), Empty(), space_1to1())
        self.assertEqual(len(capture.errors), 1)

    def test_one_broken_object_costs_one_row_not_the_rest_of_the_link(self):
        """cad2bim's reader would lose the lot; here the failure is a row."""
        class Exploding(object):
            """Every attribute access raises -- the worst an import can offer."""
            @property
            def GraphicsStyleId(self):
                raise Exception("boom")
        capture = read([R.line((0, 0, 0), (1, 0, 0)), Exploding(),
                        R.line((2, 0, 0), (3, 0, 0))])
        self.assertEqual(len(capture.items), 3)     # the odd one still recorded
        self.assertEqual(capture.errors, [])        # guarded, so nothing raised


class ParsedPassTests(unittest.TestCase):
    """The other half of stage B: the link as cad2bim's own reader sees it."""

    class FakeRecord(object):
        def __init__(self, kind, points, layer, length_ft=None):
            self.kind = kind
            self.points = points
            self.layer = layer
            self.length_ft = length_ft
            self.category = None

    class FakeResult(object):
        def __init__(self, records):
            self.source_name = "link"
            self.records = records

    def test_records_become_items_in_both_spaces(self):
        record = self.FakeRecord("line", [(0, 0, 0), (10, 0, 0)], "S-COLS",
                                 length_ft=10.0)
        module = type("M", (), {
            "read_link": staticmethod(lambda doc, inst: self.FakeResult([record]))})
        capture = geometry_reader.read_parsed(R.Document(), object(),
                                              space_1to1(), reader=module)
        item = capture.items[0]
        self.assertEqual(item.stage, config.STAGE_LINK_PARSED)
        self.assertEqual(item.layer, "S-COLS")
        self.assertAlmostEqual(item.extra["length_mm"], 3048.0)
        self.assertAlmostEqual(item.points_revit[1][0], 3048.0)

    def test_a_reader_that_raises_is_an_error_row(self):
        def boom(doc, inst):
            raise RuntimeError("no")
        module = type("M", (), {"read_link": staticmethod(boom)})
        capture = geometry_reader.read_parsed(R.Document(), object(),
                                              space_1to1(), reader=module)
        self.assertEqual(capture.items, [])
        self.assertEqual(len(capture.errors), 1)


if __name__ == "__main__":
    unittest.main()
