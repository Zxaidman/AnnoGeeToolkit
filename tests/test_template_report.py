# -*- coding: utf-8 -*-
"""The model describing itself, checked off Revit.

``template_report`` is pure — data in, Markdown out — so the shape of the report
can be argued with here rather than by running it against somebody's template
and reading what falls out.

Two properties matter more than the wording. **It is stable**: the same data
renders identically twice, with no timestamp and nothing that depends on
iteration order, because a report that changes when nothing changed cannot be
diffed and therefore cannot answer *what changed in the template*. And **it
survives a section that failed**: a model whose global parameters raise still
produces a family tree, because a template inspector that gives up on the first
awkward model is one nobody runs twice.
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
from anongee_toolkit.rc_automation import template_report        # noqa: E402


def _data(**overrides):
    """A small model, complete enough that every section renders."""
    data = {
        "model": {"title": "RC TEMPLATE", "path": r"C:\jobs\rc.rvt",
                  "survey_offset_mm": 100000.0, "survey_note": ""},
        "datum": {
            "levels": [{"name": "01 GROUND LVL.", "elevation_mm": 0.0},
                       {"name": "00 FOUNDATION LVL.",
                        "elevation_mm": -1500.0}],
            "grids": [{"name": "A", "segment_mm": ((0.0, -2000.0),
                                                   (0.0, 14000.0))},
                      {"name": "R1", "segment_mm": None}],
        },
        "categories": [{"name": "Structural Columns", "types": 4,
                        "instances": 90}],
        "families": [{
            "category": "Structural Columns",
            "family": "Concrete-Rectangular-Column",
            "loadable": True,
            "types": [{"name": "C-300x600", "mark": "C-300x600",
                       "parameters": {"b": "300", "h": "600"}},
                      {"name": "300 x 300mm", "mark": "",
                       "parameters": {"b": "300", "h": "300"}}],
        }],
        "parameters": {
            "shared": [{"name": "AG_BarMark", "kind": "spec:text",
                        "categories": ["Structural Rebar"], "instance": True,
                        "shared": True, "guid": "abc"}],
            "project": [{"name": "Pour Number", "kind": "spec:int",
                         "categories": ["Structural Columns"],
                         "instance": True, "shared": False, "guid": ""}],
            "global": [{"name": "Storey Height", "kind": "length",
                        "categories": [], "instance": False,
                        "shared": False, "guid": ""}],
            "family": [{"family": "Concrete-Rectangular-Column",
                        "parameters": [
                            {"name": "b", "kind": "length", "shared": False,
                             "read_only": False},
                            {"name": "Volume", "kind": "volume",
                             "shared": False, "read_only": True}]}],
        },
        "views": {
            "templates": [{"name": "Structural Plan", "kind": "FloorPlan"}],
            "sheets": [{"number": "S-101", "name": "FOUNDATION PLAN"}],
            "title_blocks": [{"name": "A1 Title : AnonGee"}],
        },
    }
    data.update(overrides)
    return data


class RenderingTests(unittest.TestCase):

    def setUp(self):
        self.text = template_report.render(_data())

    def test_it_starts_with_the_models_name(self):
        self.assertTrue(self.text.startswith("# RC TEMPLATE"))

    def test_every_section_is_there(self):
        for heading in ("## Datum", "## Categories", "## Families and types",
                        "## Parameters", "## Views, sheets and title blocks"):
            self.assertIn(heading, self.text, heading)

    def test_a_type_mark_is_shown_because_the_workbook_writes_it(self):
        # The TypeMark column of a placement sheet has to say exactly this.
        self.assertIn("**C-300x600**", self.text)

    def test_a_type_shows_the_numbers_a_reader_wants(self):
        self.assertIn("b 300", self.text)
        self.assertIn("h 600", self.text)

    def test_levels_are_ordered_by_height_not_by_name(self):
        foundation = self.text.index("00 FOUNDATION LVL.")
        ground = self.text.index("01 GROUND LVL.")
        self.assertLess(foundation, ground)

    def test_a_grid_that_is_not_straight_says_so_rather_than_lying(self):
        self.assertIn("not a straight line", self.text)

    def test_the_survey_offset_is_reported(self):
        self.assertIn("100000 mm", self.text)

    def test_parameter_scopes_are_named_and_explained(self):
        # The scope is the point of the section: a value written to the wrong
        # kind disappears on the next family reload and nothing says why.
        for heading in ("### Shared", "### Project", "### Global",
                        "### Family"):
            self.assertIn(heading, self.text, heading)
        self.assertIn("survives a family reload", self.text)

    def test_a_family_parameter_says_whether_it_can_be_written(self):
        self.assertIn("| `Volume` |", self.text)
        self.assertIn("| `b` |", self.text)

    def test_a_long_revit_type_name_is_shortened(self):
        # "autodesk.spec.aec:length-2.0.0" is not a thing anybody wants in a
        # table cell.
        self.assertEqual(
            template_report._short("autodesk.spec.aec:length-2.0.0"), "length")
        self.assertEqual(template_report._short(""), "—")

    def test_it_says_it_changed_nothing(self):
        self.assertIn("Read-only", self.text)


class StabilityTests(unittest.TestCase):
    """A report that changes when nothing changed cannot be diffed."""

    def test_the_same_model_renders_identically(self):
        self.assertEqual(template_report.render(_data()),
                         template_report.render(_data()))

    def test_there_is_no_timestamp_in_it(self):
        text = template_report.render(_data())
        for word in ("2026", "generated at", "Generated on"):
            self.assertNotIn(word, text, word)

    def test_the_renderer_writes_the_order_it_was_given(self):
        """Sorting happens once, in the gatherer, and is not re-done here.

        Which is worth pinning down rather than leaving to chance: two places
        sorting the same list by different rules is how a diff fills up with
        moved lines on a model where nothing moved.
        """
        rows = [{"name": "Walls", "types": 1, "instances": 2},
                {"name": "Floors", "types": 3, "instances": 4}]
        text = template_report.render(_data(categories=rows))
        self.assertLess(text.index("| Walls |"), text.index("| Floors |"))


class BrokenModelTests(unittest.TestCase):
    """One section failing must not take the rest of the report with it."""

    def test_a_section_that_could_not_be_read_says_so_and_carries_on(self):
        text = template_report.render(_data(
            categories=[{"error": "the collector threw"}]))
        self.assertIn("could not be read: the collector threw", text)
        self.assertIn("## Families and types", text)

    def test_an_empty_model_still_renders(self):
        text = template_report.render({})
        self.assertIn("This model", text)
        self.assertIn("Read-only", text)

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertTrue(template_report.render(None))

    def test_a_missing_survey_offset_is_reported_not_invented(self):
        text = template_report.render(_data(
            model={"title": "T", "path": "", "survey_offset_mm": None,
                   "survey_note": "this model has no survey point"}))
        self.assertIn("not readable", text)
        self.assertIn("no survey point", text)


class InventoryContractTests(unittest.TestCase):
    """What the Revit half promises, checked without importing Revit."""

    def source(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "structural", "inventory.py")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_it_opens_no_transaction(self):
        # It is meant to be safe to point at the real template.
        body = self.source()
        self.assertNotIn("Transaction(", body)
        self.assertNotIn(".Delete(", body)

    def test_every_section_is_wrapped(self):
        # A model whose global parameters raise must still produce a family
        # tree. Each section is gathered through _safe for that reason.
        body = self.source()
        for section in ("_categories", "_families", "_parameters", "_datum",
                        "_views"):
            self.assertIn("_safe({0}, doc".format(section), body, section)


if __name__ == "__main__":
    unittest.main()
