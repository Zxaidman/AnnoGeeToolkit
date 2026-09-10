# -*- coding: utf-8 -*-
"""Static checks on the Filter View Manager dockable pane.

``tests/test_filterview_ui.py`` covers the modeless window. This file covers
the pane, and the two are separate because almost nothing about them is: the
window is CPython, light, floating and its own name scope; the pane is
IronPython, dark, embedded in Revit's chrome and drawn half in XAML and half
in ``provider.py``.

Everything here is checked without Revit and without WPF. That is not a
compromise -- it is the only option. ``provider.py`` imports ``clr`` at module
scope, so it cannot even be imported on the machine that runs this suite, and
the pane cannot be looked at without starting Revit, docking it and dragging
it to an edge. So the failures that shipped were the ones nobody could see:

* **BUG-7** the pane appeared on Revit start with nobody pressing anything --
  ``DockablePaneProviderData.VisibleByDefault`` defaults to **True**;
* **BUG-8** a white panel between the Properties palette and the Project
  Browser, both of which follow Revit's dark theme;
* **BUG-9** docked to the right, the ``WrapPanel`` centred one button in a
  column of dead space and clipped the second off the edge behind a
  *horizontal* scrollbar.

Each of those is a gate below, and each gate was proved by putting the fault
back and watching it fail.

The contrast checks are the ones worth reading twice. A dark palette is easy
to get wrong in a way that looks fine to whoever picked the colours, so the
ratios are computed here from the hex in ``Resources/Colors.xaml`` rather than
asserted as prose -- if someone nudges a token, the arithmetic notices.
"""

import ast
import io
import os
import unittest
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PANE = os.path.join(_ROOT, "AnonGee.extension", "lib", "anongee_filterpane")
_XAML = os.path.join(_PANE, "pane.xaml")
_PROVIDER = os.path.join(_PANE, "provider.py")
_RESOURCES = os.path.join(_ROOT, "AnonGee.extension", "Resources")
_GUIDELINES = os.path.join(_ROOT, "AnonGee_BIM_Tools_Brand_Guidelines.md")

#: The canonical dictionaries the pane's inline theme is lifted from (S12.3).
_CANONICAL = ("Colors.xaml", "Typography.xaml", "Controls.xaml")

_X = "{http://schemas.microsoft.com/winfx/2006/xaml}"


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _canonical_sources():
    return [_read(os.path.join(_RESOURCES, name)) for name in _CANONICAL]


def block(source, key):
    """The verbatim lines defining ``x:Key="key"``, dedented to column 0.

    Lifting the source text rather than the parsed element is deliberate: an
    XML round-trip drops the comments and re-quotes every attribute, so two
    files could compare equal while reading completely differently. This
    compares what a person would actually diff.
    """
    needle = 'x:Key="{0}"'.format(key)
    lines = source.split("\n")
    for start, line in enumerate(lines):
        if needle not in line:
            continue
        stripped = line.lstrip()
        if not stripped.startswith("<"):
            continue
        indent = len(line) - len(stripped)
        tag = stripped[1:].split()[0].split(">")[0]
        if stripped.rstrip().endswith("/>") or "</{0}>".format(tag) in line:
            return _dedent([line], indent)
        close = "</{0}>".format(tag)
        for end in range(start + 1, len(lines)):
            here = lines[end]
            if here.strip() == close and len(here) - len(here.lstrip()) == indent:
                return _dedent(lines[start:end + 1], indent)
        raise KeyError("unterminated: {0}".format(key))
    raise KeyError(key)


def _dedent(lines, indent):
    out = []
    for line in lines:
        out.append(line[indent:] if line[:indent].strip() == "" else line.lstrip())
    return "\n".join(out)


def pane_keys():
    """Every ``x:Key`` the pane defines, in file order."""
    return [e.get(_X + "Key") for e in ET.parse(_XAML).getroot().iter()
            if e.get(_X + "Key")]


def pane_uses():
    """Every ``{StaticResource X}`` / ``{DynamicResource X}`` the pane names."""
    source = _read(_XAML)
    found = set()
    for token in ("{StaticResource ", "{DynamicResource "):
        index = 0
        while True:
            index = source.find(token, index)
            if index < 0:
                break
            start = index + len(token)
            end = start
            while end < len(source) and source[end] not in "}, \n\r\t":
                end += 1
            found.add(source[start:end])
            index = end
    return found


