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


if __name__ == "__main__":
    unittest.main()
