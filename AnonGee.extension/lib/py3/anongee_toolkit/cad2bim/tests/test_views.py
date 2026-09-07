# -*- coding: utf-8 -*-
"""Which view the run links into, which it ends in, and how long it says it took.

The owner's report, with the dialog: "i am getting this error when i am usually
running cad2bim link from either schedule view or sheet view. not from 3D or
Plan view." -- `ArgumentException: The view is not printable. Parameter name:
pDBView`, thrown by `Document.Link` before anything is created.

His fix, and the rule these tests hold: when the active view cannot host the
link, do not report it -- go to a 3D view and carry on.
"""

import unittest

import _loader


views = _loader.load("views")


def _v(name, view_type, is_template=False):
    return (name, view_type, is_template)


class WhatCanHostALink(unittest.TestCase):
    def test_the_views_a_structural_engineer_builds_from_can(self):
        for view_type in ("FloorPlan", "EngineeringPlan", "ThreeD", "Section",
                          "Elevation", "CeilingPlan", "AreaPlan", "Detail",
                          "DraftingView"):
            self.assertTrue(views.can_host_link(view_type),
                            "{0} must be able to host the link".format(view_type))

    def test_the_two_the_owner_was_actually_in_cannot(self):
        # the report names both: "either schedule view or sheet view"
        self.assertFalse(views.can_host_link("Schedule"))
        self.assertFalse(views.can_host_link("DrawingSheet"))

    def test_nor_can_the_other_surfaces_that_are_not_drawings(self):
        for view_type in ("Legend", "ProjectBrowser", "SystemBrowser",
                          "Report", "CostReport", "PanelSchedule",
                          "ColumnSchedule", "Walkthrough", "Undefined",
                          "Internal", "Rendering"):
            self.assertFalse(views.can_host_link(view_type),
                             "{0} must not host the link".format(view_type))

    def test_a_view_TEMPLATE_never_hosts_it_whatever_its_type(self):
        # a template carries the type of the views it governs and has no
        # drawing surface of its own
        self.assertTrue(views.can_host_link("FloorPlan", is_template=False))
        self.assertFalse(views.can_host_link("FloorPlan", is_template=True))
        self.assertFalse(views.can_host_link("ThreeD", is_template=True))

    def test_a_view_type_this_release_has_never_heard_of_is_refused(self):
        # the allow-list is the point: a ViewType added in a later Revit must
        # default to "not a host" rather than to an exception inside Link
        self.assertFalse(views.can_host_link("SomeNewRevit2030View"))


class WhichViewToLinkInto(unittest.TestCase):
    def test_the_default_3D_view_wins(self):
        got = views.choose_host([_v("Level 1", "FloorPlan"),
                                 _v("Working 3D", "ThreeD"),
                                 _v("{3D}", "ThreeD")])
        self.assertEqual(got, 2)

    def test_a_per_user_default_3D_counts_as_the_default(self):
        # Revit names it {3D - username} when the user has their own
        got = views.choose_host([_v("Working 3D", "ThreeD"),
                                 _v("{3D - zaid}", "ThreeD")])
        self.assertEqual(got, 1)

    def test_any_3D_view_beats_a_plan(self):
        got = views.choose_host([_v("Level 1", "FloorPlan"),
                                 _v("Working 3D", "ThreeD")])
        self.assertEqual(got, 1)

    def test_a_plan_is_taken_when_the_model_has_no_3D_view_left(self):
        # deleting the 3D view must not stop the build
        got = views.choose_host([_v("Sheet A1", "DrawingSheet"),
                                 _v("Ground Floor", "EngineeringPlan")])
        self.assertEqual(got, 1)

    def test_a_model_of_nothing_but_schedules_and_sheets_chooses_none(self):
        got = views.choose_host([_v("Slab Schedule", "Schedule"),
                                 _v("Sheet A1", "DrawingSheet"),
                                 _v("Plan template", "FloorPlan", True)])
        self.assertIsNone(got)

    def test_no_views_at_all_is_None_and_not_an_error(self):
        self.assertIsNone(views.choose_host([]))
        self.assertIsNone(views.choose_host(None))

    def test_it_reads_a_revit_view_object_as_well_as_a_tuple(self):
        class _View(object):
            def __init__(self, name, view_type, is_template=False):
                self.Name = name
                self.ViewType = view_type
                self.IsTemplate = is_template

        got = views.choose_host([_View("Level 1", "FloorPlan"),
                                 _View("{3D}", "ThreeD")])
        self.assertEqual(got, 1)


