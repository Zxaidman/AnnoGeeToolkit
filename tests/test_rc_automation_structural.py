# -*- coding: utf-8 -*-
"""Static checks on the Revit-touching half of RC Automation.

These four modules import ``Autodesk.Revit.DB``, so they cannot be imported
here and their behaviour cannot be exercised off Revit. What *can* be checked
without Revit is everything that would otherwise only fail inside it, and each
of these has a specific failure in mind:

* a function calling something the toolkit does not have — an ``AttributeError``
  four hundred bars into a run;
* a raw Python list handed to a Revit API method, which is a fatal marshalling
  fault across the pythonnet bridge, not a catchable ``TypeError`` (§12.9.4);
* a module opening its own transaction, when a run nests thousands of bars
  inside one ``TransactionGroup`` the caller owns;
* the layout rules drifting away from the ones ``models`` defines, so a
  schedule's "12 T16 @ 200" quietly becomes something else.
"""

import ast
import io
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STRUCTURAL = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                           "anongee_toolkit", "structural")
_MODULES = ("rebar_types", "rebar_hosts", "rebar_geometry",
            "rebar_factory", "rebar_run", "levels", "grids", "footings",
            "structure_run", "rebar_constraints", "element_params")

if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()


def _pushbutton(bundle_name):
    """The folder of one named pushbutton, wherever it is stacked.

    The Dev panel's buttons move between stacks as the ribbon is arranged --
    `Bridge Check` went from `Dev.panel/` to `Dev.panel/col2.stack/` in the
    v1.26.1 layout, and every hard-coded path to it broke at once. Finding the
    bundle by name keeps these tests measuring the tool rather than its place
    on the ribbon. `test_bridge_path_sources` has done it this way all along;
    this is the same walk.
    """
    panel = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel")
    wanted = bundle_name + ".pushbutton"
    matches = []
    for current, directories, _files in os.walk(panel):
        if os.path.basename(current) == wanted:
            matches.append(current)
            directories[:] = []
    if len(matches) != 1:
        raise RuntimeError("expected exactly one {0} under {1}; found {2}".format(
            wanted, panel, matches))
    return matches[0]


def _path(name):
    return os.path.join(_STRUCTURAL, name + ".py")


def _read(name):
    with io.open(_path(name), encoding="utf-8") as handle:
        return handle.read()


def _read_script():
    """The pushbutton, for the few contracts that span it and the toolkit."""
    with io.open(os.path.join(_pushbutton("RC Automation"), "script.py"),
                 encoding="utf-8") as h:
        return h.read()


def _tree(name):
    return ast.parse(_read(name))


def _top_level_names(name):
    """Everything a module defines at the top level: functions and classes.

    Classes count. The first version of this collected only functions and duly
    reported ``rebar_factory.PlacementResult`` as a call into something that
    does not exist, which is a test finding its own blind spot rather than a
    bug.
    """
    return set(node.name for node in _tree(name).body
               if isinstance(node, (ast.FunctionDef, ast.ClassDef)))


def _functions(name):
    return dict((node.name, node) for node in _tree(name).body
                if isinstance(node, ast.FunctionDef))


class ModuleTests(unittest.TestCase):

    def test_every_module_compiles(self):
        for name in _MODULES:
            compile(_read(name), _path(name), "exec")

    def test_every_module_is_listed_in_the_package(self):
        init = _read("__init__")
        for name in _MODULES:
            self.assertIn('"{0}"'.format(name), init, name)

    def test_no_re_module(self):
        """The engine ships a partial stdlib and ``re`` is not in it (§12.9.3)."""
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.Import):
                    self.assertNotIn("re", [a.name for a in node.names], name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "re", name)

    def test_no_pyrevit_imports(self):
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("pyrevit"),
                                     name)

    def test_no_star_imports(self):
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("*", [a.name for a in node.names], name)


class TransactionOwnershipTests(unittest.TestCase):
    """A run places thousands of bars in chunks inside one TransactionGroup.

    A module that opened its own would either nest inside that or hand the user
    a thousand undo steps, so none of them may.
    """

    def test_nothing_opens_a_transaction(self):
        for name in _MODULES:
            source = _read(name)
            for forbidden in ("Transaction(", "TransactionGroup(",
                              "SubTransaction("):
                self.assertNotIn(forbidden, source,
                                 "{0} opens {1}".format(name, forbidden))

    def test_the_writing_module_says_it_does_not(self):
        source = _read("rebar_factory")
        self.assertIn("never opens a transaction", source.lower())

    def test_the_reading_modules_say_they_only_read(self):
        for name in ("rebar_types", "rebar_hosts"):
            self.assertIn("read", _read(name).split("\n")[2].lower()
                          + _read(name)[:1200].lower(), name)


class MarshallingTests(unittest.TestCase):
    """Raw Python lists across the bridge are a fatal fault, not an exception."""

    def test_curves_are_a_typed_list_built_with_add(self):
        source = _read("rebar_geometry")
        self.assertIn("List[Curve]()", source)
        self.assertIn("curves.Add(", source)

    def test_the_typed_list_is_imported_from_generic(self):
        self.assertIn("from System.Collections.Generic import List",
                      _read("rebar_geometry"))

    def test_no_python_list_literal_is_passed_as_curves(self):
        # `curves=[...]` would marshal as a fatal fault rather than raising.
        for name in ("rebar_factory", "rebar_geometry"):
            self.assertNotIn("curves = [", _read(name), name)