def _tag(element):
    return element.tag.split("}")[-1]


def _template_scopes(root):
    return [e for e in root.iter()
            if _tag(e) in ("ControlTemplate", "DataTemplate")]


def pane_names():
    """``x:Name``s in the pane's OWN scope. Template scopes are invisible to
    ``FindName`` on the control, so a name inside one is not a wiring point."""
    root = ET.parse(_XAML).getroot()
    scopes = _template_scopes(root)
    found = set()
    for element in root.iter():
        name = element.get(_X + "Name")
        if not name:
            continue
        if any(element is not s and element in list(s.iter()) for s in scopes):
            continue
        found.add(name)
    return found


def provider_tree():
    return ast.parse(_read(_PROVIDER))


def looked_up_names():
    """Every string handed to ``FindName`` in provider.py."""
    found = set()
    for node in ast.walk(provider_tree()):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "FindName"
                and node.args
                and isinstance(node.args[0], ast.Constant)):
            found.add(node.args[0].value)
    return found


def function_source(name):
    """The source of one top-level or method ``def``, by name."""
    source = _read(_PROVIDER)
    for node in ast.walk(provider_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise KeyError(name)


def load_function(name):
    """Compile ONE function out of provider.py and hand it back callable.

    ``provider.py`` imports ``clr`` at module scope and cannot be imported
    here. But a pure function inside it can be lifted out and exercised for
    real, which beats asserting on its source text -- these are the rules that
    decide which layout a user gets, and they deserve to be run.
    """
    namespace = dict(module_constants())
    exec(compile(ast.parse(function_source(name)), _PROVIDER, "exec"), namespace)
    return namespace[name]


def module_constants():
    """Every module-level literal assignment in provider.py.

    ``_wants_vertical`` reads ``NARROW_WIDTH``; lifting the function without
    its constants gives a NameError that says nothing about the layout rule
    it was meant to check.
    """
    found = {}
    for node in provider_tree().body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                found[target.id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return found


def module_constant(name):
    return module_constants()[name]


def provider_resource_keys():
    """Resource keys provider.py asks for by name at runtime.

    The chip style and the status brushes are never named in the XAML -- the
    buttons are built in Python -- so without this the "inlines only what it
    uses" gate would call them orphans and delete the pane's own controls.
    """
    found = set()
    for node in ast.walk(provider_tree()):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "TryFindResource"
                and node.args
                and isinstance(node.args[0], ast.Constant)):
            found.add(node.args[0].value)
    found.update(module_constant("_TONE_BRUSH").values())
    return found


# ── colour arithmetic ───────────────────────────────────────────────────

def colors():
    """``{key: "#RRGGBB"}`` for every ``<Color>`` in Resources/Colors.xaml."""
    found = {}
    for element in ET.parse(os.path.join(_RESOURCES, "Colors.xaml")).getroot():
        if _tag(element) == "Color" and element.get(_X + "Key"):
            found[element.get(_X + "Key")] = (element.text or "").strip()
    return found


def _luminance(value):
    """WCAG relative luminance. Accepts #RGB, #RRGGBB and #AARRGGBB."""
    digits = value.lstrip("#")
    if len(digits) == 8:            # WPF puts alpha FIRST
        digits = digits[2:]
    channels = [int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one, other):
    first, second = _luminance(one), _luminance(other)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


class PaneThemeProvenanceTests(unittest.TestCase):
    """S12.3 -- an inline theme is a verbatim copy or it is a defect."""

    def test_every_inlined_resource_is_verbatim_from_a_canonical_dictionary(self):
        """The gate the old rule could only ask for in prose.

        The previous version asserted that each key *existed* in another
        tool's inline copy, which catches an invented key and nothing else --
        a hand-tuned hex or a changed trigger passed. This lifts both blocks
        and compares them.
        """
        pane = _read(_XAML)
        sources = _canonical_sources()
        for key in pane_keys():
            mine = block(pane, key)
            theirs = None
            for source in sources:
                try:
                    theirs = block(source, key)
                    break
                except KeyError:
                    continue
            self.assertIsNotNone(
                theirs,
                "{0} is in pane.xaml but in no canonical dictionary -- add it "
                "to Resources/ first, then re-splice".format(key))
            self.assertEqual(
                mine, theirs,
                "{0} has drifted from Resources/. Change the canonical file "
                "and re-splice; never hand-edit the inline copy.".format(key))

    def test_every_resource_the_pane_uses_is_one_it_defines(self):
        """A missing key is a ``XamlReader.Load`` throw and a pane nobody sees."""
        missing = sorted(pane_uses() - set(pane_keys()))
        self.assertEqual(missing, [], "undefined resource: {0}".format(missing))

    def test_no_resource_key_is_defined_twice(self):
        keys = pane_keys()
        duplicates = sorted(set(k for k in keys if keys.count(k) > 1))
        self.assertEqual(duplicates, [], "defined twice: {0}".format(duplicates))

    def test_the_pane_inlines_only_what_it_uses(self):
        """637 lines of dictionary for three buttons was the old shape.

        A key nobody references is a style that can rot without anything
        noticing, and it is how the file grew to ten times the size of the
        control it themes. Base styles are exempt: they are reached through
        ``BasedOn``, not ``{StaticResource}``.
        """
        based_on = set()
        for key in pane_keys():
            body = block(_read(_XAML), key)
            index = body.find("BasedOn=\"{StaticResource ")
            if index >= 0:
                rest = body[index + len("BasedOn=\"{StaticResource "):]
                based_on.add(rest.split("}")[0].strip())
        # Colors are reached by the brushes; brushes and styles by name; and
        # the chips and status tints by provider.py, which builds them in
        # Python and never mentions them in the markup.
        reachable = pane_uses() | based_on | provider_resource_keys()
        orphans = sorted(set(pane_keys()) - reachable)
        self.assertEqual(orphans, [], "inlined but never used: {0}".format(orphans))

    def test_the_scrollbar_is_a_derivation_and_not_a_variant(self):
        """The one un-keyed style in the pane, and it must stay one line.

        A dark container opts in by deriving from the keyed canonical style.
        Re-templating a ScrollBar here instead would be exactly the hand-
        edited copy S12.3 forbids.
        """
        self.assertIn(
            '<Style TargetType="ScrollBar" BasedOn="{StaticResource ScrollBarOnDark}"/>',
            _read(_XAML))


class DarkSurfaceTests(unittest.TestCase):
    """BUG-8 -- the pane must actually be dark, not merely intend to be."""

    def test_the_pane_paints_a_dark_canvas(self):
        source = _read(_XAML)
        self.assertIn('Background="{StaticResource BrushDarkCanvas}"', source)

    def test_no_light_surface_is_painted_anywhere_in_the_pane(self):
        """The gate that would have caught the white panel.

        Only ``Background`` and ``Fill`` are checked. ``BrushPureWhite`` is a
        legitimate *foreground* on dark -- it is the label on a pressed red
        button -- so banning the brush outright would ban the correct use
        along with the wrong one.
        """
        light = ("BrushPureWhite", "BrushOffWhite", "BrushLightBorder",
                 "BrushOffWhiteHover", "BrushSecondaryBackground",
                 "BrushNeutralBackground", "BrushInputBackground")
        problems = []
        for element in ET.parse(_XAML).getroot().iter():
            for attribute in ("Background", "Fill"):
                value = element.get(attribute) or ""
                for brush in light:
                    if brush in value:
                        problems.append("{0}.{1}={2}".format(
                            _tag(element), attribute, value))
        for key in pane_keys():
            body = block(_read(_XAML), key)
            for line in body.split("\n"):
                if 'Property="Background"' not in line and 'Property="Fill"' not in line:
                    continue
                for brush in light:
                    if brush in line:
                        problems.append("{0}: {1}".format(key, line.strip()))
        self.assertEqual(problems, [],
                         "light surface on a dark pane: {0}".format(problems))

    def test_the_brand_rule_is_still_on_the_pane(self):
        """S12.6 -- the 2px Vivid Red rule is what makes it ours."""
        source = _read(_XAML)
        self.assertIn('Height="2"', source)
        self.assertIn('Fill="{StaticResource BrushVividRed}"', source)


class DarkContrastTests(unittest.TestCase):
    """S10.1 computed, not quoted. Every ratio comes out of Colors.xaml."""

    def setUp(self):
        self.colors = colors()

    def _ratio(self, foreground, background):
        for key in (foreground, background):
            self.assertIn(key, self.colors, "{0} is not in Colors.xaml".format(key))
        return contrast(self.colors[foreground], self.colors[background])

    def test_text_on_dark_clears_aa(self):
        for token in ("ColorDarkTextPrimary", "ColorSilverSteel",
                      "ColorDarkTextMuted"):
            for surface in ("ColorDarkCanvas", "ColorDarkSurface"):
                ratio = self._ratio(token, surface)
                self.assertGreaterEqual(
                    ratio, 4.5,
                    "{0} on {1} is {2:.2f}:1 -- fails AA".format(token, surface, ratio))

    def test_the_interactive_boundary_clears_wcag_1_4_11(self):
        """3:1, and it is the only thing marking a control on near-black.

        The fill step between a button and the canvas is about 1.1:1, so if
        this border goes quiet the control stops being findable.
        """
        for surface in ("ColorDarkCanvas", "ColorDarkSurface"):
            ratio = self._ratio("ColorDarkBorderStrong", surface)
            self.assertGreaterEqual(
                ratio, 3.0,
                "ColorDarkBorderStrong on {0} is {1:.2f}:1".format(surface, ratio))

    def test_the_decorative_border_is_deliberately_quieter(self):
        """If these two ever converge, one of them is redundant and the rule
        in S3.8.2 has quietly stopped meaning anything."""
        decorative = self._ratio("ColorDarkBorder", "ColorDarkCanvas")
        strong = self._ratio("ColorDarkBorderStrong", "ColorDarkCanvas")
        self.assertLess(decorative, strong)

    def test_every_lifted_semantic_clears_aa_on_dark(self):
        for token in ("ColorSuccessGreenOnDark", "ColorCautionAmberOnDark",
                      "ColorErrorRedOnDark", "ColorInfoBlueOnDark"):
            ratio = self._ratio(token, "ColorDarkCanvas")
            self.assertGreaterEqual(
                ratio, 4.5, "{0} is {1:.2f}:1 on dark".format(token, ratio))

    def test_every_lifted_semantic_is_clearer_on_dark_than_its_light_twin(self):
        """The invariant that actually holds for all four.

        Not every light semantic *fails* on dark -- Success Green is 5.2:1 and
        passes AA while still reading as a muddy smear on near-black. What is
        true of all four is that the lifted one is measurably clearer, and a
        "lifted" token that is not would be a colour someone liked rather
        than a fix.
        """
        for light, dark in (("ColorSuccessGreen", "ColorSuccessGreenOnDark"),
                            ("ColorCautionAmber", "ColorCautionAmberOnDark"),
                            ("ColorErrorRed", "ColorErrorRedOnDark"),
                            ("ColorInfoBlue", "ColorInfoBlueOnDark")):
            self.assertGreater(
                self._ratio(dark, "ColorDarkCanvas"),
                self._ratio(light, "ColorDarkCanvas"),
                "{0} is no clearer on dark than {1}".format(dark, light))

    def test_the_light_semantics_are_large_text_only_on_dark(self):
        """The specific claim S3.8.4 makes, and the reason the set exists.

        Error Red and Info Blue land at 3.56:1 and 3.32:1 on Dark Canvas --
        above 3:1, so legal for large text, and below 4.5:1, so illegal for
        the body text and status lines they would actually be used for.
        """
        for token in ("ColorErrorRed", "ColorInfoBlue"):
            ratio = self._ratio(token, "ColorDarkCanvas")
            self.assertLess(ratio, 4.5,
                            "{0} is {1:.2f}:1 on dark".format(token, ratio))

    def test_vivid_red_is_never_a_foreground_on_the_dark_pane(self):
        """S3.7 / S3.8.5. Red on dark is 3.6:1 -- large text only.

        The ban is checked where it can be broken: a ``Foreground`` setter in
        one of the pane's own dark styles.
        """
        self.assertLess(self._ratio("ColorVividRed", "ColorDarkCanvas"), 4.5)
        offenders = []
        for key in pane_keys():
            for line in block(_read(_XAML), key).split("\n"):
                if 'Property="Foreground"' in line and "BrushVividRed" in line:
                    offenders.append("{0}: {1}".format(key, line.strip()))
        self.assertEqual(offenders, [],
                         "Vivid Red as text on dark: {0}".format(offenders))

    def test_white_on_vivid_red_still_passes_so_primary_needs_no_dark_twin(self):
        """The reason S9.10 has no ``ButtonPrimaryOnDark``."""
        self.assertGreaterEqual(
            contrast(self.colors["ColorPureWhite"], self.colors["ColorVividRed"]),
            4.5)


class PaneWiringTests(unittest.TestCase):

    def test_every_looked_up_control_exists_in_the_xaml(self):
        missing = sorted(looked_up_names() - pane_names())
        self.assertEqual(missing, [], "FindName with no control: {0}".format(missing))

    def test_every_named_control_the_xaml_defines_is_looked_up(self):
        unused = sorted(pane_names() - looked_up_names())
        self.assertEqual(unused, [], "never looked up: {0}".format(unused))

    def test_the_pane_is_hidden_until_the_button_shows_it(self):
        """BUG-7. ``VisibleByDefault`` starts **True**: registering a pane and
        showing it are separate in the API but not in its defaults.

        This walks the tree rather than searching the text, and that is the
        difference between a gate and a decoration -- the first version of it
        matched the sentence in the method's own docstring and stayed green
        with the assignment deleted.
        """
        assigned = []
        for node in ast.walk(ast.parse(function_source("SetupDockablePane"))):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (isinstance(target, ast.Attribute)
                        and target.attr == "VisibleByDefault"):
                    assigned.append(getattr(node.value, "value", "?"))
        self.assertEqual(assigned, [False],
                         "SetupDockablePane must assign VisibleByDefault = False "
                         "exactly once; found {0!r}".format(assigned))

    def test_the_chip_style_the_provider_asks_for_is_one_the_xaml_defines(self):
        """``TryFindResource`` returns None on a typo and the chips render as
        Windows default buttons -- grey, square, and nobody's."""
        source = _read(_PROVIDER)
        self.assertIn('TryFindResource("ButtonRuleOnDark")', source)
        self.assertIn("ButtonRuleOnDark", pane_keys())

    def test_every_status_tone_names_a_brush_the_pane_defines(self):
        for tone, key in sorted(module_constant("_TONE_BRUSH").items()):
            self.assertIn(key, pane_keys(),
                          "tone {0!r} names {1}, which the pane does not "
                          "define".format(tone, key))

    def test_the_error_tone_is_the_lifted_red_and_not_the_light_one(self):
        """S3.8.4 -- ``BrushErrorRed`` on this canvas is 2.3:1."""
        self.assertEqual(module_constant("_TONE_BRUSH")["error"],
                         "BrushErrorRedOnDark")


class OrientationTests(unittest.TestCase):
    """BUG-9 -- the pane lays out for the shape it is actually in."""

    def setUp(self):
        self.wants_vertical = load_function("_wants_vertical")

    def test_a_top_docked_strip_runs_across(self):
        self.assertFalse(self.wants_vertical(1600.0, 90.0))

    def test_a_side_docked_column_runs_down(self):
        self.assertTrue(self.wants_vertical(300.0, 900.0))

    def test_a_short_side_dock_still_runs_down(self):
        """Narrow beats short: a 300px-wide pane has no room to run across
        however little height it has."""
        self.assertTrue(self.wants_vertical(300.0, 120.0))

    def test_a_tall_floating_pane_runs_down(self):
        self.assertTrue(self.wants_vertical(500.0, 700.0))

    def test_a_wide_floating_pane_runs_across(self):
        self.assertFalse(self.wants_vertical(800.0, 400.0))

    def test_an_unmeasured_control_keeps_the_layout_the_xaml_declares(self):
        """Before the first pass both are zero. Answering "vertical" there
        would flip the layout once on load, for one frame, for nothing."""
        self.assertFalse(self.wants_vertical(0.0, 0.0))
        self.assertFalse(self.wants_vertical(-1.0, -1.0))

    def test_the_threshold_leaves_room_above_a_side_dock(self):
        """S12.4 caps a side dock at 360. The switch has to happen before the
        buttons start clipping, not after."""
        self.assertGreater(module_constant("NARROW_WIDTH"), 360.0)

    def test_the_layout_moves_everything_the_orientation_touches(self):
        """Orientation alone is not enough -- the failure that shipped was a
        vertical list with a horizontal scrollbar under it and the actions
        still docked to the right, eating the width."""
        layout = function_source("_layout")
        for fragment in ("Orientation.Vertical", "DockPanel.SetDock",
                         "VerticalScrollBarVisibility",
                         "HorizontalScrollBarVisibility",
                         "ScrollBarVisibility.Disabled",
                         "HorizontalAlignment.Stretch",
                         "self._dress_chips()"):
            self.assertIn(fragment, layout, fragment)

    def test_the_chip_container_stretches_so_the_chips_can(self):
        """A StackPanel left-aligned in its parent sizes to its widest child,
        so ``Stretch`` on a chip inside it stretches the chip to nothing. The
        container has to give up its own alignment first."""
        layout = function_source("_layout")
        index = layout.find("self.buttons.HorizontalAlignment")
        self.assertGreater(index, -1, "the chip container's alignment never moves")
        self.assertIn("HorizontalAlignment.Stretch", layout[index:index + 220])

    def test_exactly_one_axis_scrolls(self):
        """Both on Auto is the state that drew a horizontal scrollbar under a
        column that had nothing to scroll sideways."""
        layout = function_source("_layout")
        self.assertEqual(layout.count("ScrollBarVisibility.Auto"), 2)
        self.assertEqual(layout.count("ScrollBarVisibility.Disabled"), 2)

    def test_the_relayout_is_gated_on_the_orientation_actually_changing(self):
        """``SizeChanged`` fires on every drag pixel. Without the gate a drag
        re-margins every chip a few hundred times."""
        layout = function_source("_layout")
        self.assertIn("if vertical == self.vertical:", layout)
        self.assertIn("return", layout)

    def test_size_changed_is_subscribed(self):
        self.assertIn("SizeChanged += self._on_size", _read(_PROVIDER))

    def test_nothing_in_the_pane_centres_itself_vertically(self):
        """A pane is given whatever height the user dragged it to, so content
        that centres floats in the middle of an empty panel -- image 1."""
        root = ET.parse(_XAML).getroot()
        scopes = _template_scopes(root)
        offenders = []
        for element in root.iter():
            if (element.get("VerticalAlignment") or "") != "Center":
                continue
            # Inside a ControlTemplate, Center means "centred in this 28px
            # button" -- which is right. Only the pane's own tree is at issue.
            if any(element is not s and element in list(s.iter()) for s in scopes):
                continue
            offenders.append(_tag(element))
        self.assertEqual(offenders, [],
                         "centred in a dockable pane: {0}".format(offenders))


class GuidelinesTests(unittest.TestCase):
    """The dark theme had to be *documented*, not just built."""

    def setUp(self):
        self.doc = _read(_GUIDELINES)

    def test_the_dark_palette_has_a_section(self):
        self.assertIn("### 3.8 Dark Surfaces", self.doc)
        self.assertIn("### 9.10 Dark-Surface Controls", self.doc)

    def test_the_document_says_which_surfaces_are_dark(self):
        self.assertIn("dockable pane", self.doc)
        for phrase in ("embedded in Revit's own chrome",
                       "1.4.11"):
            self.assertIn(phrase, self.doc)

    def test_every_dark_token_in_the_code_is_documented(self):
        """Tokens are authoritative and this prose describes them -- so an
        undocumented token means the document is now wrong."""
        undocumented = []
        for key, value in sorted(colors().items()):
            if "Dark" not in key and "OnDark" not in key:
                continue
            hexes = value.lstrip("#")
            plain = "#" + (hexes[2:] if len(hexes) == 8 else hexes)
            if key not in self.doc or plain.upper() not in self.doc.upper():
                undocumented.append("{0} {1}".format(key, plain))
        self.assertEqual(undocumented, [],
                         "in Colors.xaml, not in the guidelines: {0}".format(
                             undocumented))

    def test_the_visible_by_default_trap_is_written_down(self):
        """It cost a release. The next person gets it for free."""
        self.assertIn("VisibleByDefault", self.doc)

    def test_the_orientation_rule_is_written_down(self):
        for phrase in ("scrolls vertically", "scrolls horizontally",
                       "WrapPanel"):
            self.assertIn(phrase, self.doc)


if __name__ == "__main__":
    unittest.main()