class WhichViewToFinishIn(unittest.TestCase):
    """FEAT-11: "auto open the 3D view if not active by user and zoom to fit"."""

    def test_the_default_3D_is_preferred_here_too(self):
        got = views.choose_3d([_v("Working 3D", "ThreeD"),
                               _v("{3D}", "ThreeD")])
        self.assertEqual(got, 1)

    def test_a_plan_is_NOT_a_fallback_when_showing_the_model(self):
        # unlike the link host: "open the 3D view" means a 3D view or nothing,
        # or the owner is left in the plan he started in and told otherwise
        self.assertIsNone(views.choose_3d([_v("Level 1", "FloorPlan"),
                                           _v("Ground", "EngineeringPlan")]))

    def test_a_3D_view_template_is_not_a_view_to_open(self):
        self.assertIsNone(views.choose_3d([_v("3D template", "ThreeD", True)]))


class WhatTheZoomFrames(unittest.TestCase):
    """The owner, on the first zoom: "it also takes LinkedCAD and Level or Grid
    on Zoom to fit, what actually want was it should only zoom to fit BIM
    model." So the box is built from the model, and these say what that means.
    """

    def test_what_a_run_builds_counts(self):
        for category in ("OST_StructuralColumns", "OST_StructuralFraming",
                         "OST_Floors", "OST_StructuralFoundation",
                         "OST_Walls", "OST_Stairs"):
            self.assertTrue(views.counts_as_model(category),
                            "{0} is the model".format(category))

    def test_the_datums_that_run_past_the_building_do_not(self):
        self.assertFalse(views.counts_as_model("OST_Grids"))
        self.assertFalse(views.counts_as_model("OST_Levels"))
        self.assertFalse(views.counts_as_model("OST_CLines"))

    def test_the_linked_dxf_does_not_however_it_is_named(self):
        # an ImportInstance is known by its type, not its category name, so the
        # caller answers that question and this only has to honour it
        self.assertFalse(views.counts_as_model("OST_StructuralColumns",
                                               is_import=True))
        self.assertFalse(views.counts_as_model("", is_import=True))

    def test_an_element_with_no_category_still_counts(self):
        # better to frame something unexpected than to miss half the model
        self.assertTrue(views.counts_as_model(""))
        self.assertTrue(views.counts_as_model(None))


class HowLongItTook(unittest.TestCase):
    """FEAT-12's headline, which is the one thing on that window."""

    def test_a_fast_run_keeps_its_decimal(self):
        # the difference between 2 and 2.4 seconds is the whole of a fast run
        self.assertEqual(views.format_elapsed(2.44), "2.4 seconds")
        self.assertEqual(views.format_elapsed(0), "0.0 seconds")

    def test_seconds_lose_the_decimal_once_they_stop_mattering(self):
        self.assertEqual(views.format_elapsed(12.4), "12 seconds")
        self.assertEqual(views.format_elapsed(59.4), "59 seconds")

    def test_a_minute_is_read_as_minutes_and_seconds(self):
        self.assertEqual(views.format_elapsed(60), "1 min 00 sec")
        self.assertEqual(views.format_elapsed(412.7), "6 min 53 sec")

    def test_a_long_build_is_read_as_hours(self):
        self.assertEqual(views.format_elapsed(3600), "1 hr 00 min 00 sec")
        self.assertEqual(views.format_elapsed(3725), "1 hr 02 min 05 sec")

    def test_nothing_it_cannot_read_reaches_the_window_as_a_crash(self):
        for bad in (None, "", "later", -1):
            self.assertEqual(views.format_elapsed(bad), "-")