class CrossModuleApiTests(unittest.TestCase):
    """Every rc_automation attribute these modules name actually exists."""

    OWNERS = {"rebar_spec": "rebar_spec", "models": "models",
              "naming": "naming"}

    def test_referenced_rc_automation_attributes_exist(self):
        missing = []
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, ast.Attribute):
                    continue
                owner = node.value
                if (not isinstance(owner, ast.Name)
                        or owner.id not in self.OWNERS):
                    continue
                module = getattr(_rc, self.OWNERS[owner.id])
                if not hasattr(module, node.attr):
                    missing.append("{0}: {1}.{2}".format(
                        name, owner.id, node.attr))
        self.assertEqual(sorted(set(missing)), [])

    def test_internal_calls_resolve(self):
        """A call into a sibling module has to name a function it defines."""
        known = dict((name, _top_level_names(name)) for name in _MODULES)
        missing = []
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id in known
                        and func.attr not in known[func.value.id]):
                    missing.append("{0}: {1}.{2}".format(
                        name, func.value.id, func.attr))
        self.assertEqual(sorted(set(missing)), [])

    def test_every_layout_rule_models_defines_is_handled(self):
        source = _read("rebar_factory")
        models = _rc.models
        for rule in (models.LAYOUT_NUMBER_WITH_SPACING,
                     models.LAYOUT_MAXIMUM_SPACING,
                     models.LAYOUT_FIXED_NUMBER):
            constant = [n for n in dir(models)
                        if n.startswith("LAYOUT_")
                        and getattr(models, n) == rule][0]
            # FixedNumber is the else-branch, so its constant need not appear;
            # the API call for it must.
            if rule != models.LAYOUT_FIXED_NUMBER:
                self.assertIn("models." + constant, source, constant)
        for call in ("SetLayoutAsNumberWithSpacing",
                     "SetLayoutAsMaximumSpacing", "SetLayoutAsFixedNumber"):
            self.assertIn(call, source, call)

    def test_the_tie_role_drives_the_stirrup_style(self):
        # A tie placed as a Standard bar hooks and schedules like a straight
        # one, which is wrong in the model and wrong in the BBS.
        source = _read("rebar_factory")
        self.assertIn("ROLE_COLUMN_TIE", source)
        self.assertIn("RebarStyle.StirrupTie", source)
        self.assertTrue(hasattr(_rc.rebar_spec, "ROLE_COLUMN_TIE"))


