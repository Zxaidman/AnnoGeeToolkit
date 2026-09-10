# -*- coding: utf-8 -*-
"""The pushbutton dialog and its XAML must agree on every named control.

A control added to ui.xaml but never bound in script.py (or bound but missing
from the XAML) only fails when the user opens the dialog in Revit -- exactly how
v0.59.0's `tb_slab_step` got out. Both files are plain text here, so the check
is a static one: no Revit, no WPF, no XamlReader.
"""

import ast
import os
import re
import unittest
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
_BUTTON = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "..", "..",
    "AnonGee.tab", "Core.panel", "cad2bim.pushbutton"))
_SCRIPT = os.path.join(_BUTTON, "script.py")
# the dialogs moved into the library; the button keeps the run pipeline
_WINDOW = os.path.normpath(os.path.join(_HERE, "..", "ui_window.py"))
# ...and the element-creation drivers moved beside them
_BUILDERS = os.path.normpath(os.path.join(_HERE, "..", "run_builders.py"))
_DIALOGS = os.path.normpath(os.path.join(_HERE, "..", "ui_dialogs.py"))
# the wall builder itself: imports Revit at module level, so text-only here
_WALLS_BUILDER = os.path.normpath(os.path.join(_HERE, "..", "builders",
                                               "walls.py"))
# ...and the column builder, which since the three-way choice is also where a
# vertical member is routed to one builder or the other
_COLUMNS_BUILDER = os.path.normpath(os.path.join(_HERE, "..", "builders",
                                                 "columns.py"))
_XAML = os.path.join(_BUTTON, "ui.xaml")
_LINK_XAML = os.path.join(_BUTTON, "link_options.xaml")
_ADV_XAML = os.path.join(_BUTTON, "advanced.xaml")
_ELAPSED_XAML = os.path.join(_BUTTON, "elapsed.xaml")

_RESOURCES = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "..", "..", "Resources"))

_FIND = re.compile(r'\bfind\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')


def _body_iter(path):
    """Every element OUTSIDE Window.Resources -- the dialog's real controls.

    The dialogs inline the AnonGee theme under Window.Resources (Brand
    Guidelines 12.3 / 12.7.B), and its ControlTemplates carry part names
    (PART_*, Bg, Stroke, Bd...) that live in their own WPF namescopes: they
    are not dialog controls, FindName never resolves them, and the same part
    name legitimately repeats across templates. Scans about the dialog's OWN
    controls therefore walk the body only.
    """
    def walk(element):
        for child in element:
            if child.tag.endswith("Window.Resources"):
                continue
            yield child
            for grandchild in walk(child):
                yield grandchild
    return walk(ET.parse(path).getroot())


def _xaml_source():
    """The dialog's .xaml as text, for pinning attributes rather than names."""
    with open(_XAML, "rb") as handle:
        return handle.read().decode("utf-8", "replace")


def _xaml_names(*paths):
    """Every x:Name in the given .xaml files (all three dialogs by default)."""
    key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    names = set()
    for path in (paths or (_XAML, _LINK_XAML, _ADV_XAML)):
        names.update(el.get(key) for el in _body_iter(path) if el.get(key))
    return names


def _tab_homes():
    """{x:Name: tab path} for every named control under a TabItem.

    Which tab a control sits on is invisible to FindName -- WPF resolves names
    per window -- so a control pasted onto the wrong tab still binds and still
    runs. Only the user sees the difference, which makes the tab a thing worth
    asserting. A control under a nested TabItem records the whole path, e.g.
    "Build > Foundation"."""
    key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    homes = {}

    def walk(element, header):
        if element.tag.endswith("TabItem"):
            own = element.get("Header")
            header = "%s > %s" % (header, own) if header else own
        name = element.get(key)
        if name and header:
            homes[name] = header
        for child in element:
            walk(child, header)
    walk(ET.parse(_XAML).getroot(), None)
    return homes


def _tab_outline():
    """[(top-level tab header, [sub-tab headers])], in document order."""
    def tabs_under(element):
        found = []
        for child in element:
            if child.tag.endswith("TabItem"):
                found.append((child.get("Header"),
                              [header for header, _ in tabs_under(child)]))
            else:
                found.extend(tabs_under(child))
        return found
    return tabs_under(ET.parse(_XAML).getroot())


def _script_source():
    """The pushbutton itself -- the run pipeline and its entry point."""
    with open(_SCRIPT, "rb") as handle:
        return handle.read().decode("utf-8")


def _window_source():
    """The dialog: every control binding lives here now."""
    with open(_WINDOW, "rb") as handle:
        return handle.read().decode("utf-8")


def _builders_source():
    """The element-creation drivers: one transaction and one outcome per kind."""
    with open(_BUILDERS, "rb") as handle:
        return handle.read().decode("utf-8")


def _dialogs_source():
    """The window plumbing: loading a .xaml, and the windows built on top."""
    with open(_DIALOGS, "rb") as handle:
        return handle.read().decode("utf-8")


def _all_source():
    """Both, for checks that span the dialog and the run it starts."""
    return "\n".join((_script_source(), _window_source(),
                      _builders_source()))


class DialogControlNames(unittest.TestCase):
    def test_every_bound_control_exists_in_the_xaml(self):
        missing = sorted(set(_FIND.findall(_window_source())) - _xaml_names())
        self.assertEqual(missing, [], "bound but absent from ui.xaml: %s" % missing)

    def test_every_control_the_dialog_uses_is_bound(self):
        """self.tb_x / self.cb_x / self.chk_x must come from a find(...) call.

        Catches the reverse slip: a new textbox read by _init_tolerances or
        _read_tolerances that nobody ever assigned.
        """
        source = _window_source()
        bound = set(_FIND.findall(source))
        prefixes = ("tb_", "cb_", "chk_", "rb_", "btn_", "lbl_")
        assigned = set()
        used = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "self":
                continue
            if not node.attr.startswith(prefixes):
                continue
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
            else:
                used.add(node.attr)
        unbound = sorted(name for name in used
                         if name not in bound and name not in assigned)
        self.assertEqual(unbound, [],
                         "used but never bound to a control: %s" % unbound)


class SlabToleranceRow(unittest.TestCase):
    """Every slab tolerance on the Tolerances tab reaches slab_outlines."""

    def test_slab_tolerance_boxes_are_all_present(self):
        names = _xaml_names(_XAML)
        for control in ("tb_slab_snap", "tb_slab_heal", "tb_slab_chain",
                        "tb_slab_width", "tb_slab_step", "tb_slab_note_area"):
            self.assertIn(control, names)

    def test_every_tolerance_the_build_reads_is_on_the_tab(self):
        """The user's standing rule: a tolerance the project uses is shown here.

        Every key _read_tolerances returns has to come from a control, not from
        a constant buried in a module.
        """
        source = _window_source()
        block = source.split("def _read_tolerances(", 1)[1].split(
            "def ", 1)[0]
        keys = re.findall(r'"([a-z0-9_]+)":\s*self\._read_(?:float|int)\(',
                          block)
        self.assertGreater(len(keys), 10)
        for key in ("slab_note_min_area_m2", "face_label_reach_mm",
                    "face_size_tol_mm"):
            self.assertIn(key, keys, "%s is not read from a control" % key)


class NamingTabControls(unittest.TestCase):
    """The Naming tab's boxes are bound through a format string, so the static
    find() check cannot see them -- list them explicitly instead."""

    _CONTROL = {"column_rect": "column", "column_round": "column_round",
                "beam_sized": "beam", "beam_width": "beam_width",
                "floor": "floor", "stair": "stair",
                "stair_waist": "stair_waist", "level": "level",
                "grid": "grid", "footing": "footing", "raft": "raft",
                "wall_struct": "wall_struct", "wall_arch": "wall_arch"}

    def test_one_box_and_one_preview_per_template(self):
        names = _xaml_names(_XAML)
        for control in self._CONTROL.values():
            self.assertIn("tb_name_{0}".format(control), names)
            self.assertIn("lbl_name_{0}".format(control), names)
        self.assertIn("btn_name_defaults", names)
        self.assertIn("naming_saved_text", names)
        self.assertIn("chk_level_follow", names)

    def _template_keys(self):
        with open(os.path.join(os.path.dirname(_HERE), "naming.py"),
                  "rb") as handle:
            source = handle.read().decode("utf-8")
        block = source.split("DEFAULTS = {", 1)[1].split("}", 1)[0]
        keys = re.findall(r'"([a-z_]+)":', block)
        self.assertTrue(keys)
        return keys

    def test_every_template_key_has_a_dialog_row(self):
        names = _xaml_names(_XAML)
        for key in self._template_keys():
            self.assertIn(key, self._CONTROL,
                          "no dialog row for template %r" % key)
            self.assertIn("tb_name_{0}".format(self._CONTROL[key]), names)

    def test_every_template_key_is_bound_in_the_dialog(self):
        """A row in the XAML that __init__ never binds is a dead box.

        `footing` was exactly that: the template, the row and the preview label
        all existed, and the box came up blank because the binding loop had
        nine keys in it instead of ten.
        """
        source = _window_source()
        block = source.split("self.name_boxes = {}", 1)[1].split(
            "self.naming_saved_text", 1)[0]
        bound = set(re.findall(r'\("([a-z_]+)",\s*"[a-z_]+"\)', block))
        for key in self._template_keys():
            self.assertIn(key, bound, "the Naming tab never binds %r" % key)


class MaterialAndFootingControls(unittest.TestCase):
    """Material combos are bound through a format string over materials.KINDS."""

    def test_one_material_combo_per_kind(self):
        with open(os.path.join(os.path.dirname(_HERE), "builders",
                               "materials.py"), "rb") as handle:
            source = handle.read().decode("utf-8")
        block = source.split("KINDS = (", 1)[1].split(")", 1)[0]
        kinds = re.findall(r'"([a-z_]+)"', block)
        self.assertTrue(kinds)
        names = _xaml_names(_XAML)
        for kind in kinds:
            self.assertIn("cb_mat_{0}".format(kind), names)

    def test_the_footing_row_lives_on_the_foundation_sub_tab(self):
        # Foundation is no longer a top-level tab: it lives inside Build
        homes = _tab_homes()
        for control in ("chk_footings", "cb_footing_family",
                        "tb_footing_projection", "tb_footing_thickness",
                        "tb_max_step", "tb_fnd_min_area"):
            self.assertEqual(homes.get(control), "Build > Foundation",
                             "%s sits on %r" % (control, homes.get(control)))
        self.assertEqual(homes.get("chk_view_filters"), "Output & Graphics")


class TheDialogTabSet(unittest.TestCase):
    """The restructure's contract: six top-level tabs, Build split by discipline.

    The user's exact five: General (the run-wide picks, grids included),
    Structure (columns, beams and slabs together), Architecture (the walls
    placeholder), Foundation and Staircase. Settings files restore controls
    BY NAME, so moving a node between tabs is free -- but a control moved by
    copy-paste is easily left behind in the old tab too, and a duplicated
    x:Name is something XamlReader only refuses at runtime, in Revit, exactly
    where these checks exist not to look.
    """

    _TABS = ["Layers", "Build", "Multi-storey", "Tolerances",
             "Output & Graphics", "Naming"]
    _BUILD = ["General", "Structure", "Architecture", "Foundation",
              "Staircase"]

    def test_the_six_top_level_tabs_in_order(self):
        self.assertEqual([header for header, _ in _tab_outline()], self._TABS)

    def test_build_carries_the_element_sub_tabs_in_order(self):
        outline = dict(_tab_outline())
        self.assertEqual(outline.get("Build"), self._BUILD)
        for header, sub_tabs in _tab_outline():
            if header != "Build":
                self.assertEqual(sub_tabs, [],
                                 "%s grew sub-tabs: %s" % (header, sub_tabs))

    def test_no_name_is_declared_twice(self):
        # body only: the inlined theme's template part names repeat by design
        # and live in per-template namescopes XamlReader never complains about
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        for path in (_XAML, _LINK_XAML, _ADV_XAML):
            names = [el.get(key) for el in _body_iter(path) if el.get(key)]
            doubled = sorted(name for name in set(names)
                             if names.count(name) > 1)
            self.assertEqual(doubled, [], "%s declares twice: %s"
                             % (os.path.basename(path), doubled))

    def test_the_moved_controls_landed_where_the_layout_says(self):
        homes = _tab_homes()
        for control, tab in (
                # run-wide picks: the level pair serves columns, beams, slabs,
                # stairs and footings alike, so it lives on Build > General --
                # and the grids moved in beside them ("move grid inside
                # General tab")
                ("cb_name_param", "Build > General"),
                ("cb_base_level", "Build > General"),
                ("cb_top_level", "Build > General"),
                ("chk_grids", "Build > General"),
                # columns, beams and slabs merged onto one Structure sub-tab,
                # a GroupBox per element
                ("chk_columns", "Build > Structure"),
                ("cb_family", "Build > Structure"),
                ("cb_circular_family", "Build > Structure"),
                ("chk_beams", "Build > Structure"),
                ("cb_beam_family", "Build > Structure"),
                ("chk_slabs", "Build > Structure"),
                ("cb_floor_type", "Build > Structure"),
                ("chk_stairs", "Build > Staircase"),
                ("cb_stair_type", "Build > Staircase"),
                ("chk_export", "Output & Graphics"),
                ("tb_compare", "Output & Graphics"),
                ("tb_grid_snap", "Tolerances")):
            self.assertEqual(homes.get(control), tab,
                             "%s sits on %r" % (control, homes.get(control)))