class _Point(object):
    """Stands in for Revit's XYZ: three coordinates and nothing else."""

    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z

    def __repr__(self):
        return "({0}, {1}, {2})".format(self.X, self.Y, self.Z)


class _Box(object):
    """Stands in for BoundingBoxXYZ: a Min and a Max, and NOT a pair.

    Deliberately not iterable. That is the whole point of the bug this covers --
    the accumulator unpacked one of these and Revit threw "cannot unpack
    non-iterable BoundingBoxXYZ object", so a fake that happened to be a tuple
    would pass a test the real object fails.
    """

    def __init__(self, low, high):
        self.Min, self.Max = _Point(*low), _Point(*high)


class TheBoxTheZoomFramesTheModelWith(unittest.TestCase):
    """The framing never ran once, and only the owner's console said so.

    `run_builders` imports Revit at module level, so a test cannot import it and
    the zoom could only be pinned by reading its source. A pin reads names. It
    could not see that the fold seeded itself with the Revit box and then fed
    that to a union which unpacks a pair, so the SECOND model element raised,
    the scan swallowed it, and every run quietly fell back to ZoomToFit -- the
    exact behaviour the owner had asked to be rid of. The arithmetic lives in
    `views` now so these run it rather than reading it.
    """

    def test_two_boxes_are_covered_by_one_that_holds_both(self):
        box = views.model_box([_Box((0, 0, 0), (10, 10, 3)),
                               _Box((-5, 2, -1), (4, 20, 2))], _Point)
        low, high = box
        self.assertEqual((low.X, low.Y, low.Z), (-5, 0, -1))
        self.assertEqual((high.X, high.Y, high.Z), (10, 20, 3))

    def test_the_second_element_does_not_raise_which_is_the_whole_bug(self):
        # One box never exercised the union; two did, and two is every real run.
        box = views.model_box([_Box((0, 0, 0), (1, 1, 1)),
                               _Box((2, 2, 2), (3, 3, 3))], _Point)
        self.assertIsNotNone(box)
        self.assertEqual((box[1].X, box[1].Y, box[1].Z), (3, 3, 3))

    def test_one_box_alone_comes_back_as_the_pair_zoom_takes(self):
        box = views.model_box([_Box((1, 2, 3), (4, 5, 6))], _Point)
        low, high = box                      # unpackable, unlike a Revit box
        self.assertEqual((low.X, low.Y, low.Z), (1, 2, 3))
        self.assertEqual((high.X, high.Y, high.Z), (4, 5, 6))

    def test_an_element_with_no_geometry_here_does_not_decide_the_framing(self):
        box = views.model_box([None, _Box((0, 0, 0), (2, 2, 2)), None], _Point)
        self.assertIsNotNone(box)
        self.assertEqual((box[1].X, box[1].Y, box[1].Z), (2, 2, 2))

    def test_nothing_to_frame_says_so_rather_than_inventing_a_box(self):
        self.assertIsNone(views.model_box([], _Point))
        self.assertIsNone(views.model_box([None, None], _Point))

    def test_the_order_the_elements_arrive_in_does_not_change_the_box(self):
        boxes = [_Box((0, 0, 0), (1, 1, 1)), _Box((-9, 4, 0), (2, 5, 8)),
                 _Box((3, -2, -4), (4, 0, 0))]
        first = views.model_box(boxes, _Point)
        second = views.model_box(list(reversed(boxes)), _Point)
        self.assertEqual((first[0].X, first[0].Y, first[0].Z),
                         (second[0].X, second[0].Y, second[0].Z))
        self.assertEqual((first[1].X, first[1].Y, first[1].Z),
                         (second[1].X, second[1].Y, second[1].Z))


if __name__ == "__main__":
    unittest.main()