class PlacementContractTests(unittest.TestCase):

    def test_the_factory_exposes_the_three_placement_shapes(self):
        functions = _functions("rebar_factory")
        for name in ("place_layer", "place_set", "place_bars", "create_bar",
                     "apply_layout"):
            self.assertIn(name, functions, name)

    def test_placement_returns_results_rather_than_raising(self):
        """One bad bar in four hundred costs that bar, not the run."""
        source = _read("rebar_factory")
        for name in ("place_layer", "place_set", "place_bars"):
            body = source.split("def " + name)[1].split("\ndef ")[0]
            self.assertIn("result.errors.append", body, name)
            self.assertIn("except Exception", body, name)

    def test_a_uniform_run_is_placed_as_one_element(self):
        # The 2,000-versus-50,000 difference at the stated scale.
        body = _read("rebar_factory").split("def place_layer")[1]\
            .split("\ndef ")[0]
        self.assertIn("plan.as_set()", body)
        self.assertIn("apply_layout", body)

    def test_placed_bars_are_stamped_so_a_rerun_can_tell_them_apart(self):
        # Phase 3 replaces only what this tool made and leaves hand-added bars
        # alone, which it can only do if they were marked when placed.
        source = _read("rebar_factory")
        self.assertIn("STAMP_TEXT", source)
        self.assertIn("_stamp(rebar)", source)
        self.assertIn("def existing_stamped_rebar", source)

    def test_host_validity_is_asked_before_anything_is_placed(self):
        source = _read("rebar_hosts")
        self.assertIn("def is_valid_host", source)
        self.assertIn("IsValidHost", source)
        # And the reason a footing usually fails it is spelled out.
        self.assertIn("FLOOR_PARAM_IS_STRUCTURAL", source)

    def test_bar_types_are_matched_never_created(self):
        """Creating a bar type nobody loaded puts a wrong name in the BBS.

        A cover type is different and is created — it is a distance with a name
        and carries none of that baggage — but it is created by the module that
        writes, not by the one that reads.
        """
        source = _read("rebar_types")
        for forbidden in (".Duplicate(", ".Create(", "NewFamilyInstance"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertIn("RebarCoverType.Create", _read("rebar_factory"))

    def test_shape_driven_bars_use_the_shape_driven_constraint_api(self):
        """The first version called the free-form one and could never work.

        ``RebarConstraint.Create`` is free-form only. Against a bar from
        ``CreateFromCurves`` it raises "Constrained rebar isn't a free form
        rebar element", which is what a real run reported. Shape-driven bars
        ask Revit for candidates and pick one.
        """
        source = _read("rebar_constraints")
        # Below the module docstring, which explains the mistake and so names
        # the call it is warning about.
        code = source.split('"""', 2)[-1]
        self.assertNotIn("RebarConstraint.Create", code)
        self.assertIn("GetConstraintCandidatesForHandle", code)
        self.assertIn("SetPreferredConstraint", source)
        self.assertIn("ApplyRebarConstraints", source)
        # The cover is the point; a bare face ignores a cover change.
        self.assertIn("IsToCover", source)

    def test_varying_sets_are_the_accessor_flag(self):
        """The ribbon's Varying Rebar Set is one property, set after
        constraining — the constraints are what produce the variation."""
        source = _read("rebar_constraints")
        self.assertIn("UseRebarConstraintsToProduceVaryingBars", source)
        body = source.split("def set_varying")[1].split("\ndef ")[0]
        self.assertIn("after", body.lower())

    def test_every_constraint_call_is_probed(self):
        """Written without a Revit to try it against, so nothing is assumed."""
        source = _read("rebar_constraints")
        self.assertIn("def _call(owner, name, *args)", source)
        self.assertIn("getattr(owner, name, None)", source)
        self.assertIn("def describe", source)

    def test_what_revit_actually_did_is_read_back(self):
        # A set told to fill between constrained ends decides its own length.
        self.assertIn("def array_length_mm", _read("rebar_constraints"))


class RunContractTests(unittest.TestCase):
    """The Phase 2 pass: what it refuses to do, and why."""

    def body(self, function):
        return _read("rebar_run").split("def " + function)[1].split("\ndef ")[0]

    def test_planning_opens_no_transaction(self):
        # The plan is shown before a transaction exists, so it can be refused.
        for name in ("plan_footings", "_plan_one_footing", "resolve_bar_types"):
            self.assertNotIn("Transaction", self.body(name), name)

    def test_a_host_that_cannot_be_reinforced_is_asked_first(self):
        body = self.body("_plan_one_footing")
        self.assertIn("is_valid_host", body)
        self.assertIn("why_not_a_host", body)

    def test_a_pad_that_is_not_its_scheduled_size_is_refused(self):
        # Bars planned from the schedule and placed against a bounding box do
        # not fit a pad that was modelled differently, or rotated.
        body = self.body("_plan_one_footing")
        self.assertIn("_sized_as_scheduled", body)
        self.assertIn("STATUS_INVALID", body)

    def test_an_outline_is_threaded_through_to_the_bars(self):
        body = self.body("_plan_one_footing")
        self.assertIn("plan_footing(footing, rows, placement)", body)

    def test_existing_reinforcement_stops_a_second_run_doubling_it(self):
        body = self.body("_plan_one_footing")
        self.assertIn("_has_any_rebar", body)
        self.assertIn("STATUS_EXISTS", body)

    def test_bar_types_are_resolved_once_for_the_run(self):
        # A thousand footings of one type ask the same question a thousand
        # times otherwise.
        body = self.body("resolve_bar_types")
        self.assertIn("if key in resolved or key in missing", body)

    def test_the_size_check_uses_the_schedule_not_the_type_row(self):
        body = self.body("_plan_one_footing")
        self.assertIn("rebar_spec.scheduled_extent_mm", body)
        self.assertTrue(hasattr(_rc.rebar_spec, "scheduled_extent_mm"))


class FootingCreationTests(unittest.TestCase):
    """Phase 1: making the pads, and the two things easy to leave out."""

    def body(self, module, function):
        return _read(module).split("def " + function)[1].split("\ndef ")[0]

    def test_a_pad_is_flagged_structural_when_it_is_made(self):
        """Otherwise it carries no reinforcement and looks identical anyway.

        This is what the first probe of a real model found waiting: a floor
        that is not flagged structural refuses every bar, in every view, with
        nothing to see.
        """
        self.assertIn("set_structural(floor)", self.body("footings", "create"))
        body = self.body("footings", "set_structural")
        self.assertIn("FLOOR_PARAM_IS_STRUCTURAL", body)

    def test_a_type_is_duplicated_per_thickness_not_edited(self):
        # Setting the thickness on a shared type would silently resize every
        # footing already using it.
        body = self.body("footings", "resolve_type")
        self.assertIn(".Duplicate(", body)
        self.assertIn("cache", body)

    def test_an_existing_type_of_that_thickness_is_reused(self):
        # A second run over the same schedule must add no types.
        body = self.body("footings", "resolve_type")
        self.assertIn("floor_type.Name == wanted", body)

    def test_the_outline_is_a_typed_curve_loop(self):
        body = self.body("footings", "create")
        self.assertIn("List[CurveLoop]()", body)
        self.assertIn("loops.Add(", body)

    def test_zero_length_edges_are_dropped_not_passed_on(self):
        # Revit refuses the whole sketch for one, so a repeated outline point
        # would cost the entire pad.
        body = self.body("footings", "curve_loop")
        self.assertIn("MIN_EDGE_FT", body)

    def test_rotation_happens_before_the_offset(self):
        """Rotating after offsetting swings a pad away from where it belongs."""
        body = self.body("footings", "curve_loop")
        self.assertLess(body.index("math.radians"), body.index("origin_mm[0]"))

    def test_nothing_in_the_creation_modules_opens_a_transaction(self):
        for name in ("footings", "structure_run", "levels", "grids"):
            for forbidden in ("Transaction(", "TransactionGroup("):
                self.assertNotIn(forbidden, _read(name),
                                 "{0} opens {1}".format(name, forbidden))


class StructureRunTests(unittest.TestCase):
    """Resolving everything before writing anything."""

    def body(self, function):
        return _read("structure_run").split("def " + function)[1]\
            .split("\ndef ")[0]

    def test_a_mark_already_in_the_model_is_not_placed_twice(self):
        body = self.body("_plan_one")
        self.assertIn("already", body)
        self.assertIn("STATUS_EXISTS", body)

    def test_an_unmatched_level_stops_the_run_rather_than_one_row(self):
        """A level nobody can match breaks every row that uses it, so it is
        reported once as a blocker with the model's own names beside it."""
        body = self.body("plan")
        self.assertIn("blockers", body)
        self.assertIn("level_module.names(doc)", body)

    def test_coordinates_rescue_a_grid_reference_that_does_not_resolve(self):
        # A workbook carrying both has already said where the pad goes.
        body = self.body("_position_mm")
        self.assertIn("has_coordinates", body)

    def test_a_project_with_no_floor_type_is_a_blocker(self):
        body = self.body("plan")
        self.assertIn("default_type_id", body)
        self.assertIn("Structural Foundation floor type", body)

    def test_an_outline_is_placed_as_drawn(self):
        body = self.body("_plan_one")
        self.assertIn("rebar_spec.outline_for", body)


class GeometryContractTests(unittest.TestCase):

    def test_the_array_vector_is_used_as_the_plane_normal(self):
        """Revit distributes a set along the normal, so it is not a free choice.

        A footing layer running X and spaced along Y has to hand over Y, or the
        set marches off vertically instead of across the pad.
        """
        source = _read("rebar_geometry")
        self.assertIn("array_vector", source)
        self.assertIn("def normal_for", source)
        self.assertTrue(hasattr(_rc.rebar_spec.BarSetSpec, "__slots__"))
        self.assertIn("array_vector", _rc.rebar_spec.BarSetSpec.__slots__)

    def test_zero_length_segments_are_dropped_not_passed_on(self):
        # Revit rejects an entire sketch for one zero-length line, so a repeated
        # outline point would otherwise cost the whole bar.
        source = _read("rebar_geometry")
        self.assertIn("MIN_SEGMENT_FT", source)
        self.assertIn("skipped", source)

    def test_rotation_is_applied_before_the_offset(self):
        """Rotating after offsetting swings a pad's bars away from the pad."""
        body = _read("rebar_geometry").split("def to_xyz")[1].split("\ndef ")[0]
        rotate_at = body.index("math.radians")
        offset_at = body.index("origin_ft is None")
        self.assertLess(rotate_at, offset_at)


class CoverFaceTests(unittest.TestCase):
    """A cover type belongs to a face, not to a number.

    A run against a schedule with 50 mm on top and 50 mm on the sides -- which
    is most schedules -- gave the side faces the type named ``FOOTING TOP``,
    because the cache that stops three identical types being created was keyed
    on the value alone. The footing then read *Other Faces: FOOTING TOP
    <50 mm>*: the right number on the wrong face, which is the kind of wrong
    that survives a check and reaches a drawing.
    """

    def body(self, name):
        return _read("rebar_factory").split("def " + name)[1].split("\ndef ")[0]

    def test_the_cover_cache_is_keyed_by_face_as_well_as_value(self):
        body = self.body("ensure_cover_type")
        self.assertIn("key = (face,", body)

    def test_an_existing_type_has_to_match_the_face_name_too(self):
        body = self.body("ensure_cover_type")
        self.assertIn("name_hint=wanted", body)

    def test_a_name_hint_never_falls_back_to_a_type_of_the_same_size(self):
        """Otherwise the hint buys nothing: the wrong-named type wins anyway."""
        body = (_read("rebar_types").split("def match_cover_type")[1]
                .split("\ndef ")[0])
        hinted = body.split("if name_hint:")[1]
        self.assertIn("return None", hinted.split("\n\n")[0])

    def test_every_face_of_a_footing_has_its_own_name(self):
        source = _read("rebar_factory")
        names = source.split("COVER_TYPE_NAMES = {")[1].split("}")[0]
        for face in ("top", "bottom", "side"):
            self.assertIn('"{0}"'.format(face), names)
        # Element-specific, not "RC 50 mm" -- a schedule full of RC-something
        # tells a reader nothing about where it applies.
        self.assertIn("FOOTING TOP", names)
        self.assertIn("FOOTING BOTTOM", names)
        self.assertIn("FOOTING ALL SIDE", names)


class ConstraintChoiceTests(unittest.TestCase):
    """Which candidate a handle takes decides whether a varying set varies.

    A pad offers a cover candidate for every face. Taking the first one that
    answers ``IsToCover()`` ties the gable-end bars of a tapered pad to a square
    face, and the varying set then has nothing to vary along -- which is what a
    real model showed after the bars were already landing in the right regions.
    """

    def body(self, name):
        return (_read("rebar_constraints").split("def " + name)[1]
                .split("\ndef ")[0])

    def test_the_nearest_cover_candidate_wins_not_the_first(self):
        body = self.body("_nearest_cover_candidate")
        self.assertIn("abs(gap) < abs(best_gap)", body)

    def test_the_distance_is_compared_as_a_magnitude(self):
        # Signed in Revit: a raw comparison picks the most negative, which is
        # the face furthest behind the handle rather than the nearest one.
        self.assertIn("callers compare magnitudes", _read("rebar_constraints"))

    def test_a_candidate_that_will_not_say_is_unrankable_not_nearest(self):
        body = self.body("_nearest_cover_candidate")
        self.assertIn("unranked", body)

    def test_the_handle_is_named_when_the_constraint_is_set(self):
        """``SetPreferredConstraint`` alone reported success and changed nothing."""
        body = self.body("_prefer")
        self.assertIn("SetPreferredConstraintForHandle", body)
        self.assertLess(body.index("SetPreferredConstraintForHandle"),
                        body.index('"SetPreferredConstraint"'))

    def test_the_apply_call_that_does_not_exist_is_not_made(self):
        # ``ApplyRebarConstraints()`` raised "No method matches given
        # arguments" in a real run, and the note went into the report as though
        # a constraint had failed.
        source = _read("rebar_constraints")
        self.assertNotIn('_call(manager, "ApplyRebarConstraints"', source)

    def test_a_varying_set_reports_which_faces_its_ends_found(self):
        # "The varying set did not vary" and "the varying set was tied to the
        # wrong face" look identical in a model and are the same bug. The face
        # report is what went *right*, so it travels separately from the notes
        # rather than under a heading that says nothing was constrained.
        body = self.body("apply_to_all")
        self.assertIn("faces = []", body)
        self.assertIn("faces.append(line)", body)
        self.assertIn("return (applied,", body)
        script = _read_script()
        self.assertIn('"constraint_faces": constraint_faces', script)
        self.assertIn("the cover face each end found", script)

    def test_only_a_handle_already_on_its_cover_is_snapped_to_zero(self):
        # A second layer sits a whole bar diameter off its cover and has to
        # keep doing so; forcing every handle to zero would move the steel.
        body = self.body("constrain_to_cover")
        self.assertIn("snap_tolerance_mm", body)
        self.assertIn("abs(gap) <= snap_tolerance_mm", body)


class IdentityParameterTests(unittest.TestCase):
    """Filling the project's own schedule fields, and never inventing them."""

    def test_nothing_here_opens_its_own_transaction(self):
        source = _read("element_params")
        self.assertNotIn("Transaction(", source)
        self.assertIn("Requires a transaction the caller owns", source)

    def test_categories_cross_the_bridge_as_a_category_set(self):
        """A raw Python list is a fatal marshalling fault, not a TypeError."""
        body = (_read("element_params").split("def _category_set")[1]
                .split("\ndef ")[0])
        self.assertIn("NewCategorySet", body)
        self.assertIn(".Insert(category)", body)

    def test_both_spellings_of_the_moved_api_are_tried(self):
        source = _read("element_params")
        for pair in (("SpecTypeId", "ParameterType"),
                     ("GroupTypeId", "BuiltInParameterGroup")):
            for name in pair:
                self.assertIn(name, source, name)

    def test_a_shared_parameter_file_is_written_with_its_header(self):
        # Revit hands back None for a file with no header, and every definition
        # then fails to create with nothing said about why.
        source = _read("element_params")
        self.assertIn("*META\\tVERSION\\tMINVERSION", source)
        self.assertIn("*PARAM\\tGUID\\tNAME", source)

    def test_an_existing_definition_is_reused_rather_than_duplicated(self):
        # A shared parameter is identified by GUID: a second one of the same
        # name reads identically on screen and is a different parameter.
        body = (_read("element_params").split("def _text_definition")[1]
                .split("\ndef ")[0])
        self.assertIn("if definition.Name == name:", body)

    def test_bound_somewhere_else_does_not_count_as_bound_here(self):
        # A project whose ID reaches only Walls has the parameter and still
        # cannot put it on a footing. Calling that present would mean writing
        # nothing and saying nothing.
        body = (_read("element_params").split("def bound_names")[1]
                .split("\ndef ")[0])
        self.assertIn("wanted.issubset(reached)", body)
        self.assertIn("reached is None", body)

    def test_element_ids_are_read_both_ways_round_the_2024_rename(self):
        body = (_read("element_params").split("def _id_value")[1]
                .split("\ndef ")[0])
        self.assertIn('"Value", "IntegerValue"', body)

    def test_a_missing_parameter_never_fails_a_bar(self):
        body = (_read("element_params").split("def write")[1]
                .split("\ndef ")[0])
        self.assertIn("notes.append", body)
        self.assertNotIn("raise", body)

    def test_a_bar_takes_its_host_s_values_rather_than_deriving_them(self):
        body = (_read("rebar_factory").split("def identify")[1]
                .split("\ndef ")[0])
        self.assertIn("identity_module.rebar_values", body)
        self.assertIn("host_identity", body)


if __name__ == "__main__":
    unittest.main()


class TypeMakerTests(unittest.TestCase):
    """``structural/typemaker`` — the module that exists so a type that cannot
    be made says why.

    ``sanitise`` and ``_candidates`` are pure, so the rules can be argued with
    here rather than through a dialog box on somebody's machine. Everything
    else in the module needs Revit and is covered by the static checks above.
    """

    def module(self):
        """Import it without the Revit half — every Revit import inside it is
        deliberately function-local, which is the property being relied on."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_typemaker_under_test", _path("typemaker"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_forbidden_character_is_removed(self):
        maker = self.module()
        for character in maker.FORBIDDEN:
            self.assertNotIn(character,
                             maker.sanitise("CH-230{0} X 600".format(character)))

    def test_a_usable_name_is_left_alone(self):
        """The owner's house convention must survive untouched, or the sheet
        stops meaning what it says."""
        maker = self.module()
        for name in ("CH-230 X 600", "B-230x600", "CH-2400 X 2400 X 150",
                     "CH-150 THK.", "300 X 600"):
            self.assertEqual(maker.sanitise(name), name)

    def test_runs_of_space_collapse(self):
        maker = self.module()
        self.assertEqual(maker.sanitise("  CH-230   X  600  "), "CH-230 X 600")

    def test_a_name_of_nothing_but_punctuation_is_empty(self):
        maker = self.module()
        self.assertEqual(maker.sanitise("{}[]"), "")
        self.assertEqual(maker.sanitise(None), "")

    def test_the_naming_sheet_is_tried_before_the_workbook(self):
        """A type is *named* by the naming sheet and *found* by the workbook's
        TypeMark. The order matters: the preferred name is the house
        convention, and falling back to the TypeMark is a reported compromise,
        not a default."""
        maker = self.module()
        candidates = maker._candidates("CH-230 X 600", "B-230x600")
        self.assertEqual(candidates[0][0], "CH-230 X 600")
        self.assertEqual(candidates[0][1], "preferred")
        self.assertEqual(candidates[1][0], "B-230x600")
        self.assertIn("refused", candidates[1][1])

    def test_numbered_variants_follow_and_are_bounded(self):
        """Enough to get past a clash, few enough that a family does not fill
        up with ``CH-230 X 600 (7)``."""
        maker = self.module()
        candidates = maker._candidates("CH-230 X 600", "B-230x600")
        numbered = [name for name, _why in candidates if name.endswith(")")]
        self.assertEqual(len(numbered), maker.VARIANTS)
        self.assertEqual(numbered[0], "CH-230 X 600 (2)")

    def test_one_name_is_not_tried_twice(self):
        """When the naming sheet renders exactly the TypeMark — which is what
        the shipped defaults do — there is one name, not two identical ones."""
        maker = self.module()
        candidates = maker._candidates("300 X 600", "300 x 600")
        self.assertEqual([name for name, _why in candidates
                          if not name.endswith(")")], ["300 X 600"])

    def test_a_missing_preferred_name_still_gives_candidates(self):
        maker = self.module()
        candidates = maker._candidates("", "B-230x600")
        self.assertEqual(candidates[0][0], "B-230x600")

    def test_every_revit_import_is_function_local(self):
        """The whole module has to be importable off Revit for the tests above
        to mean anything, and a module-level ``from Autodesk.Revit.DB import``
        would silently take that away."""
        with io.open(_path("typemaker"), encoding="utf-8") as handle:
            maker_source = handle.read()
        tree = ast.parse(maker_source)
        for node in tree.body:
            self.assertNotIsInstance(node, (ast.Import, ast.ImportFrom),
                                     "module-level import in typemaker")


class ParameterShadowingTests(unittest.TestCase):
    """BUG-31's actual cause, and a guard so it cannot come back anywhere.

    ``framing.ensure_symbol`` took a parameter called ``name`` — the type name
    the NAMING sheet asked for — and then ran four ``for _label, name, ... in
    loaded:`` loops over the model's types. Python's for-loop leaks its
    variable, so once all four passes ran without matching, which is *exactly*
    the case where a type has to be created, ``name`` held the last loaded
    type's name instead. ``Duplicate(name or wanted)`` therefore asked Revit
    for a name that already existed **by construction**, and could never
    succeed. A hundred and ten beams died on it.

    ``columns.py`` was untouched only because its four passes live in a
    separate ``find_symbol``, where there is no parameter to shadow.

    So this walks every function in the toolkit and fails when a loop target
    rebinds one of that function's own parameters.
    """

    #: Loop variables so conventional that rebinding one is never the bug.
    HARMLESS = ("_", "__")

    def files(self):
        found = []
        root = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit")
        for folder in ("structural", "commands", "rc_automation", "bridge"):
            directory = os.path.join(root, folder)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if name.endswith(".py"):
                    found.append(os.path.join(directory, name))
        return found

    def parameters(self, function):
        found = []
        arguments = function.args
        for group in (getattr(arguments, "posonlyargs", []), arguments.args,
                      arguments.kwonlyargs):
            for argument in group:
                found.append(argument.arg)
        for extra in (arguments.vararg, arguments.kwarg):
            if extra is not None:
                found.append(extra.arg)
        return set(found)

    def targets(self, node):
        """Every name a ``for`` binds, including inside a tuple unpack."""
        found = set()
        for item in ast.walk(node.target):
            if isinstance(item, ast.Name):
                found.add(item.id)
        return found

    def test_no_loop_rebinds_a_parameter_of_its_own_function(self):
        offenders = []
        for path in self.files():
            with io.open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef,
                                             ast.AsyncFunctionDef)):
                    continue
                names = self.parameters(function)
                if not names:
                    continue
                for node in ast.walk(function):
                    if not isinstance(node, (ast.For, ast.AsyncFor)):
                        continue
                    # Only loops belonging to *this* function, not to one
                    # nested inside it with parameters of its own.
                    clashing = (self.targets(node) & names) - set(self.HARMLESS)
                    for clash in sorted(clashing):
                        offenders.append("{0}:{1} {2}() rebinds {3!r}".format(
                            os.path.basename(path), node.lineno,
                            function.name, clash))
        self.assertEqual(offenders, [], "\n".join(offenders))


class TypeReuseTests(unittest.TestCase):
    """A name is not a size.

    ``duplicate`` may find a type already carrying the name it wants. Handing
    it back without checking what it *measures* is how a hundred and ten
    230 x 600 floor beams were quietly given the 230 x 450 plinth section,
    with the run reporting ``written=110`` and reading as a success.
    """

    def module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_typemaker_reuse", _path("typemaker"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    class Symbol(object):
        def __init__(self, name, family=None):
            self.Name = name
            self.Family = family

        def Duplicate(self, name):
            return TypeReuseTests.Symbol(name, self.Family)

    class Family(object):
        def __init__(self, name, ids):
            self.Name = name
            self._ids = ids

        def GetFamilySymbolIds(self):
            return self._ids

    class Document(object):
        def __init__(self, by_id):
            self.by_id = by_id

        def GetElement(self, identifier):
            return self.by_id.get(identifier)

    def world(self, *names):
        symbols = [TypeReuseTests.Symbol(name) for name in names]
        family = TypeReuseTests.Family("Concrete - Rectangular Beam",
                                       list(range(len(symbols))))
        for symbol in symbols:
            symbol.Family = family
        document = TypeReuseTests.Document(
            dict((index, symbol) for index, symbol in enumerate(symbols)))
        return document, symbols

    def test_a_free_name_is_duplicated_under_that_name(self):
        maker = self.module()
        document, symbols = self.world("PB-230x450", "B-300x600")
        made, created, note = maker.duplicate(document, symbols[0],
                                              "CH-230 X 600", "B-230x600")
        self.assertEqual(made.Name, "CH-230 X 600")
        self.assertTrue(created)
        self.assertEqual(note, "")

    def test_a_taken_name_of_the_right_size_is_reused(self):
        maker = self.module()
        document, symbols = self.world("CH-230 X 600", "B-300x600")
        made, created, note = maker.duplicate(
            document, symbols[0], "CH-230 X 600", "B-230x600",
            accept=lambda symbol: True)
        self.assertIs(made, symbols[0])
        self.assertFalse(created,
                         "a reused type must never be reported as created - "
                         "the caller sizes what it makes")
        self.assertIn("already existed", note)

    def test_a_taken_name_of_the_wrong_size_is_not_reused(self):
        """The one that matters. Rejecting it moves to the next name rather
        than handing back a section nobody asked for."""
        maker = self.module()
        document, symbols = self.world("CH-230 X 600", "B-300x600")
        made, created, note = maker.duplicate(
            document, symbols[0], "CH-230 X 600", "B-230x600",
            accept=lambda symbol: False)
        self.assertIsNot(made, symbols[0])
        self.assertTrue(created)
        self.assertEqual(made.Name, "B-230x600")
        self.assertIn("refused", note)

    def test_with_no_acceptance_test_nothing_is_reused_blindly(self):
        """``accept=None`` is the old behaviour and every caller now passes
        one; this pins what happens if a future caller forgets."""
        maker = self.module()
        document, symbols = self.world("CH-230 X 600")
        made, created, _note = maker.duplicate(document, symbols[0],
                                               "CH-230 X 600")
        self.assertIs(made, symbols[0])
        self.assertFalse(created)

    def test_fits_needs_every_dimension_to_agree(self):
        maker = self.module()

        class Sized(object):
            def __init__(self, values):
                self.values = values

            def LookupParameter(self, name):
                return self.values.get(name)

        class Value(object):
            def __init__(self, feet):
                self.feet = feet
                self.HasValue = True

            def AsDouble(self):
                return self.feet

        symbol = Sized({"b": Value(230.0 / 304.8), "h": Value(600.0 / 304.8)})
        self.assertTrue(maker.fits(symbol, ((("b",), 230.0), (("h",), 600.0))))
        self.assertFalse(maker.fits(symbol, ((("b",), 230.0), (("h",), 450.0))))

    def test_a_dimension_it_cannot_read_is_not_a_match(self):
        """Unreadable is not the same as equal. Treating it as equal would put
        the silent-wrong-section bug straight back."""
        maker = self.module()

        class Blank(object):
            def LookupParameter(self, name):
                return None

        self.assertFalse(maker.fits(Blank(), ((("b",), 230.0),)))


class DuplicateDefinitionTests(unittest.TestCase):
    """No module may define the same top-level name twice.

    ``footings.py`` carried **two** ``ensure_named_type`` definitions for a
    release: an edit spliced the new one in and left the old one below it.
    Python takes the last, so every call reached the stale function, and the
    whole suite passed — a thousand and twenty-two tests, none of which called
    it with the argument the new one had gained.

    The failure only appeared in a live model, as
    ``ensure_named_type() got an unexpected keyword argument 'name'``, and it
    cost fifteen footings and a round trip.

    Nothing about that is specific to footings, so this walks the lot.
    """

    #: Names a module is allowed to bind twice, because the second is a
    #: deliberate alias or a version-guarded fallback rather than a leftover.
    ALLOWED = ()

    def files(self):
        found = []
        base = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit")
        for folder in ("structural", "commands", "rc_automation", "bridge",
                       "revit"):
            directory = os.path.join(base, folder)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if name.endswith(".py"):
                    found.append(os.path.join(directory, name))
        return found

    def test_no_module_defines_the_same_name_twice(self):
        offenders = []
        for path in self.files():
            with io.open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            seen = {}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    if node.name in self.ALLOWED:
                        continue
                    if node.name in seen:
                        offenders.append(
                            "{0}: {1} defined at lines {2} and {3}".format(
                                os.path.basename(path), node.name,
                                seen[node.name], node.lineno))
                    seen[node.name] = node.lineno
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_module_assigns_the_same_constant_twice(self):
        """The same failure one level down: a module-level constant redefined
        below its first use reads as the first value everywhere above and the
        second everywhere below, which is not a thing anybody intends."""
        offenders = []
        for path in self.files():
            with io.open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            seen = {}
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if not target.id.isupper():
                        continue
                    if target.id in seen:
                        offenders.append(
                            "{0}: {1} assigned at lines {2} and {3}".format(
                                os.path.basename(path), target.id,
                                seen[target.id], node.lineno))
                    seen[target.id] = node.lineno
        self.assertEqual(offenders, [], "\n".join(offenders))


class CallSignatureTests(unittest.TestCase):
    """Every keyword a toolkit module passes to another must be accepted.

    ``commands/footings.py`` started passing ``name=`` to
    ``structural.footings.ensure_named_type``. The function had gained that
    parameter — and a stale duplicate definition below it had not, so Python
    bound the stale one and fifteen footings died in a live model with
    ``got an unexpected keyword argument 'name'``.

    The duplicate is guarded above. **This guards the shape of the call
    itself**, which is the thing that actually broke, and would have caught it
    even with only one definition — because no test calls these functions: they
    take a Revit ``Document``, so they cannot be called here at all. A static
    check is the only check available, which makes it worth having.
    """

    def modules(self):
        """``{module name: {function: (parameters, takes **kwargs)}}``."""
        found = {}
        base = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit")
        for folder in ("structural", "commands", "rc_automation", "bridge"):
            directory = os.path.join(base, folder)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if not name.endswith(".py"):
                    continue
                with io.open(os.path.join(directory, name),
                             encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                functions = {}
                for node in tree.body:
                    if not isinstance(node, (ast.FunctionDef,
                                             ast.AsyncFunctionDef)):
                        continue
                    arguments = node.args
                    names = set()
                    for group in (getattr(arguments, "posonlyargs", []),
                                  arguments.args, arguments.kwonlyargs):
                        for argument in group:
                            names.add(argument.arg)
                    functions[node.name] = (names,
                                            arguments.kwarg is not None)
                # Keyed by package **and** module: `commands/footings.py` and
                # `structural/footings.py` are both "footings", and letting one
                # overwrite the other made this check look at the wrong file.
                found["{0}.{1}".format(folder, name[:-3])] = functions
        return found

    def imported(self, tree):
        """``{local name: module name}`` for ``from anongee_toolkit.x import y``."""
        found = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if not module.startswith("anongee_toolkit."):
                continue
            package = module.split(".")[-1]
            for alias in node.names:
                found[alias.asname or alias.name] = "{0}.{1}".format(
                    package, alias.name)
        return found

    def test_every_keyword_is_one_the_callee_accepts(self):
        known = self.modules()
        offenders = []
        base = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit")
        for folder in ("structural", "commands"):
            directory = os.path.join(base, folder)
            for name in sorted(os.listdir(directory)):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(directory, name)
                with io.open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                bindings = self.imported(tree)

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    target = node.func
                    if not isinstance(target, ast.Attribute):
                        continue
                    owner = target.value
                    if not isinstance(owner, ast.Name):
                        continue
                    module = bindings.get(owner.id)
                    if module is None or module not in known:
                        continue
                    signature = known[module].get(target.attr)
                    if signature is None:
                        continue
                    parameters, takes_kwargs = signature
                    if takes_kwargs:
                        continue
                    for keyword in node.keywords:
                        if keyword.arg is None:      # **something
                            continue
                        if keyword.arg not in parameters:
                            offenders.append(
                                "{0}:{1} {2}.{3}() has no {4!r}".format(
                                    name, node.lineno, module, target.attr,
                                    keyword.arg))
        self.assertEqual(sorted(set(offenders)), [],
                         "\n".join(sorted(set(offenders))))

    def test_the_check_can_see_the_call_that_broke(self):
        """A check that silently matches nothing is worse than no check.

        ``commands/footings.py`` must really be passing ``name=`` to
        ``structural.footings.ensure_named_type`` — if that call ever stops
        being visible to the walk above, the walk has stopped working.
        """
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "footings.py")
        with io.open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        found = False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "ensure_named_type"
                    and any(keyword.arg == "name"
                            for keyword in node.keywords)):
                found = True
        self.assertTrue(found)
        self.assertIn("ensure_named_type",
                      self.modules().get("structural.footings", {}))