class HelpProseIsReadable(unittest.TestCase):
    """The guide notes were FontSize 10 -- too small to read, the user said.

    They share ONE keyed style, so the readable floor is asserted in one
    place. Since the brand pass, HelpText is no longer ad hoc: it derives
    from the guideline TextBody style (AnonGee Brand Guidelines section 4.4)
    and takes its size from a local FontSizeHelp token -- which must still
    honour the user's floor of 12, above the suite-wide FontSizeBody.
    """

    _WPF = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
    _KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
    _SYS = "{clr-namespace:System;assembly=mscorlib}"
    _STYLE = "{StaticResource HelpText}"

    def _style(self):
        for style in ET.parse(_XAML).iter(self._WPF + "Style"):
            if style.get(self._KEY) == "HelpText":
                return style
        self.fail("ui.xaml has no HelpText style in Window.Resources")

    def _resolve_size(self, value):
        """A FontSize setter value as a number, following one token hop."""
        match = re.match(r"\{StaticResource ([A-Za-z0-9_]+)\}", value or "")
        if not match:
            return float(value)
        for double in ET.parse(_XAML).iter(self._SYS + "Double"):
            if double.get(self._KEY) == match.group(1):
                return float(double.text)
        self.fail("FontSize token %r is not declared" % match.group(1))

    def test_the_help_style_is_tokenized_and_at_least_font_size_12(self):
        style = self._style()
        self.assertEqual(style.get("TargetType"), "TextBlock")
        # the brand pass: HelpText derives from the guideline TextBody style
        self.assertEqual(style.get("BasedOn"), "{StaticResource TextBody}",
                         "HelpText no longer derives from TextBody")
        sizes = [setter.get("Value") for setter in style
                 if setter.get("Property") == "FontSize"]
        self.assertEqual(len(sizes), 1, "the style sets FontSize once")
        self.assertGreaterEqual(self._resolve_size(sizes[0]), 12.0)
        # ...and sets nothing else inline: colour and font come from TextBody
        others = [setter.get("Property") for setter in style
                  if setter.get("Property") != "FontSize"]
        self.assertEqual(others, [],
                         "HelpText re-pins what TextBody owns: %s" % others)

    def test_every_long_note_uses_the_style_not_its_own_small_font(self):
        # anything long enough to be prose (a label never reaches 80 chars)
        # must carry the style and must not pin a FontSize of its own
        styled = 0
        for element in ET.parse(_XAML).iter(self._WPF + "TextBlock"):
            text = element.get("Text") or ""
            if len(text) < 80:
                continue
            self.assertEqual(element.get("Style"), self._STYLE,
                             "unstyled help prose: %r..." % text[:48])
            self.assertIsNone(element.get("FontSize"),
                              "prose pins its own size: %r..." % text[:48])
            styled += 1
        self.assertGreater(styled, 20, "the prose sweep found almost nothing")

    def test_the_known_guide_notes_are_spot_checked(self):
        # two the user actually complained about: the foundation prose and
        # the Architecture tab's note (the P3 walls placeholder until v0.76.0,
        # now the roofs note beside the wall controls that replaced it)
        tree = ET.parse(_XAML)
        roofs = [el for el in tree.iter(self._WPF + "TextBlock")
                 if (el.get("Text") or "").startswith(
                     "Roofs are not built yet")]
        self.assertEqual(len(roofs), 1, "the roofs note appears once")
        self.assertEqual(roofs[0].get("Style"), self._STYLE)
        foundation = [el for el in tree.iter(self._WPF + "TextBlock")
                      if "invented pads SILENTLY" in (el.get("Text") or "")]
        self.assertEqual(len(foundation), 1)
        self.assertEqual(foundation[0].get("Style"), self._STYLE)


class TheNewTolerancesAreWired(unittest.TestCase):
    """A box on the dialog is only real once it is seeded AND read back out.

    max_step_mm is the cautionary tale: run_builders read it from the
    tolerances dict since the fold planner landed, and nothing ever put it
    there -- no box, no _read_tolerances key, a dead wire the fixture runs
    could not see because the default happened to match. These checks tie
    each new key to a control at both ends.
    """

    _WIRES = {  # x:Name -> the tolerances key its box feeds
        "tb_grid_snap": "grid_snap_mm",
        "tb_pair_overlap": "pair_min_overlap_mm",
        "tb_parallel_angle": "parallel_angle_deg",
        "tb_junction_tol": "junction_tol_mm",
        "tb_concentric_tol": "concentric_tol_mm",
        "tb_max_step": "max_step_mm",
        "tb_fnd_min_area": "foundation_min_area_m2",
    }

    def test_each_box_is_in_the_xaml(self):
        names = _xaml_names(_XAML)
        for control in self._WIRES:
            self.assertIn(control, names)

    def test_each_box_is_seeded_from_the_defaults(self):
        block = _window_source().split("def _init_tolerances(", 1)[1].split(
            "\n    def ", 1)[0]
        for control in self._WIRES:
            self.assertIn("self.{0}.Text".format(control), block,
                          "%s is never seeded" % control)

    def test_each_key_is_emitted_from_its_box(self):
        block = _window_source().split("def _read_tolerances(", 1)[1].split(
            "\n    def ", 1)[0]
        keys = re.findall(r'"([a-z0-9_]+)":\s*self\._read_(?:float|int)\(',
                          block)
        for control, key in self._WIRES.items():
            self.assertIn(key, keys, "%s is not read from a control" % key)
            self.assertIn("self.{0}".format(control), block)

    def test_the_dead_wire_is_live_at_both_ends(self):
        # the consumers already read these keys off the tolerances dict; what
        # was missing was the dialog EMITTING them
        self.assertIn('.get("max_step_mm")', _builders_source())
        window = _window_source()
        self.assertIn('"max_step_mm": self._read_float(', window)
        self.assertIn('"foundation_min_area_m2": self._read_float(', window)


class TheLegendProposalReachesTheDialog(unittest.TestCase):
    """The legend result is a PROPOSAL into the dialog, never a silent apply.

    test9's convention: swatch pattern -> legend text -> meaning, inherited
    by every plan hatch of the pattern. The read itself is unit-tested in
    test_legend.py; what no offline harness can reach is the WPF window, so
    every link from the read to the marked row is pinned as text here, the
    way the tolerance wires are. Each of these degrades SILENTLY if cut --
    the dialog simply opens without the proposal and nobody is told.
    """

    def test_the_pushbutton_reads_the_legend_before_the_window(self):
        script = _script_source()
        self.assertIn("legend.read(dxf_result.regions, dxf_result.texts)",
                      script)
        self.assertIn("legend.propose(legend_entries, dxf_result.regions)",
                      script)
        # the proposal OVERRIDES the hatch convention's default for its
        # layers -- a legend describes HATCHES, so it seeds the HATCH
        # mapping, never the geometry one -- and that override, sitting in
        # the editable hatch table, IS the proposal...
        self.assertIn('default_hatch_mapping[layer_name] = '
                      'proposal["mapping"][layer_name]', script)
        self.assertNotIn('default_mapping[layer_name] = '
                         'proposal["mapping"][layer_name]', script)
        # ...the marked rows ride into the window's HATCH table, and the
        # console says so
        self.assertIn("hatch_notes=legend_notes", script)
        self.assertIn('_say("  legend:', script)

    def test_the_window_marks_the_proposed_rows(self):
        window = _window_source()
        self.assertIn("hatch_notes=None", window)
        self.assertIn("row_notes=hatch_notes", window)
        block = window.split("def _build_rows(", 1)[1].split("\n    def ",
                                                             1)[0]
        self.assertIn("row_notes", block)
        self.assertIn("ToolTip = note", block)

    def test_the_builder_hands_the_regions_to_the_cutout_machinery(self):
        # a hatch the dialog routed to "cutout" must reach plan_foundations,
        # where it holes the plan containing it (test_foundation_plan pins
        # the behaviour; this pins the hand-over). Pinned on the ARGUMENTS
        # rather than the call's exact text -- the literal broke on a
        # reformat that changed nothing about what is handed over.
        call = _builders_source().split(
            "foundation_plan.plan_foundations(", 1)
        self.assertEqual(len(call), 2, "the foundation pass is never planned")
        call = call[1][:400]
        self.assertIn("records or []", call)
        self.assertIn("texts or []", call)
        self.assertIn("regions=regions or []", call)

    def test_the_foundation_schedule_reaches_the_rings(self):
        # test16 draws an F/RF Mark|Thk block beside its slab one: a ring
        # labelled only "F2" is sized from it, and by nothing else
        call = _builders_source().split(
            "foundation_plan.plan_foundations(", 1)[1][:900]
        self.assertIn("schedule=marks.parse_thickness_schedule(", call)

    def test_that_schedule_is_read_from_the_file_not_the_routed_notes(self):
        # `texts` here is the FOUNDATION routing -- S-FND-IDEN alone -- and
        # test16 draws its table on G-ANNO-SCHD, so reading the schedule off
        # the notes returns {} and every F-marked ring stays unsized
        call = _builders_source().split(
            "foundation_plan.plan_foundations(", 1)[1][:900]
        schedule = call.split("schedule=marks.parse_thickness_schedule(", 1)[1]
        self.assertIn("schedule_texts", schedule[:60])

    def test_the_pushbutton_hands_both_passes_the_whole_file(self):
        # one list, defined once beside dxf_texts and kept apart from it: the
        # per-plan readings (the legend, the blanket note) must keep seeing
        # their own storey, which is why sheet_texts is NOT widened instead
        source = _script_source()
        self.assertIn("file_texts = schedule_source or dxf_texts", source)
        self.assertEqual(source.count("schedule_texts=file_texts"), 2,
                         "the slab pass and the footing pass must both be "
                         "handed the file's texts for their schedules")


class TheHatchLayersHaveTheirOwnTable(unittest.TestCase):
    """Hatches map on their own table, apart from geometry and text.

    v0.69.7 merged hatch-only layers into the GEOMETRY rows, so routing a
    hatch could re-route the linework on a like-named layer. The third table
    undoes that: hatch rows come only from the regions, carry the hatch
    categories, and the regions are stamped from selections["hatch_mapping"]
    -- never from the geometry mapping. Each wire here degrades silently if
    cut, which is why it is pinned as text like the tolerance wires.
    """

    def test_the_third_table_sits_on_the_layers_tab(self):
        self.assertIn("hatch_rows", _xaml_names(_XAML))
        self.assertEqual(_tab_homes().get("hatch_rows"), "Layers")

    def test_the_window_builds_and_reads_the_table(self):
        window = _window_source()
        self.assertIn('find("hatch_rows")', window)
        self.assertIn("self._hatch_combos", window)
        # emitted under its own key, with the same unmapped fallback the
        # geometry table uses
        collect = window.split("def _collect(", 1)[1].split("\n    def ",
                                                            1)[0]
        self.assertIn('"hatch_mapping": hatch_mapping', collect)

    def test_the_rows_are_built_from_the_regions_only(self):
        script = _script_source()
        self.assertIn("layers.hatch_rows(dxf_result.regions,", script)
        self.assertIn("layers.default_hatch_row_mapping(hatch_table)", script)
        self.assertIn("layers.HATCH_CATEGORIES", script)
        # ...and the geometry rows are records-only again: the v0.69.7 merge
        # of region counts into the geometry table is gone
        self.assertNotIn("| set(region_counts)", script)

    def test_the_regions_never_consult_the_geometry_mapping(self):
        script = _script_source()
        self.assertRegex(script, r'layers\.apply_hatch_mapping\('
                                 r'dxf_result\.regions,\s*'
                                 r'selections\["hatch_mapping"\]\)')
        self.assertNotIn('apply_mapping(dxf_result.regions, '
                         'selections["mapping"])', script)
        self.assertNotIn('apply_hatch_mapping(dxf_result.regions, '
                         'selections["mapping"])', script)

    def test_the_mapping_is_persisted_and_restored(self):
        window = _window_source()
        capture = window.split("def _capture_settings(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("self._hatch_combos", capture)
        self.assertIn("hatches=hatch_map", capture)
        restore = window.split("def _restore_controls(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("settings.hatch_mappings(data)", restore)
        self.assertIn("self._hatch_combos", restore)


class TheHatchTableSplitsWhereTheLegendDoes(unittest.TestCase):
    """One row per layer, until the drawing's own legend gives it several.

    BUG-6: test14's HAT carries ANGLE, ANSI37 and HONEY (three sunk depths --
    150, 75 and 50 mm) plus GOST_GLASS ("SLAB AT BEAM BOTTOM", not a step at
    all), and a per-layer row can only say HAT -> sunk. The rule and its
    measured corpus effect are unit-tested in test_hatch_rows.py; what no
    offline harness can reach is the WPF window, so every wire from the split
    to the row, the mark and the depth box is pinned as text here. Each of
    them degrades SILENTLY if cut: the dialog opens with a coarser table and
    nobody is told.
    """

    def test_the_pushbutton_shapes_the_table_from_the_legend(self):
        script = _script_source()
        self.assertIn("layers.hatch_meanings(legend_entries)", script)
        self.assertIn("layers.hatch_rows(dxf_result.regions,", script)
        # the rows the window is handed are the SPLIT rows, keyed by row
        self.assertIn('hatch_rows = [(row["key"], row["count"])', script)
        self.assertIn("layers.default_hatch_row_mapping(hatch_table)", script)
        # ...and the legend is read before any of it
        self.assertLess(script.index("legend.read(dxf_result.regions"),
                        script.index("layers.hatch_rows(dxf_result.regions"))

    def test_a_split_layer_is_proposed_one_pattern_at_a_time(self):
        script = _script_source()
        # the whole-sheet per-layer proposal skips a layer that split...
        self.assertIn("if layer_name in split_layers:", script)
        # ...and each split row gets the same translation over its own
        # pattern's legend rows alone, marked with its own evidence
        self.assertRegex(script, r'legend\.propose\(\[entry for entry in '
                                 r'legend_entries\s*if entry\["pattern"\] == '
                                 r'row\["pattern"\]\]')
        self.assertIn('default_hatch_mapping[row["key"]] = category', script)
        self.assertIn('legend_notes[row["key"]] = own["rows"][row["layer"]]',
                      script)

    def test_the_depths_are_read_and_handed_over_by_pattern(self):
        script = _script_source()
        self.assertIn("legend.legend_steps(legend_entries)", script)
        self.assertIn("hatch_step_depths=hatch_step_depths", script)
        self.assertIn("hatch_row_patterns=hatch_row_patterns", script)

    def test_the_window_takes_the_patterns_and_the_depths(self):
        window = _window_source()
        self.assertIn("hatch_row_patterns=None, hatch_step_depths=None",
                      window)
        self.assertIn("self._hatch_step_depths = dict(hatch_step_depths or {})",
                      window)
        block = window.split("class CadToBimWindow", 1)[1].split(
            "def __init__(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("row_patterns=hatch_row_patterns", block)
        self.assertIn("depth_store=self._hatch_depth_boxes", block)

    def test_the_row_builder_grows_a_fourth_column_for_the_depths(self):
        block = _window_source().split("def _build_rows(", 1)[1].split(
            "\n    def ", 1)[0]
        # three columns as before for the geometry and text tables, four when
        # a depth store is handed in (the hatch table only)
        self.assertIn("(None, 70, 180) if depth_store is None "
                      "else (None, 70, 180, 70)", block)
        self.assertIn("self._depth_box(", block)

    def test_the_depth_box_belongs_to_the_pattern_not_the_row(self):
        block = _window_source().split("def _depth_box(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("if pattern in self._hatch_step_depths", block)
        self.assertIn("depth_store.append((tuple(carried), box)", block)
        # a row whose patterns carry no legend depth shows no box at all
        self.assertIn("return None", block)

    def test_the_depths_ride_collect_under_their_own_key(self):
        window = _window_source()
        collect = window.split("def _collect(", 1)[1].split("\n    def ",
                                                            1)[0]
        # the key the fold machinery reads: {pattern: depth mm}
        self.assertIn('"hatch_step_depths": self._read_hatch_depths()',
                      collect)
        block = window.split("def _read_hatch_depths(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("depths = dict(self._hatch_step_depths)", block)
        self.assertIn("for patterns, box in self._hatch_depth_boxes:", block)
        # an unreadable box keeps the legend's own figure
        self.assertIn("self._read_float(box, depths.get(pattern))", block)

    def test_an_edited_depth_survives_the_draw_stairs_round_trip(self):
        # the depths are NOT in the settings snapshot (they are this
        # drawing's, not the office's) -- so the preset has to carry them
        # itself, or a trip out to the view to draw stair outlines silently
        # resets every depth the user changed
        block = _window_source().split("def _apply_preset(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn('preset.get("hatch_step_depths")', block)
        restore = _window_source().split("def _restore_hatch_depths(",
                                         1)[1].split("\n    def ", 1)[0]
        self.assertIn("for patterns, box in self._hatch_depth_boxes:",
                      restore)

    def test_the_table_says_what_a_split_row_is(self):
        with open(_XAML, "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertIn('Text="Depth mm"', source)
        prose = [element.get("Text") for element in _body_iter(_XAML)
                 if "layer|PATTERN" in (element.get("Text") or "")]
        self.assertEqual(len(prose), 1, "the split is unexplained on the tab")
        self.assertIn("legend", prose[0])
        self.assertIn("negative", prose[0])

    def test_the_hatch_header_row_matches_the_rows_beneath_it(self):
        # the built rows are (name, count, meaning, depth); a header grid
        # that still had three columns would sit over the wrong cells
        header = None
        for element in _body_iter(_XAML):
            if element.tag.endswith("Grid"):
                captions = [child.get("Text") for child in element.iter()
                            if child.get("Text")]
                if "Hatch layer" in captions:
                    header = element
        self.assertIsNotNone(header, "the hatch table has no header row")
        columns = [child for child in header.iter()
                   if child.tag.endswith("ColumnDefinition")]
        self.assertEqual([child.get("Width") for child in columns],
                         ["*", "70", "180", "70"])


class TheDrawStairsRoundTripKeepsTheWholeDialog(unittest.TestCase):
    """Closing the window to draw outlines must not cost the user's settings.

    _apply_preset used to re-enumerate the dialog by hand and put back only
    the ~45 values it happened to name; every control added since fell to its
    default on reopen. The preset now carries the same snapshot a settings
    file does, restored through the same path, so the two cannot drift apart
    again.
    """

    def test_collect_carries_the_snapshot(self):
        block = _window_source().split("def _collect(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn('"preset_payload": self._capture_settings()', block)

    def test_the_preset_lands_through_the_settings_path(self):
        block = _window_source().split("def _apply_preset(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn('preset.get("preset_payload")', block)
        self.assertIn("self._restore_controls(", block)
        # the live parts the snapshot cannot carry keep their special handling
        self.assertIn('preset.get("storey_settings")', block)
        self.assertIn("self._show_outline_count()", block)


class OutcomesReachTheExportClean(unittest.TestCase):
    """The live ElementIds the material pass needs must not reach json.dump."""

    def _script_namespace(self):
        source = _builders_source()
        start = source.index('_IDS = "_element_ids"')
        end = source.index("def _skip_details(")
        namespace = {}
        exec(compile(source[start:end], "<script>", "exec"), namespace)
        return namespace

    def test_strip_ids_removes_the_id_key_and_keeps_the_rest(self):
        namespace = self._script_namespace()
        outcomes = {"columns": {"rect": 3, namespace["_IDS"]: ["id1", "id2"]},
                    "beams": {"created": 9},
                    "materials": {"column": {"elements": 3}}}
        clean = namespace["_strip_ids"](outcomes)
        self.assertNotIn(namespace["_IDS"], clean["columns"])
        self.assertEqual(clean["columns"]["rect"], 3)
        self.assertEqual(clean["beams"]["created"], 9)
        self.assertEqual(clean["materials"], {"column": {"elements": 3}})
        # the original is untouched: the material pass still needs the ids
        self.assertIn(namespace["_IDS"], outcomes["columns"])

    def test_every_material_kind_records_the_ids_it_created(self):
        """A creator that returns counts only is invisible to the material pass.

        `_create_beams` did exactly that: the beams outcome had no _IDS key, so
        `_apply_materials` found no elements and said "nothing of this kind was
        built" on every run with beams in it.
        """
        source = _builders_source()
        creator = {"column": "_create_columns", "beam": "_create_beams",
                   "slab": "_create_slabs", "stair": "_create_stairs",
                   "footing": "_create_footings"}
        tree = ast.parse(source)
        functions = dict((node.name, node) for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef))
        for kind, name in creator.items():
            node = functions.get(name)
            self.assertIsNotNone(node, "no %s in script.py" % name)
            records = False
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Dict):
                    continue
                for key in inner.keys:
                    if isinstance(key, ast.Name) and key.id == "_IDS":
                        records = True
            self.assertTrue(records,
                            "%s never records _IDS: %s takes no material"
                            % (name, kind))

    def test_no_outcome_dict_exports_an_id_list_under_a_plain_key(self):
        # reading a builder's own result["created_ids"] is fine; putting one
        # into an outcome dict under a plain key is what broke the export
        source = _builders_source()
        self.assertNotIn('"created_ids":', source,
                         "an outcome dict exports an id list under a plain key")


class TheDrawnFoundationsReachTheBuilder(unittest.TestCase):
    """The drawing-fed footing path is Revit-side, so only a static check sees it.

    Every link in it fails QUIETLY. Drop the records or the notes at the call
    and `plan_foundations` reads an empty drawing; drop `outlines=` and the
    builder falls back to the column-offset derivation. Either way the run says
    "footings created" and lays invented pads over a drawing that showed the
    real ones -- the same class of silent wrong answer as the swallowed type
    clash in v0.68.1, and unreachable by the offline harnesses because
    builders/footings.py imports Revit at module level.
    """

    def _function(self, source, name):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("no %s" % name)

    def _call(self, node, name):
        """The call to `name` (plain or dotted) inside `node`."""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = (func.id if isinstance(func, ast.Name)
                      else getattr(func, "attr", None))
            if called == name:
                return inner
        return None

    def test_the_storey_hands_its_geometry_and_notes_to_the_footings(self):
        call = self._call(self._function(_script_source(), "_build_one_storey"),
                          "_create_footings")
        self.assertIsNotNone(call, "_build_one_storey never creates footings")
        passed = set(keyword.arg for keyword in call.keywords)
        for argument in ("records", "texts"):
            self.assertIn(argument, passed,
                          "the footing pass is called without %s: the drawing's "
                          "own foundations cannot be read" % argument)

    def test_the_notes_are_routed_by_layer_and_never_fall_back_to_all_text(self):
        # a BARE "1200MM THK" is a raft on the foundation layer and a slab note
        # anywhere else; only the routing separates them, so the slab notes'
        # "use every text when nothing is routed" fallback would claim them
        source = _script_source()
        self.assertIn("CATEGORY_FOUNDATION_TEXT", source)
        assignments = [node for node in ast.walk(ast.parse(source))
                       if isinstance(node, ast.Assign)
                       and any(getattr(t, "id", None) == "foundation_texts"
                               for t in node.targets)]
        self.assertEqual(len(assignments), 1,
                         "foundation_texts is assigned more than once: one of "
                         "them is a fall back to every text in the drawing")
        self.assertIsInstance(assignments[0].value, ast.ListComp)

    def test_the_outlines_the_drawing_carries_reach_place_footings(self):
        node = self._function(_builders_source(), "_create_footings")
        self.assertIsNotNone(self._call(node, "plan_foundations"),
                             "the footing pass never reads the drawing")
        call = self._call(node, "place_footings")
        self.assertIsNotNone(call, "the footing pass places nothing")
        self.assertIn("outlines", [keyword.arg for keyword in call.keywords],
                      "place_footings is called without the drawn outlines: "
                      "every run falls back to pads invented from the columns")

    def test_the_hatches_are_moved_and_classified_like_everything_else(self):
        """A region read but never placed or categorised is a region ignored.

        The reader keeps hatches OUT of `records`, which is what stopped them
        reaching the column passes -- and also what stops them being carried by
        anything that walks records. Both passes have to name them explicitly.
        """
        source = _script_source()
        self.assertIn("transform.apply_to_records(text_affine, dxf_result.regions)",
                      source, "hatches are never moved into model coordinates")
        # apply_HATCH_mapping, not apply_mapping: a hatch row may be keyed by
        # (layer, pattern), and only the hatch version looks there
        self.assertIn("layers.apply_hatch_mapping(dxf_result.regions", source,
                      "hatches are never classified, so no fold is a fold")

    def test_each_storey_keeps_the_hatches_drawn_on_it(self):
        # one DXF holds every storey side by side; a fold belongs to the plan it
        # was drawn on, so the splitter has to carry hatches as it carries
        # records, or the foundation storey inherits the whole sheet's folds
        source = _script_source()
        self.assertIn("hatches=dxf_result.regions", source)
        self.assertIn("hatches=region.regions", source)
        call = self._call(self._function(_builders_source(), "_create_footings"),
                          "place_footings")
        self.assertIn("steps", [keyword.arg for keyword in call.keywords],
                      "the planned steps never reach the builder")

    def test_the_region_limit_is_read_where_the_dialog_files_it(self):
        # it lives in TOLERANCES, where the column pass reads it; the footing
        # pass looked in "limits" and so always found None, which meant the
        # user's own setting never reached it
        call = self._call(self._function(_builders_source(), "_create_footings"),
                          "place_footings")
        keyword = [k for k in call.keywords if k.arg == "region_max_side_mm"]
        self.assertEqual(len(keyword), 1)
        read = set(node.value for node in ast.walk(keyword[0])
                   if isinstance(node, ast.Constant)
                   and isinstance(node.value, str))
        self.assertIn("tolerances", read)
        self.assertNotIn("limits", read)


class TheWallsReachTheBuilder(unittest.TestCase):
    """The wall pass is Revit-side past the planner, so its wiring is static.

    `wall_plan` is unit-tested offline (test_wall_plan) and the sweep counts
    its segments; `builders/walls.py` imports Revit at module level, so no
    offline harness can execute it. Every link below fails QUIETLY if cut:
    drop the tolerances at the plan_walls call and the planner reads config
    defaults over the user's boxes; drop a selections key and a whole wall
    kind silently stops building; leave a combo unfilled and the type picker
    is decoration. Pinned as text, the way the foundation links are.
    """

    def _function(self, source, name):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("no %s" % name)

    def _call(self, node, name):
        """The call to `name` (plain or dotted) inside `node`."""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = (func.id if isinstance(func, ast.Name)
                      else getattr(func, "attr", None))
            if called == name:
                return inner
        return None

    def _walls_source(self):
        with open(_WALLS_BUILDER, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_each_kind_lives_on_its_own_discipline_tab(self):
        # the user's tab set: structural walls belong to Structure, arch
        # walls give Architecture its first real content
        homes = _tab_homes()
        for control, tab in (("chk_struct_walls", "Build > Structure"),
                             ("cb_struct_wall_type", "Build > Structure"),
                             ("chk_arch_walls", "Build > Architecture"),
                             ("cb_arch_wall_type", "Build > Architecture"),
                             ("tb_name_wall_struct", "Naming"),
                             ("tb_name_wall_arch", "Naming")):
            self.assertEqual(homes.get(control), tab,
                             "%s sits on %r" % (control, homes.get(control)))

    def test_the_pushbutton_offers_the_models_wall_types(self):
        # mirrors how floor types reach the slab picker: one document scan,
        # handed to the window by keyword
        script = _script_source()
        self.assertIn("walls.wall_types(doc)", script)
        self.assertIn("wall_type_options=wall_type_options", script)

    def test_the_window_fills_both_pickers_and_emits_the_selections(self):
        window = _window_source()
        self.assertIn('find("cb_struct_wall_type")', window)
        self.assertIn('find("cb_arch_wall_type")', window)
        collect = _window_source().split("def _collect(", 1)[1].split(
            "\n    def ", 1)[0]
        for key in ('"create_struct_walls"', '"create_arch_walls"',
                    '"struct_wall_type_id"', '"arch_wall_type_id"'):
            self.assertIn(key, collect,
                          "%s never leaves the dialog" % key)

    def test_the_storey_hands_its_records_to_the_wall_pass(self):
        call = self._call(self._function(_script_source(),
                                         "_build_one_storey"),
                          "_create_walls")
        self.assertIsNotNone(call, "_build_one_storey never creates walls")
        # the records ride positionally: doc, records, selections
        self.assertGreaterEqual(len(call.args), 2,
                                "the wall pass is called without records")
        records = call.args[1]
        self.assertEqual(getattr(records, "attr", None), "records",
                         "the second argument is not the storey's records: "
                         "the planner would read an empty drawing")

    def test_the_planner_gets_the_dialog_tolerances(self):
        # plan_walls quietly falls back to config defaults without them --
        # the user's pair-overlap and parallel-angle boxes would stop
        # reaching the walls while still reaching the beams
        call = self._call(self._function(_builders_source(), "_create_walls"),
                          "plan_walls")
        self.assertIsNotNone(call, "the wall pass never plans")
        self.assertIn("tolerances", [k.arg for k in call.keywords],
                      "plan_walls is called without the dialog tolerances")

    def test_both_kinds_place_through_one_guarded_transaction(self):
        block = _builders_source().split("def _create_walls(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("txn_failures.attach_warning_swallower(transaction)",
                      block)
        self.assertIn("walls.place_walls(", block)
        self.assertIn('structural=(kind == "structural")', block)
        # errors print in red, apart from the skip/note lines (the v0.69.3
        # convention every creator follows)
        self.assertIn('_say_error("  wall: {0}".format(message))', block)

    def test_place_walls_is_told_the_top_level_and_the_fallback_height(self):
        call = self._call(self._function(_builders_source(), "_create_walls"),
                          "place_walls")
        self.assertIsNotNone(call)
        passed = set(keyword.arg for keyword in call.keywords)
        for argument in ("top_level_id", "height_mm", "structural"):
            self.assertIn(argument, passed,
                          "place_walls is called without %s" % argument)

    def test_the_builder_sets_width_through_the_compound_structure(self):
        # a wall has NO width parameter: the number lives in the type's
        # compound structure, so the duplicate-and-resize is the whole
        # mechanism -- and a structure that refuses the width must land in
        # result["errors"], never raise out of the batch
        source = self._walls_source()
        for text in ("GetCompoundStructure", "SetLayerWidth",
                     "SetCompoundStructure",
                     'result["errors"].append(width_problem)'):
            self.assertIn(text, source)

    def test_the_builder_constrains_the_top_and_carries_the_kind(self):
        # structural walls rise base-to-top like columns, arch walls run to
        # the level above -- the constraint is WALL_HEIGHT_TYPE, attached
        # after Create the way columns attach FAMILY_TOP_LEVEL_PARAM; and
        # the `structural` bool on Wall.Create is what files the wall under
        # structure for the analytical model
        source = self._walls_source()
        self.assertIn("WALL_HEIGHT_TYPE", source)
        self.assertIn("Wall.Create(doc, line, wall_type.Id, base_level.Id,",
                      source)
        self.assertIn("height_ft, 0.0, False, structural)", source)

    def test_the_type_cache_is_keyed_by_kind_and_width(self):
        # a 200-wide shear wall and a 200-wide partition are two types with
        # two names (the Naming tab's separate rows); a width-only key would
        # hand one the other's type
        source = self._walls_source()
        self.assertIn("key = (kind, int(round(width_mm)))", source)
        self.assertIn("naming.struct_wall_type_name(", source)
        self.assertIn("naming.arch_wall_type_name(", source)


class TheColumnOrWallChoiceIsWired(unittest.TestCase):
    """Build > Structure's three-way: Column, Wall, or Combine (smart).

    "currently vertical members are being made using only Structure Column,
    but i want one toggle ... to use Structural Wall entire instead" -- the
    user's words. Column stays the DEFAULT, so a run nobody re-configures is
    the run it has always been; every link below fails quietly if cut, which
    is why each is pinned rather than trusted.
    """

    _WPF = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
    _KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"

    _BUTTONS = ("rb_vertical_column", "rb_vertical_wall",
                "rb_vertical_combine")

    def _radios(self):
        return dict((el.get(self._KEY), el) for el in _body_iter(_XAML)
                    if el.get(self._KEY) in self._BUTTONS)

    def _columns_source(self):
        with open(_COLUMNS_BUILDER, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_all_three_buttons_are_on_the_structure_sub_tab(self):
        homes = _tab_homes()
        for control in self._BUTTONS:
            self.assertEqual(homes.get(control), "Build > Structure",
                             "%s sits on %r" % (control, homes.get(control)))

    def test_they_are_one_group_so_only_one_can_be_chosen(self):
        radios = self._radios()
        self.assertEqual(sorted(radios), sorted(self._BUTTONS))
        groups = set(el.get("GroupName") for el in radios.values())
        self.assertEqual(len(groups), 1,
                         "the three readings are not one group: %s" % groups)
        self.assertNotIn(None, groups, "a radio with no GroupName is a tick")

    def test_column_is_the_one_checked_in_the_xaml(self):
        # the whole no-surprise guarantee rests on this line: a user who never
        # opens the row gets Structural Columns, exactly as before
        radios = self._radios()
        checked = [name for name, el in radios.items()
                   if el.get("IsChecked") == "True"]
        self.assertEqual(checked, ["rb_vertical_column"])

    def test_the_window_binds_all_three_and_emits_the_mode(self):
        window = _window_source()
        for control in self._BUTTONS:
            self.assertIn('find("%s")' % control, window,
                          "%s is decoration" % control)
        collect = window.split("def _collect(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('"vertical_member_mode"', collect,
                      "the choice never leaves the dialog")

    def test_the_dialog_names_the_modes_from_the_planner_not_by_hand(self):
        # three string literals in the window and a fourth in the planner is
        # how a renamed mode becomes a silently-ignored one
        window = _window_source()
        for constant in ("wall_plan.MODE_COLUMN", "wall_plan.MODE_WALL",
                         "wall_plan.MODE_COMBINE"):
            self.assertIn(constant, window, constant)

    def test_the_reader_falls_back_to_column(self):
        window = _window_source()
        block = window.split("def _vertical_member_mode(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("return wall_plan.MODE_COLUMN", block,
                      "no button checked must mean the run it always was")

    def test_the_help_prose_states_both_rules_in_the_users_terms(self):
        prose = [(el.get("Text") or "") for el in ET.parse(_XAML).iter(
            self._WPF + "TextBlock")
            if "length-to-thickness" in (el.get("Text") or "")]
        self.assertEqual(len(prose), 1, "the L/B note appears once")
        text = prose[0]
        # the ratio rule, in the words the user gave (ElementTree hands back
        # the DECODED text, so the &lt;/&gt; the XAML carries read as < and >)
        for phrase in ("aspect ratio of the cross-section",
                       "L/B < 4", "L/B >= 4",
                       "axial compression",
                       "in-plane bending and shear",
                       "IS 456", "IS 13920", "ACI 318"):
            self.assertIn(phrase, text, phrase)
        # ...and the mark rule beside it
        for phrase in ("C1 is a Column", "SW1 or W1 is a Wall"):
            self.assertIn(phrase, text, phrase)

    def test_the_help_prose_wears_the_help_style(self):
        for element in ET.parse(_XAML).iter(self._WPF + "TextBlock"):
            text = element.get("Text") or ""
            if "length-to-thickness" not in text and (
                    "no L/B and no long axis" not in text):
                continue
            self.assertEqual(element.get("Style"),
                             "{StaticResource HelpText}", text[:48])

    def test_the_classifier_is_offline_and_carries_its_codes(self):
        # the rule lives in classify/marks.py, which imports nothing but re --
        # so it is unit-tested outside Revit (test_vertical_members)
        with open(os.path.normpath(os.path.join(
                _HERE, "..", "classify", "marks.py")), "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertIn("WALL_ASPECT_RATIO = 4.0", source)
        self.assertNotIn("Autodesk.Revit", source)

    def test_the_split_is_offline_too(self):
        with open(os.path.normpath(os.path.join(_HERE, "..", "wall_plan.py")),
                  "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertIn("def split_vertical_members(", source)
        self.assertIn("def rect_wall_segment(", source)
        self.assertNotIn("Autodesk.Revit", source)

    def test_each_kind_goes_to_its_own_builder(self):
        # the point of the whole exercise: a member built as a wall is named
        # by the Naming tab's structural-wall row and sized through a wall
        # type's compound structure, never by the column template
        source = self._columns_source()
        block = source.split("def place_vertical_members(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("wall_plan.split_vertical_members(", block)
        self.assertIn("place_columns(doc, column_sections", block)
        self.assertIn("walls.place_walls(", block)
        self.assertIn("structural=True", block)

    def test_the_walls_ride_apart_from_the_columns(self):
        # "created" stays the columns: the material pass reads it as the
        # column ids, and a wall type keeps no structural material parameter
        block = self._columns_source().split(
            "def place_vertical_members(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('result["wall_ids"] = outcome["created"]', block)
        self.assertNotIn('result["created"] + outcome["created"]', block)

    def test_a_missing_wall_type_builds_columns_and_says_so(self):
        # place_walls raises on a base type it cannot resolve; losing a whole
        # mode to an empty picker on another group would be the silent kind
        block = self._columns_source().split(
            "def place_vertical_members(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("wall_type_id is None", block)
        self.assertIn("built as columns instead", block)

    def test_the_split_speaks_every_time(self):
        block = self._columns_source().split(
            "def place_vertical_members(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('result["notes"]', block)
        self.assertIn('split["console"]', block)

    def test_the_run_routes_through_the_three_way(self):
        # The whole feature is inert if _create_columns still calls the column
        # builder directly: the mode would be collected, persisted, shown, and
        # never consulted. Wall mode would silently build columns.
        block = _builders_source().split("def _create_columns(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("columns.place_vertical_members(", block)
        self.assertNotIn("columns.place_columns(", block)


class TheSlabScheduleReachesTheSlabs(unittest.TestCase):
    """test16 carries a Mark|Thk slab schedule and the floors kept the default
    type. The parser is unit-tested in test_thickness_schedule; this pins the
    two links that make it reach a slab, both of which fail silently -- a
    schedule nobody reads and a bay nobody sizes look identical in the model.
    """

    def test_the_slab_pass_reads_the_thickness_table(self):
        block = _builders_source().split("def _create_slabs(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("marks.parse_thickness_schedule(", block,
                      "the slab pass never reads a Mark|Thk schedule, so a "
                      "drawing that has one still falls back to the note")

    def test_it_is_read_from_the_whole_file_not_the_storey(self):
        # the table sits on its own annotation layer, outside every plan on the
        # sheet: measured on test16, the file reads 11 Mark|Thk rows and each of
        # its five storeys reads NONE, while four of them carry 62, 62, 62 and
        # 15 S-marks on the plan. Reading it off the storey sizes nothing.
        block = _builders_source().split("def _create_slabs(", 1)[1].split(
            "\ndef ", 1)[0]
        call = block.split("marks.parse_thickness_schedule(", 1)[1][:60]
        self.assertIn("schedule_texts", call)

    def test_the_thickness_wins_over_a_section_sharing_the_mark(self):
        # a thickness stated against the mark beats the first dimension of any
        # section that happens to carry it: assignment, not setdefault
        block = _builders_source().split("def _create_slabs(", 1)[1].split(
            "\ndef ", 1)[0]
        tail = block.split("marks.parse_thickness_schedule(", 1)[1][:400]
        self.assertIn("slab_schedule[mark] = thickness", tail)


class TheBlanketNoteReachesTheBuilders(unittest.TestCase):
    """The sheet's "ALL BEAMS ARE 750MM IN DEPTH U.N.O." wiring, pinned as text.

    The parser and both planners are unit-tested offline (test_blanket_notes)
    and the sweep counts what they size, but the wiring between them is
    Revit-side and every link in it fails QUIETLY:

      * read the note out of the ROUTED beam labels instead of the whole
        sheet, and it is found in every offline harness and never once in
        Revit -- a general note sits on a general-notes layer, which is routed
        to nothing;
      * drop `blanket_depth_mm` / `blanket_thickness_mm` at a call and the
        dialog's box and tick become decoration while the planners quietly
        keep reading the sheet;
      * drop the two report lines and hundreds of members take a depth nobody
        was told about -- the same class of silent wrong answer as the
        invented pads in v0.68.1.
    """

    def _function(self, source, name):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("no %s" % name)

    def _call(self, node, name):
        """The call to `name` (plain or dotted) inside `node`."""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = (func.id if isinstance(func, ast.Name)
                      else getattr(func, "attr", None))
            if called == name:
                return inner
        return None

    def test_the_controls_live_with_what_is_shared_by_every_element(self):
        # Moved off Structure at the owner's word: one note governs beams AND
        # slabs, so it belongs where the level pair and the grids are, not
        # inside either element's own group.
        homes = _tab_homes()
        for control in ("chk_blanket_note", "tb_blanket_beam_depth",
                        "tb_blanket_slab_thk", "lbl_blanket_note"):
            self.assertEqual(homes.get(control), "Build > General",
                             "%s sits on %r" % (control, homes.get(control)))

    def test_the_window_binds_all_four_and_emits_the_three_keys(self):
        window = _window_source()
        for control in ("chk_blanket_note", "tb_blanket_beam_depth",
                        "tb_blanket_slab_thk", "lbl_blanket_note"):
            self.assertIn('find("%s")' % control, window,
                          "%s is in the XAML but never bound" % control)
        collect = window.split("def _collect(", 1)[1].split("\n    def ", 1)[0]
        for key in ('"blanket_notes"', '"blanket_beam_depth_mm"',
                    '"blanket_slab_thickness_mm"'):
            self.assertIn(key, collect, "%s never leaves the dialog" % key)

    def test_the_note_is_read_from_the_whole_sheet_before_any_routing(self):
        # THE bug this pin exists for: beam_texts is the routed beam-label
        # subset and the sheet's general note is not in it, so reading the
        # note from there would find it in the sweep and never in Revit
        script = _script_source()
        self.assertIn("marks.sheet_defaults(dxf_result.texts)", script,
                      "the blanket note is not read from the whole drawing")
        self.assertIn("blanket_note=blanket_note", script,
                      "the dialog is never shown what the sheet proposed")

    def test_the_beam_pass_is_handed_the_figure_not_left_to_find_it(self):
        call = self._call(self._function(_script_source(), "_build_one_storey"),
                          "build_beam_segments")
        self.assertIsNotNone(call, "_build_one_storey never builds beams")
        self.assertIn("blanket_depth_mm", [k.arg for k in call.keywords],
                      "build_beam_segments is called without the blanket "
                      "depth: the dialog's box and tick reach nothing")

    def test_the_slab_pass_is_handed_the_figure_too(self):
        call = self._call(self._function(_builders_source(), "_create_slabs"),
                          "apply_slab_labels")
        self.assertIsNotNone(call, "the slab pass never labels its loops")
        self.assertIn("blanket_thickness_mm", [k.arg for k in call.keywords],
                      "apply_slab_labels is called without the blanket "
                      "thickness")

    def test_the_hatches_and_the_sheet_reach_both_sunk_passes(self):
        # The whole sunk pass is inert without these four keywords, and inert
        # silently: every creator has a `regions=None` default, so a missing
        # argument reads as "this drawing has no hatches" rather than as a bug.
        # The legend prices a pattern and the hatch says which member is priced,
        # so a pass handed one without the other can do nothing either.
        storey = self._function(_script_source(), "_build_one_storey")
        beams = self._call(storey, "_create_beams")
        self.assertIsNotNone(beams, "_build_one_storey never creates beams")
        beam_kwargs = [k.arg for k in beams.keywords]
        self.assertIn("regions", beam_kwargs,
                      "the beam pass is not handed the hatches: a beam under a "
                      "sunk strip can never be dropped")
        self.assertIn("texts", beam_kwargs,
                      "the beam pass is not handed the sheet's texts, so the "
                      "legend that prices the strip cannot be read")
        slabs = self._call(storey, "_create_slabs")
        self.assertIsNotNone(slabs, "_build_one_storey never creates slabs")
        slab_kwargs = [k.arg for k in slabs.keywords]
        self.assertIn("regions", slab_kwargs,
                      "the slab pass is not handed the hatches: no bay can step")
        # NOT `texts`: slab_texts is narrowed by routing and may no longer hold
        # the legend block, which is exactly what prices the bay.
        self.assertIn("sheet_texts", slab_kwargs,
                      "the slab pass is handed only its routed texts, which "
                      "cannot be trusted to still carry the legend")
        # and NOT `sheet_texts` either for the SCHEDULE: that list is this
        # storey's, and a Mark|Thk table is drawn once for the sheet, outside
        # every plan on it -- test16's five storeys read none of its 11 rows
        self.assertIn("schedule_texts", slab_kwargs,
                      "the slab pass reads its schedule from the storey, so a "
                      "multi-storey sheet's table reaches no bay at all")

    def test_one_function_turns_the_tick_and_the_boxes_into_one_number(self):
        # the dialog cannot send None, so the (tick, box) -> tri-state mapping
        # has to live in ONE place both passes call, or the two kinds drift
        self.assertIn("def blanket_mm(selections, key):", _builders_source())
        self.assertIn("def storey_blanket_mm(selections, key, note_key, texts):",
                      _builders_source())
        # both kinds go through the per-storey wrapper, so a sheet whose plans
        # carry different notes builds each plan to its own
        self.assertIn('"blanket_slab_thickness_mm", "slab_thickness_mm"',
                      _builders_source())
        self.assertIn('"blanket_beam_depth_mm", "beam_depth_mm"',
                      _script_source())

    def test_both_counts_are_said_out_loud(self):
        # a default applied silently is a default nobody can check
        self.assertIn('.get("blanket_depth", 0)', _script_source())
        self.assertIn("took the sheet's blanket depth", _script_source())
        self.assertIn("took the sheet's blanket thickness", _builders_source())

    def test_plans_that_differ_are_said_plainly_and_read_one_by_one(self):
        # Notes that disagree ACROSS PLANS are not a contradiction to refuse:
        # test14 writes 750/125 on two plans and 600/150 on the third, and the
        # owner confirmed that is deliberate. Nothing is settled for the SHEET,
        # which leaves the box empty on purpose, and each storey then reads the
        # note inside its own plan -- so this is a note, not an error.
        script = _script_source()
        self.assertIn('for key, values in blanket_note["conflicts"]:', script)
        block = script.split('blanket_note["conflicts"]', 1)[1][:900]
        self.assertNotIn("_say_error(", block,
                         "plans that legitimately differ are reported as a "
                         "refusal, which is no longer what happens")
        self.assertIn("each plan will use the note drawn inside it", block)

    def test_the_figures_come_from_this_drawing_not_from_the_last_run(self):
        # restoring last week's 750 onto a sheet that says 600 would put a
        # wrong depth on every unlabelled beam and say nothing -- so the two
        # boxes join the storey-detection controls: saved, never restored.
        # The TICK is a preference and restores normally.
        with open(os.path.normpath(os.path.join(_HERE, "..", "settings.py")),
                  "rb") as handle:
            settings_source = handle.read().decode("utf-8")
        block = settings_source.split("DETECTED_NAMES = frozenset(", 1)[1]
        block = block.split("))", 1)[0]
        for name in ("tb_blanket_beam_depth", "tb_blanket_slab_thk"):
            self.assertIn(name, block,
                          "%s would be restored from another drawing" % name)
        self.assertNotIn("chk_blanket_note", block,
                         "the tick is a preference, not a drawing fact")


class StoreyTableIsSelectable(unittest.TestCase):
    """The storey stack has to be pickable, and visibly so.

    Rows were a StackPanel of Grids with a click handler on the Grid: the combo
    box and text boxes inside each row swallowed the mouse, so the handler
    rarely fired and nothing ever looked selected. A ListBox gives native
    selection -- highlight, arrow keys, SelectedIndex -- for free.
    """

    def test_the_storey_table_is_a_listbox(self):
        tree = ET.parse(_XAML)
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        found = [el for el in tree.iter() if el.get(key) == "storey_rows"]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].tag.endswith("ListBox"),
                        "storey_rows is %s, not a ListBox" % found[0].tag)

    def test_the_row_click_is_a_preview_handler(self):
        # a bubbling handler never sees the click: the child controls take it
        source = _window_source()
        self.assertIn("PreviewMouseLeftButtonDown", source)
        self.assertNotIn("grid.MouseLeftButtonDown", source)

    def test_selection_drives_the_move_buttons(self):
        source = _window_source()
        self.assertIn("self.storey_rows.SelectedIndex", source)
        self.assertIn("storey_selection_text", source)
        names = _xaml_names(_XAML)
        for control in ("btn_storey_up", "btn_storey_down", "btn_storey_add",
                        "btn_storey_remove", "storey_selection_text"):
            self.assertIn(control, names)


class LevelNamesReachTheBuilder(unittest.TestCase):
    """The Naming tab decides what a created level is called.

    _storey_level_pairs hard-coded "CAD Level {0}" at the Level.Create call, so
    naming.level_name -- written and tested -- was called by nothing at all.
    """

    def test_the_level_name_comes_from_naming(self):
        source = _script_source()
        self.assertIn("naming.level_name(", source)
        self.assertIn("naming.next_level_names(", source)

    def test_no_hard_coded_level_name_is_left(self):
        source = _script_source()
        self.assertNotIn('"CAD Level {0}".format', source)

    def test_following_the_model_is_a_choice_the_dialog_offers(self):
        # the tick is on the dialog, the decision is read in the run pipeline
        source = _all_source()
        self.assertIn('"level_follow_existing"', source)
        self.assertIn("self.chk_level_follow", source)


class TheEngineKeepsModulesBetweenRuns(unittest.TestCase):
    """A fresh click must run the library on disk, not last session's copy.

    The CPython3 engine outlives a run: script.py is re-read every click, its
    imports are not. v0.67.1 shipped naming.next_level_names and a session that
    had already run v0.67.0 raised AttributeError on it until Revit restarted.
    """

    def test_stale_modules_are_dropped_before_the_imports(self):
        source = _script_source()
        purge = source.index("def _drop_stale_modules(")
        call = source.index("\n_drop_stale_modules()")
        first_import = source.index("\nfrom anongee_toolkit import cad2bim")
        registry = source.index("\nimport anongee_clr")
        self.assertLess(purge, call)
        self.assertLess(call, first_import)
        # the CLR registry is imported AFTER the purge and is not part of it:
        # it holds this session's emitted types and must outlive the reload
        self.assertLess(call, registry)
        self.assertLess(registry, first_import)

    def test_the_parent_attribute_goes_too(self):
        # `from anongee_toolkit import cad2bim` reads the attribute off the
        # parent module and never consults sys.modules
        source = _script_source()
        block = source.split("def _drop_stale_modules(", 1)[1].split(
            "\n\n_bootstrap", 1)[0]
        self.assertIn("del sys.modules[name]", block)
        self.assertIn("delattr(parent", block)

    def test_a_library_older_than_the_button_says_so_up_front(self):
        source = _script_source()
        self.assertIn("_library_mismatch()", source)
        for attribute in ("next_level_names", "recover_face_columns",
                          "loops_for_unclaimed_notes"):
            self.assertIn(attribute, source)


class AnOldLibraryIsReportedNotCrashed(unittest.TestCase):
    """The button imports five modules that a stale library will not have.

    Those imports run at MODULE level, before main() can catch anything, so an
    ImportError there would surface as a raw traceback instead of the sentence
    _library_mismatch exists to give. The import is therefore deferred into a
    reported failure -- and the report itself needs names the failed import was
    supposed to provide.
    """

    def test_the_new_module_imports_are_guarded(self):
        source = _script_source()
        block = source.split("_MISSING_MODULE = None", 1)[1].split(
            "_HERE = ", 1)[0]
        self.assertIn("try:", block)
        self.assertIn("except ImportError", block)
        for module in ("run_builders", "run_picking", "ui_window", "ui_dialogs",
                       "run_console"):
            self.assertIn(module, block, "%s imported outside the guard" % module)

    def test_the_failure_path_can_still_talk(self):
        """Every name main() uses to REPORT the failure must have a fallback."""
        source = _script_source()
        tree = ast.parse(source)
        handler = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for candidate in node.handlers:
                if any(isinstance(inner, ast.Assign)
                       and getattr(inner.targets[0], "id", "") == "_MISSING_MODULE"
                       for inner in ast.walk(candidate)):
                    handler = candidate
        self.assertIsNotNone(handler, "the guarded import has no handler")
        defined = set()
        for node in ast.walk(handler):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
        for name in ("_say", "_alert", "_error", "_OUT", "_close_progress"):
            self.assertIn(name, defined,
                          "%s has no fallback: the report would raise" % name)

    def test_the_missing_module_reaches_the_report(self):
        source = _script_source()
        block = source.split("def _library_mismatch(", 1)[1].split("\n\n\n", 1)[0]
        self.assertIn("_MISSING_MODULE", block)


class TheAdvancedWindowIsGatedAndWired(unittest.TestCase):
    """The Advanced settings window: its button, its gate, and its shell.

    The rows themselves are code-built from advanced.REGISTRY (like the layer
    table), so what the static check can pin is everything around them: the
    button lives on Output & Graphics, the click goes through the Yes/No gate
    before any window opens, the shell XAML declares the panel and the three
    buttons the dialog binds, and the warning prose is the one the gate
    repeats.
    """

    def test_the_button_lives_on_output_and_graphics(self):
        homes = _tab_homes()
        self.assertEqual(homes.get("btn_advanced"), "Output & Graphics",
                         "btn_advanced sits on %r" % homes.get("btn_advanced"))

    def test_the_click_goes_through_the_confirmation_gate(self):
        block = _window_source().split("def on_advanced(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("_confirm(", block)
        self.assertIn("AdvancedSettingsDialog(", block)
        # the risk statement is IN the gate, not only in the window behind it
        self.assertIn("fails quietly", block)
        # the gate refuses by default: the dialog only opens inside the branch
        self.assertLess(block.index("_confirm("),
                        block.index("AdvancedSettingsDialog("))

    def test_the_shell_declares_what_the_dialog_binds(self):
        names = _xaml_names(_ADV_XAML)
        for control in ("advanced_rows", "advanced_version_text",
                        "advanced_warning_text", "btn_adv_reset",
                        "btn_adv_apply", "btn_adv_cancel"):
            self.assertIn(control, names)

    def test_the_warning_header_states_the_risk_and_the_way_back(self):
        tree = ET.parse(_ADV_XAML)
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        warning = [el for el in tree.iter()
                   if el.get(key) == "advanced_warning_text"]
        self.assertEqual(len(warning), 1)
        text = warning[0].get("Text") or ""
        for sentence in ("These change how drawings are read",
                         "fails quietly", "Reset restores every default"):
            self.assertIn(sentence, text)

    def test_the_rows_render_the_registry_not_a_second_list(self):
        block = _window_source().split("class AdvancedSettingsDialog", 1)[1].split(
            "\nclass ", 1)[0]
        self.assertIn("for entry in advanced.REGISTRY", block)
        self.assertIn("entry.effect", block)
        self.assertIn("entry.unit", block)

    def test_the_values_ride_collect_capture_and_restore(self):
        source = _window_source()
        collect = source.split("def _collect(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn('"advanced": dict(self._advanced_values)', collect)
        capture = source.split("def _capture_settings(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("advanced=dict(self._advanced_values)", capture)
        restore = source.split("def _restore_controls(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("settings.advanced_overrides(data)", restore)
        remember = source.split("def _remember_conventions(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn("advanced.save(self._advanced_values)", remember)

    def test_the_pushbutton_applies_the_overrides_before_any_planning(self):
        # the saved overrides must rebind BEFORE storey detection runs --
        # floor_plans is a registered consumer -- and again from the dialog's
        # result so an edit takes effect on the run it was made for
        source = _script_source()
        self.assertIn('advanced.apply(_saved_prefs.get("advanced") or {})',
                      source)
        self.assertLess(
            source.index('advanced.apply(_saved_prefs.get("advanced")'),
            source.index("floor_plans.autodetect_storeys("))
        self.assertIn('advanced.apply(selections.get("advanced") or {})',
                      source)

    def test_the_advanced_xaml_reaches_use_xaml(self):
        source = _script_source()
        self.assertIn('os.path.join(_HERE, "advanced.xaml")', source)
        self.assertIn("ui_window.use_xaml(_XAML, _LINK_XAML, _ADVANCED_XAML)",
                      source)


class SettingsSaveAndLoad(unittest.TestCase):
    """The whole dialog has to survive a Revit session, not just two boxes."""

    def test_the_footer_has_both_buttons(self):
        names = _xaml_names(_XAML)
        for control in ("btn_settings_save", "btn_settings_load", "status_text"):
            self.assertIn(control, names)

    def test_the_buttons_are_wired(self):
        source = _all_source()
        self.assertIn("self.btn_settings_save.Click += self.on_settings_save",
                      source)
        self.assertIn("self.btn_settings_load.Click += self.on_settings_load",
                      source)

    def test_the_run_remembers_the_whole_dialog(self):
        source = _all_source()
        self.assertIn('"dialog": self._capture_settings()', source)
        self.assertIn('_saved_prefs.get("dialog")', source)
        self.assertIn("saved_settings=saved_settings", source)

    def test_capture_is_driven_by_the_xaml_names(self):
        """Listing controls by hand is how a new one gets forgotten."""
        source = _all_source()
        self.assertIn("for name in _control_names():", source)
        self.assertIn("settings.saveable(name)", source)
        self.assertIn("settings.restorable(name)", source)

    def test_every_saveable_xaml_control_is_a_kind_capture_understands(self):
        """A control type _control_value cannot read saves as nothing at all."""
        known = ("TextBox", "CheckBox", "RadioButton", "ComboBox", "Slider",
                 "TextBlock", "ListBox", "Button", "StackPanel", "Grid",
                 "Border", "Expander", "TabItem", "ScrollViewer", "Window",
                 "Separator", "Label", "ToggleButton")
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        unknown = []
        for element in _body_iter(_XAML):
            name = element.get(key)
            if not name:
                continue
            tag = element.tag.rsplit("}", 1)[-1]
            if tag not in known:
                unknown.append((name, tag))
        self.assertEqual(unknown, [],
                         "settings cannot read these control types: %s"
                         % unknown)


class TheDialogsSpeakTheTheme(unittest.TestCase):
    """Brand pass: tokens, not hex (AnonGee Brand Guidelines 3 / 12.3 / 13.4).

    The dialogs inline the shared theme under Window.Resources -- the one
    strategy that survives Revit's pyRevit sandbox (12.7.B; runtime-merged
    dictionaries fail to resolve there). Two things keep the copies honest:
    a colour literal may exist ONLY on the token primitives themselves, and
    any token that also exists in the shared Resources/*.xaml dictionaries
    must carry the same value -- an inline copy that drifts is a defect
    (12.3). The last two checks pin the template rules that crash or fail
    silently inside Revit: no resource reference on the root Window element
    (12.7.A) and PART_EditableTextBox wherever an editable ComboBox gets a
    custom template (12.7.C).
    """

    _DIALOGS = (_XAML, _LINK_XAML, _ADV_XAML)
    _WPF = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
    _KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
    _NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    _HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    _REF = re.compile(r"\{StaticResource\s+([A-Za-z0-9_]+)\}")
    # the tiers that may carry a literal colour: Tier-1 primitives and the
    # elevation shadows (13.1); everything else must reference a token key
    _PRIMITIVES = ("Color", "SolidColorBrush", "GradientStop",
                   "DropShadowEffect")

    def _tokens(self, path):
        """{key: value} for every primitive token a dictionary declares."""
        out = {}
        for element in ET.parse(path).iter():
            key = element.get(self._KEY)
            if not key:
                continue
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "SolidColorBrush":
                out[key] = ("Brush", (element.get("Color") or "").strip())
            elif tag == "Color":
                out[key] = ("Color", (element.text or "").strip())
            elif tag == "Double":
                out[key] = ("Double", (element.text or "").strip())
            elif tag == "FontFamily":
                out[key] = ("FontFamily", (element.text or "").strip())
        return out

    def test_hex_literals_live_only_on_token_primitives(self):
        for path in self._DIALOGS:
            for element in ET.parse(path).iter():
                tag = element.tag.rsplit("}", 1)[-1]
                if tag in self._PRIMITIVES:
                    continue
                for attribute, value in element.attrib.items():
                    self.assertIsNone(
                        self._HEX.search(value),
                        "%s hardcodes %r as %s on <%s> -- use a theme token"
                        % (os.path.basename(path), value, attribute, tag))

    def test_every_referenced_token_is_declared_before_use(self):
        # XamlReader resolves StaticResource eagerly, so a key referenced
        # above its declaration (or never declared) dies at parse time in
        # Revit -- exactly where these checks exist not to look
        for path in self._DIALOGS:
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            for match in self._REF.finditer(source):
                token = match.group(1)
                declared = source.find('x:Key="%s"' % token)
                self.assertGreaterEqual(
                    declared, 0, "%s references undeclared token %r"
                    % (os.path.basename(path), token))
                self.assertLess(
                    declared, match.start(),
                    "%s references %r above its declaration"
                    % (os.path.basename(path), token))

    def test_the_inline_tokens_match_the_shared_dictionaries(self):
        # 12.3: an inline copy is verbatim -- same key, same value as
        # Resources/*.xaml; a hand-edited variant is a defect
        shared = {}
        for name in ("Colors.xaml", "Typography.xaml"):
            shared.update(self._tokens(os.path.join(_RESOURCES, name)))
        for path in self._DIALOGS:
            for key, value in self._tokens(path).items():
                if key not in shared:
                    continue   # local additions (FontSizeHelp) are fine
                self.assertEqual(
                    value, shared[key],
                    "%s drifts from Resources/ on %r: %r != %r"
                    % (os.path.basename(path), key, value, shared[key]))

    def test_the_dialogs_actually_wear_the_brand(self):
        # each dialog carries the charcoal header band, the 3px Vivid Red
        # rule and a primary action -- the section 12.6 window anatomy
        for path in self._DIALOGS:
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            for token in ("BrushCharcoalBlack", "BrushVividRed",
                          "ButtonPrimary", "TextH2OnDark"):
                self.assertIn("{StaticResource %s}" % token, source,
                              "%s never uses %s"
                              % (os.path.basename(path), token))

    def test_no_resource_reference_on_the_root_window(self):
        # 12.7.A: XamlReader resolves root Window attributes BEFORE
        # Window.Resources is parsed; a reference there throws in Revit
        for path in self._DIALOGS:
            root = ET.parse(path).getroot()
            self.assertTrue(root.tag.endswith("Window"))
            for attribute, value in root.attrib.items():
                self.assertNotIn("{StaticResource", value,
                                 "%s: StaticResource on root %s"
                                 % (os.path.basename(path), attribute))
                self.assertNotIn("{DynamicResource", value,
                                 "%s: DynamicResource on root %s"
                                 % (os.path.basename(path), attribute))

    def _input_combo_template_names(self, path):
        """x:Names inside the InputComboBox style, or None if no such style."""
        for style in ET.parse(path).iter(self._WPF + "Style"):
            if style.get(self._KEY) != "InputComboBox":
                continue
            return set(el.get(self._NAME) for el in style.iter()
                       if el.get(self._NAME))
        return None

    def test_editable_combos_get_the_editable_template(self):
        # 12.7.C: an editable ComboBox whose template lacks
        # PART_EditableTextBox renders but silently refuses typed input
        for path in self._DIALOGS:
            editable = [el for el in _body_iter(path)
                        if el.tag == self._WPF + "ComboBox"
                        and el.get("IsEditable") == "True"]
            if not editable:
                continue
            names = self._input_combo_template_names(path)
            self.assertIsNotNone(names, "%s has editable combos but no "
                                 "InputComboBox style"
                                 % os.path.basename(path))
            for part in ("PART_EditableTextBox", "PART_Popup"):
                self.assertIn(part, names,
                              "%s: InputComboBox template lacks %s"
                              % (os.path.basename(path), part))
            for combo in editable:
                self.assertEqual(combo.get("Style"),
                                 "{StaticResource InputComboBox}",
                                 "editable combo %r does not wear the "
                                 "editable-capable template"
                                 % combo.get(self._NAME))


class TheRunGoesToAViewItCanLinkInto(unittest.TestCase):
    """BUG-25. Every link the owner starts from a schedule or a sheet died on
    `ArgumentException: The view is not printable`, and his fix was to move him
    rather than tell him. The rule is unit-tested in test_views; this pins the
    two Revit calls that act on it, both of which fail silently if they drift.
    """

    def test_the_host_view_is_settled_BEFORE_the_dxf_is_linked(self):
        source = _script_source()
        self.assertIn("_ensure_link_host_view(doc, uidoc)", source,
                      "the run never checks whether the active view can host "
                      "the link")
        self.assertLess(source.index("_ensure_link_host_view(doc, uidoc)"),
                        source.index("dxf_linker.link_dxf("),
                        "the view must be settled before Link is called, not "
                        "after it has already thrown")

    def test_it_asks_the_shared_rule_rather_than_re_deciding_here(self):
        block = _builders_source().split("def _ensure_link_host_view(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("views.can_host_link(", block)
        self.assertIn("views.choose_host(", block)

    def test_a_view_TEMPLATE_is_never_offered_as_the_host(self):
        block = _builders_source().split("def _ensure_link_host_view(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("not v.IsTemplate", block)

    def test_the_switch_is_on_the_UI_document_not_the_database_one(self):
        # doc.ActiveView is read-only; only uidoc.ActiveView moves the user
        block = _builders_source().split("def _ensure_link_host_view(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("uidoc.ActiveView = chosen", block)


class TheRunEndsShowingTheModel(unittest.TestCase):
    """FEAT-11: "auto open the 3D view if not active by user and zoom to fit"."""

    def test_both_finishes_show_the_model(self):
        # the multi-storey path and the single-storey path each end on their
        # own line, and a fix applied to one of them only is the usual bug
        self.assertEqual(_script_source().count("_show_the_model(doc, uidoc)"), 2)

    def test_it_opens_a_3D_view_and_zooms_it(self):
        block = _builders_source().split("def _show_the_model(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("views.choose_3d(", block)
        self.assertIn("uidoc.ActiveView = candidates[index]", block)
        self.assertIn("_zoom_to_model(doc, uidoc)", block)

    def test_the_zoom_frames_the_MODEL_not_the_link_and_the_datums(self):
        # the owner, on the first one: "it also takes LinkedCAD and Level or
        # Grid on Zoom to fit, what actually want was it should only zoom to
        # fit BIM model"
        block = _builders_source().split("def _zoom_to_model(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("views.counts_as_model(", block)
        self.assertIn("ImportInstance", block,
                      "the linked DXF must be excluded by type, not by name")
        self.assertIn("ZoomAndCenterRectangle(box[0], box[1])", block)

    def test_a_model_with_nothing_to_frame_still_zooms(self):
        block = _builders_source().split("def _zoom_to_model(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("ZoomToFit()", block,
                      "an empty run must still frame something")


class TheRunSaysHowLongItTook(unittest.TestCase):
    """FEAT-12: the elapsed-time window, its headline and its three exits."""

    def test_the_clock_starts_on_the_first_line_of_the_command(self):
        # "from when user click the run command" -- before any dialog
        body = _script_source().split("def main():", 1)[1][:600]
        self.assertIn("clicked_at = time.time()", body)

    def test_the_build_is_timed_separately_from_the_dialogs(self):
        source = _script_source()
        self.assertIn("build_started = time.time()", source)
        self.assertLess(source.index('selections = window.result'),
                        source.index("build_started = time.time()"),
                        "the build clock must start when the settings window "
                        "closes, not while the user is still reading it")

    def test_both_finishes_report_the_time(self):
        # the calls, not the definition line that shares the signature
        calls = [line for line in _script_source().splitlines()
                 if line.strip() == "_report_elapsed(clicked_at, build_started)"]
        self.assertEqual(len(calls), 2,
                         "the multi-storey finish and the single-storey finish "
                         "must both report the time")

    def test_the_window_carries_the_headline_and_the_countdown(self):
        names = _xaml_names(_ELAPSED_XAML)
        for control in ("txt_elapsed", "txt_breakdown", "txt_countdown",
                        "btn_close"):
            self.assertIn(control, names,
                          "elapsed.xaml has no {0}".format(control))

    def test_the_time_is_the_biggest_boldest_thing_on_it(self):
        # the owner asked for it "in BOLD and BIGGER", so this is the feature,
        # not styling: a headline that quietly loses its size is the bug
        root = ET.parse(_ELAPSED_XAML).getroot()
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        headline = [el for el in _body_iter(_ELAPSED_XAML)
                    if el.get(key) == "txt_elapsed"]
        self.assertEqual(len(headline), 1)
        self.assertEqual(headline[0].get("FontWeight"), "Bold")
        self.assertGreaterEqual(float(headline[0].get("FontSize") or 0), 24.0)

    def test_it_closes_three_ways(self):
        block = _dialogs_source().split("def show_elapsed(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("DispatcherTimer", block, "nothing closes it on its own")
        self.assertIn("Key.Escape", block, "Esc does not close it")
        self.assertIn("button.Click += close", block, "the button does not")

    def test_the_window_stays_up_long_enough_to_read(self):
        # the owner's number: "make dialog box stay upto 30s, because 10s go by
        # very quickly". One line holds it, which is the line he was told to edit.
        self.assertIn("ELAPSED_AUTO_CLOSE_SECONDS = 30", _dialogs_source())
        self.assertIn("auto_close_seconds=ELAPSED_AUTO_CLOSE_SECONDS",
                      _dialogs_source(),
                      "the window must take the constant as its default, or "
                      "editing that one line changes nothing")

    def test_the_headline_is_the_BUILD_and_the_parts_are_underneath(self):
        # his call after seeing the first one: the big number is the build
        # alone, with the dialog time and the total below it
        block = _dialogs_source().split("def _elapsed_parts(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("views.format_elapsed(build_seconds)", block)
        names = _xaml_names(_ELAPSED_XAML)
        self.assertIn("txt_waiting", names)
        self.assertIn("txt_total", names)

    def test_the_caption_figures_are_red_and_bold_but_caption_sized(self):
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        fields = dict((el.get(key), el) for el in _body_iter(_ELAPSED_XAML)
                      if el.get(key) in ("txt_waiting", "txt_total",
                                         "txt_elapsed"))
        for name in ("txt_waiting", "txt_total"):
            self.assertEqual(fields[name].get("FontWeight"), "Bold")
            self.assertIn("VividRed", fields[name].get("Foreground") or "")
            # caption-sized means it takes the caption style rather than a
            # size of its own -- the headline is the only thing with one
            self.assertIsNone(fields[name].get("FontSize"))
        self.assertIsNotNone(fields["txt_elapsed"].get("FontSize"))

    def test_a_failed_stopwatch_never_costs_the_owner_a_good_build(self):
        block = _dialogs_source().split("def show_elapsed(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("except Exception", block)


class TheMappingTablesTakeManyRowsAtOnce(unittest.TestCase):
    """FEAT-13, second attempt, pinned rather than run.

    The first one hand-rolled Explorer's click rules on mouse events. The owner:
    "without Ctrl hold i can select multiple which is not good. and i could not
    unselect it with ctrl + click ... it should follow `OneFilterParameter.
    pushbutton` reference". So WPF owns the clicking now -- real ListBoxItems in
    a `SelectionMode="Extended"` ListBox, which is what that reference uses and
    what this dialog's own storey table has used all along.

    These hold what is left: that the tables really are multi-select lists, that
    the one rule still ours goes through `selection.spread`, and that the
    hand-rolled machinery is gone rather than merely bypassed.
    """

    def test_all_three_tables_are_extended_selection_lists(self):
        xaml = _xaml_source()
        for name in ("layer_rows", "text_rows", "hatch_rows"):
            block = xaml.split('x:Name="%s"' % name, 1)[1][:400]
            self.assertIn('SelectionMode="Extended"', block, name)
            self.assertIn("ListBox", xaml.split('x:Name="%s"' % name, 1)[0][-120:],
                          name)

    def test_the_rows_are_real_list_items_so_wpf_can_select_them(self):
        source = _window_source()
        block = source.split("def _build_rows(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("ListBoxItem()", block)
        self.assertIn("panel.Items.Add(item)", block)

    def test_nothing_hand_rolls_the_click_rules_any_more(self):
        source = _window_source()
        for gone in ("_ctrl_held", "_shift_held", "ModifierKeys",
                     "_wire_selection", "bulk_bar"):
            self.assertNotIn(gone, source, "%s survived the rewrite" % gone)

    def test_no_apply_button_or_second_dropdown_is_left_in_the_xaml(self):
        xaml = _xaml_source()
        for gone in ("layer_bulk", "text_bulk", "hatch_bulk"):
            self.assertNotIn(gone, xaml)

    def test_changing_a_selected_row_spreads_through_selection_spread(self):
        source = _window_source()
        self.assertIn("selection.spread(", source)
        self.assertIn("combo.SelectionChanged += self._spread_to_selection",
                      source)

    def test_the_spread_cannot_echo_itself(self):
        # Setting the other combos raises SelectionChanged on each of them.
        block = _window_source().split("def _spread_to_selection(", 1)[1]
        block = block.split("\n    def ", 1)[0]
        self.assertIn("_spreading", block)
        self.assertIn("finally:", block)


class AColumnIsBuiltOnceOverItsWholeRun(unittest.TestCase):
    """FEAT-16, pinned rather than run: both ends of it import Revit.

    A multi-storey sheet is built one plan per storey, so a column running
    eleven floors came out as eleven one-storey columns stacked on each other.
    `column_extent` decides where each one really begins and ends -- and it is
    unit-tested on its own, standalone -- but the deciding is worthless unless
    the run asks it BEFORE the first storey is built and the builder groups its
    rectangles by the answer. Those two joints are what these hold.

    Measured on test17: 2344 drawn outlines over 13 floors are 386 columns,
    196 of them running through more than one storey.
    """

    def test_the_whole_stack_is_read_before_the_first_storey_is_built(self):
        source = _script_source()
        planned = source.index("column_extent.plan(")
        loop = source.index("for index, (region, label) in enumerate(built)")
        self.assertLess(planned, loop,
                        "a column's span is only knowable from every plan it "
                        "appears on, so the read cannot be inside the loop")

    def test_every_storey_s_footprints_go_into_the_one_read(self):
        source = _script_source()
        self.assertIn("_column_footprints(region.records)", source)
        self.assertIn("for region, _lbl in built", source)

    def test_a_footprint_carries_its_drawn_section_not_just_its_place(self):
        # Without the size a column that reduces up the building is one column
        # at the bottom storey's section, and 126 of test17's 219 reduce.
        block = _script_source().split("def _column_footprints(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("304.8", block)
        self.assertIn("max(xs) - min(xs)", block)
        self.assertIn("max(ys) - min(ys)", block)

    def test_the_answer_reaches_the_builder_through_the_selections(self):
        source = _script_source()
        block = source.split('storey_selections["column_extents"]', 1)[1][:300]
        for key in ('"columns"', '"spans"', '"storey"', '"top_ids"'):
            self.assertIn(key, block, key)

    def test_the_builder_groups_its_rectangles_by_the_level_they_reach(self):
        source = _builders_source()
        block = source.split("def _create_columns(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_column_groups(sections, selections)", block)
        self.assertIn("for group_sections, group_top in groups:", block)
        self.assertIn("_merge_placed(result, placed)", block)

    def test_a_rectangle_finds_its_column_by_position_not_by_index(self):
        # The footprints come from the drawing's records and the rectangles from
        # `decompose_to_rectangles`, which splits some and drops others: the two
        # lists never line up, and matching them by index would put spans on the
        # wrong columns silently.
        block = _builders_source().split("def _column_groups(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("column_extent.assign(columns, rect[\"center\"],", block)
        # WITH ITS OWN SIZE. A grid point can hold two members -- one stopping
        # on this floor, one carrying on above, concentric and a different
        # section -- and position alone gives the rectangle to whichever of them
        # the records happened to list first (BUG-35).
        self.assertIn('(rect["width_mm"], rect["height_mm"])', block)
        self.assertIn("column_extent.plan_storey(keys, spans, storey)", block)

    def test_a_group_keeps_the_entries_it_came_from(self):
        # The entry carries the drawing's own layer and whether the outline was
        # approximated; a group that flattened them into one nameless entry
        # would take both out of everything downstream that reads them.
        block = _builders_source().split("def _column_groups(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("dict(source[number], rectangles=kept)", block)

    def test_a_single_storey_run_is_left_exactly_as_it_was(self):
        block = _builders_source().split("def _column_groups(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("if not plan:", block)
        self.assertIn("return [(sections, top_id)], 0", block)

    def test_a_storey_with_nothing_left_of_its_own_places_nothing(self):
        # test17's terrace is 58 members and every one was built lower down and
        # carried up to it. Rebuilding the storey when no group came back would
        # put a second column inside each of them.
        block = _builders_source().split("def _create_columns(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        after = block.split("if result is None:", 1)[1][:600]
        self.assertNotIn("place_vertical_members", after)
        self.assertIn('"created": []', after)

    def test_what_was_carried_up_from_below_is_said_out_loud(self):
        block = _builders_source().split("def _create_columns(", 1)[1]
        block = block.split("\ndef ", 1)[0]
        self.assertIn("carried", block)
        self.assertIn("_START/_STOP", block)


class TheBoundaryZonesAreFoldedBeforeAnythingReadsThem(unittest.TestCase):
    """FEAT-17, pinned: the fold itself is unit-tested, the wiring is not.

    One element family per zone box means no two families' outlines lie on top
    of one another, which is the only thing Revit's link eats. The fold has to
    happen BEFORE the storeys are split and before anything is compared, or
    every pass downstream sees four copies of the drawing -- which is exactly
    what the owner's 0.97.1 run of the zone file did: 346 columns, 178 of them
    a second copy from the combine zone.
    """

    def test_the_fold_runs_before_the_storeys_are_split(self):
        source = _script_source()
        folded = source.index("_fold_zones(revit_result, dxf_result")
        split = source.index("floor_plans.split_floors(")
        self.assertLess(folded, split)

    def test_it_runs_before_the_link_is_compared_with_the_dxf(self):
        # The diff is a reading of the same drawing; comparing a folded set
        # with an unfolded one would report every zone as missing geometry.
        source = _script_source()
        self.assertLess(source.index("_fold_zones(revit_result, dxf_result"),
                        source.index("comparison = compare.diff("))

    def test_both_record_sets_are_folded(self):
        # The Revit records are what gets built; the DXF records are what every
        # marker reader consults. Folding one and not the other would leave the
        # two disagreeing about where the building is.
        block = _script_source().split("def _fold_zones(", 1)[1]
        block = block.split("\nclass ", 1)[0]
        self.assertIn("revit_result.records = records", block)
        self.assertIn("dxf_result.records = dxf_records", block)
        self.assertIn("dxf_result.texts = texts", block)
        self.assertIn("dxf_result.regions = hatches", block)

    def test_the_boxes_come_from_the_dxf_read(self):
        # A plan's origin is a bare POINT and the link does not always import
        # one, which is why every marker in this pipeline is read from the DXF.
        block = _script_source().split("def _fold_zones(", 1)[1]
        block = block.split("\nclass ", 1)[0]
        self.assertIn("zone_plan.zones(dxf_result.records", block)
        self.assertIn("marker_records=dxf_result.records", block)

    def test_a_drawing_with_no_zones_is_left_alone(self):
        block = _script_source().split("def _fold_zones(", 1)[1]
        block = block.split("\nclass ", 1)[0]
        self.assertIn("if not found:", block)
        self.assertIn("return", block.split("if not found:", 1)[1][:40])

    def test_what_the_fold_decided_is_said_out_loud(self):
        block = _script_source().split("def _fold_zones(", 1)[1]
        block = block.split("\nclass ", 1)[0]
        self.assertIn("Boundary zones:", block)
        self.assertIn("for note in notes:", block)


class TheSectionsAreARailNotATabStrip(unittest.TestCase):
    """FEAT-18. The owner sent a before-and-after: the six sections move from a
    strip across the top to a rail down the left, collapsible to icons.

    The PAGES did not move. Every TabItem is still here with the header it had,
    so every check about which control lives on which section still reads the
    same file the same way -- only the strip is gone, and the rail drives the
    pages instead.
    """

    def test_the_rail_lists_every_section_the_pages_have(self):
        xaml = _xaml_source()
        rail = xaml.split('x:Name="nav_list"', 1)[1].split("</ListBox>", 1)[0]
        for header, _home in _tab_outline():
            # the outline is parsed XML, the rail is raw source
            escaped = header.replace("&", "&amp;")
            self.assertIn('ToolTip="%s"' % escaped, rail,
                          "%s is a page with no rail item" % header)

    def test_the_rail_drives_the_pages(self):
        xaml = _xaml_source()
        self.assertIn("SelectedIndex=\"{Binding SelectedIndex, "
                      "ElementName=nav_list", xaml)

    def test_the_strip_is_gone_from_the_pages(self):
        # The headless template is what removes it; a TabPanel left in would
        # draw the old strip down the side of the rail.
        block = _xaml_source().split('x:Key="HeadlessTabControl"', 1)[1]
        block = block.split("</Style>", 1)[0]
        self.assertNotIn("TabPanel", block)
        self.assertIn("ContentSource=\"SelectedContent\"", block)

    def test_every_rail_item_has_an_icon_and_a_label(self):
        rail = _xaml_source().split('x:Name="nav_list"', 1)[1]
        rail = rail.split("</ListBox>", 1)[0]
        self.assertEqual(rail.count("<Path Data="), len(_tab_outline()))
        # ...and the label goes away with the rail, the icon stays
        self.assertEqual(rail.count("ElementName=btn_rail"), len(_tab_outline()))

    def test_collapsing_the_rail_is_remembered_like_any_other_setting(self):
        # It is a ToggleButton with a name, so the settings capture reads it --
        # which is why ToggleButton had to become a kind it understands.
        self.assertIn('x:Name="btn_rail"', _xaml_source())
        self.assertIn("ToggleButton", _dialogs_source())

    def test_each_page_says_what_it_is_for(self):
        xaml = _xaml_source()
        self.assertEqual(xaml.count("{StaticResource PageTitle}"),
                         len(_tab_outline()))


class TheZoneTableIsWired(unittest.TestCase):
    """FEAT-17's dialog half: one row per boundary zone, saying what it holds."""

    def test_the_table_is_on_the_multi_storey_page(self):
        self.assertEqual(_tab_homes().get("zone_rows"), "Multi-storey")

    def test_it_selects_and_spreads_like_the_other_tables(self):
        # Eight zones is eight clicks, not eight trips (FEAT-13).
        xaml = _xaml_source()
        block = xaml.split('x:Name="zone_rows"', 1)[1][:400]
        self.assertIn('SelectionMode="Extended"', block)
        source = _window_source()
        self.assertIn('self._build_rows(find("zone_rows")', source)

    def test_the_dropdown_offers_groups_not_raw_categories(self):
        source = _window_source()
        self.assertIn("zone_plan.group_names()", source)

    def test_the_answer_reaches_the_fold(self):
        window = _window_source()
        self.assertIn('"zone_mapping": zone_mapping', window)
        block = _script_source().split("def _fold_zones(", 1)[1]
        block = block.split("\nclass ", 1)[0]
        self.assertIn('selections.get("zone_mapping")', block)

    def test_the_rows_come_from_the_drawing_s_own_layer_names(self):
        # This runs before any mapping exists, so it reads names, not
        # categories -- and it leaves out the box that HOLDS the zones.
        source = _script_source()
        self.assertIn("zone_plan.is_zone_layer(name, storey_layer)", source)
        self.assertIn("zone_plan.default_group(name)", source)

    def test_a_drawing_with_no_zones_says_so_rather_than_showing_nothing(self):
        self.assertIn('find("zone_note").Text', _window_source())


if __name__ == "__main__":
    unittest.main()
