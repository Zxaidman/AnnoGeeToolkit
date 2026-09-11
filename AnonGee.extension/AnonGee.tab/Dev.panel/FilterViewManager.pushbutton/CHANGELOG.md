# Filter View Manager — changelog

Semantic versioning, read from the point of view of someone using the tool:

| Part | Meaning |
| --- | --- |
| **MAJOR** | The tool behaves differently on purpose — a workflow moved, or what pressing a rule does to the model changed shape. |
| **MINOR** | A new capability. Everything already saved still works. |
| **PATCH** | A fix. Nothing new to learn. |

The version is declared once, in `script.py`'s `VERSION`. `bundle.yaml`'s
`Version:` line and the newest heading here are held to it — once the tool has
a window with a header to check, by a test, the way `tests/test_autolevel_ui.py`
holds Auto Level Manager's four copies together.

---

## 0.4.0 - 2026-09-11

The second in-Revit run of the panel. Everything 0.3.0 set out to fix was
fixed -- it stays hidden at startup, it remembers where it was docked, it lays
out for both shapes. Two things it got wrong were things only the model in
front of a user can show.

### The dark was the wrong dark

0.3.0 reasoned the palette down from the brand's Charcoal Black and landed on
`#1B1B1E`. Beside the Properties palette and the Project Browser, both sitting
at Revit's own panel grey, that reads as a **hole punched between them** rather
than as a darker panel. Matching the host is the entire point of an embedded
surface, and near-black does not match it.

The canvas is now **Revit 2025's dark palette background**. That is not a
repaint -- a lighter canvas is a *smaller* step from mid-tone colours, so every
token measured against it had to move:

| | 0.3.0 (near-black) | 0.4.0 (Revit grey) |
| --- | --- | --- |
| Canvas | `#1B1B1E` | `#383838` |
| Interactive border | `#6F707C` | `#9EA1AB` |
| Muted text | `#9AA2B3` | `#B4BBC8` |
| Error on dark | `#F87171` | `#FF9A93` |

**And it forced a lifted brand red.** On Revit grey `ColorVividRed` is
**2.46:1** -- under WCAG 1.4.11's 3:1. That is not a preference about
brightness: the Clear button's 1.5px red outline is an interactive boundary,
and at 2.46:1 the control has no boundary a low-vision user can find. So
`ColorVividRedOnDark` (`#FF5F4C`, 3.90:1) now carries every **accent and
border** use on dark -- the 2px pane rule, a chip's left bar, an outlined
button, a dragged scrollbar thumb.

**Fills keep Vivid Red proper.** A Primary button is white-on-red at 4.78:1
whatever sits behind it, so the fill never needed lifting and lifting it would
have weakened the label. Two uses, two rules, and §3.8.5 now says which is
which.

Design system **v3.3 -> v3.4**.

### Raised, not recessed

A recessed ramp was tried first -- Revit's own inputs are darker than its
panels -- and abandoned. With the canvas in the middle of the range, hover
*crossed* it and landed at 1.04:1 against the thing it was supposed to stand
out from. Faces now step up monotonically, so hover always reads as lighter
than rest and pressed as lighter than hover.

### The wheel did nothing across the top

Docked as a strip there is no vertical axis, and WPF's wheel only ever drives
the vertical one. So the wheel was inert and rules past the fold could only be
reached by dragging an 8px scrollbar. The wheel now goes to whichever axis is
live. Shift+wheel is left alone in both orientations -- that is the platform's
own "scroll sideways" and overriding it would be rude.

### Changing the panel's appearance no longer needs a Revit restart

Revit is handed the `FrameworkElement` once, at registration, and will not take
another -- so a pyRevit reload leaves the **old** control on screen and the new
theme only appeared after a full restart. A poor trade for a panel being
iterated on, and avoidable: Revit holds the `UserControl`, not its contents, so
Refresh now re-reads `pane.xaml` and swaps the contents underneath it.

The order matters and the gate says so: names are resolved from the fresh tree
**before** its content is detached, because re-parenting does not carry the
name scope with it and `FindName` returns `None` afterwards. Any failure leaves
the tree that is already on screen alone -- a pane showing last build's theme
is a blemish, a pane showing nothing is a lost tool.

### The saved rules take a multiple selection

Asked for directly, and modelled on cad2bim's layer mapping so the same gesture
means the same thing in both tools:

- **Ctrl+click** adds to the selection, **Shift+click** takes a run --
  `SelectionMode="Extended"` and WPF does both natively.
- A **tick** on the left of each row shows what is selected. It is a *report*,
  not a second switch: bound one-way to the row's own `IsSelected` and not
  hit-testable, so clicking it selects the row exactly as clicking the name
  does (§12.7.Q -- a Python bool does not coerce for `IsChecked`, so the
  binding has to reach the native container). Two independent notions of
  "chosen" in one list is the bug this avoids.
- **Duplicate, Delete and every Move** act on the whole selection. Delete names
  up to six and counts the rest.
- The editor holds one rule, so it loads only when **exactly one** is selected.
  Picking several never discards what was being edited.

### Two more places to put a rule

**To top** and **To bottom** join Move up and Move down. One place at a time is
fine for two rules and useless for thirty.

All four go through `RuleSet.reorder`, which moves a **block** -- and a block
move is not a loop over single moves. Looping reverses a multiple selection
going up and collapses it going down, depending which end you start from.
Stepping swaps each chosen rule with its *unchosen* neighbour, walking top-down
to go up and bottom-up to go down, so a chosen rule pressed against another
chosen one is never dragged through it and a block at the edge stays put
instead of turning itself inside out.

A move rewrites the list, which drops the selection, so the block is re-ticked
afterwards. Without that the second press of Move up does nothing, which reads
as the button being broken.

### The size ceiling did its job

`tests/test_filterrules.py` refuses to let a Revit-coupled module carry more
logic than the largest **tested** one, and `provider.py` crossed it at 249
statements. The honest answer to crossing that line is to move the thinking
out, not to raise the bar: `anongee_filterpane/layout.py` now holds every
decision the panel makes about its own shape -- which orientation, how far a
wheel notch goes, which brush a status tone takes -- with none of the .NET
plumbing that carries them out.

They are **run** by the suite now rather than read. The previous release lifted
`_wants_vertical` out of `provider.py` by compiling its AST, because the module
cannot be imported without Revit; a module that can be imported does not need
the trick.

### Also

- 27 new tests (1329 -> 1356). Fourteen faults were put back one at a time; **three
  gates did not catch theirs.** One compared the wrong two lines, one matched
  `SelectedItems.Add(row)` in the *category* list so it was green whatever the
  rule list did, and one was pointed at a case that never exercised the guard
  it was testing. All three were rewritten until they failed.
- `_build` no longer parses `pane.xaml` twice: `reload` is re-skin plus redraw,
  and the first build already has the tree in its hand.
- `ModifierKeys.None` cannot be written down -- `None` is a Python keyword, so
  the attribute access is a `SyntaxError` on both engines. `getattr` is the
  only way to name the member, and there is a gate on it.

---

## 0.3.0 - 2026-09-10

The first in-Revit run of the panel. It registered, it read the rules and the
buttons worked -- and it was wrong in four ways at once, all of them visible in
one screenshot and none of them findable without docking it.

### It appeared at Revit start with nobody pressing anything

0.2.0's note said the pane "stays hidden until something calls `Show()`". That
is true of `DockablePane.Show()` and false of the pane, because
`DockablePaneProviderData.VisibleByDefault` **defaults to `True`** and nothing
in the API docs puts that next to the sentence about registration being
invisible. Registration and visibility are separate concepts with a shared
default.

One line fixes it -- `data.VisibleByDefault = False` in `SetupDockablePane` --
and the requirement it restores is the one from the very first conversation
about this tool: *"does not need to be start with revit, only when user click
the pushbutton"*.

The gate for it walks the AST rather than searching the text. Its first version
searched the text, matched the sentence in the method's own **docstring**, and
stayed green with the assignment deleted. A gate that cannot fail is a comment.

### It was white, between two dark palettes

The pane sits in the same column as the Properties palette and the Project
Browser. Both follow Revit's theme. A white slab between them does not read as
an AnonGee panel; it reads as a control that failed to paint.

**The design system had no dark anything.** `Colors.xaml` was light-only; the
only on-dark tokens in the whole repository were three text styles for putting
text on the Charcoal header band. So the fix was not a tool change:

- **`Resources/Colors.xaml`** gains a dark surface palette -- a four-step
  surface ramp from Charcoal, two borders, three text weights and four semantic
  colours lifted for dark.
- **`Resources/Controls.xaml`** gains `ButtonSecondaryOnDark`,
  `ButtonGhostOnDark`, `ButtonRuleOnDark`, `ScrollBarOnDark` and
  `CardBorderOnDark`.
- **`Resources/Typography.xaml`** gains `TextSmallOnDark` and
  `TextCaptionOnDark`.
- **The brand guidelines** gain **§3.8 Dark Surfaces** and **§9.10 Dark-Surface
  Controls**, and §10.1 gains eight computed contrast rows.

**§3.8's rule is about context, not taste:** a surface is dark when it is
*embedded in Revit's chrome* -- a dockable pane -- and light when it is the
user's foreground task. There is no dark-mode toggle and none is planned. Each
surface is one or the other by what it is.

**Two borders, and the difference is load-bearing.** On a near-black canvas the
fill step between a button and its background is about 1.1:1, which is
invisible: the border is the only thing telling the user where the control is.
So `ColorDarkBorderStrong` (`#6F707C`, 3.51:1 on canvas) is the boundary of
anything interactive and clears WCAG 2.1 **1.4.11**, while `ColorDarkBorder`
(`#34343C`) is decorative only. Outlining a button with the decorative one looks
tidier and is the accessibility defect.

**Vivid Red is 3.60:1 on dark** -- large text only -- so §3.7's existing ban on
red text over Charcoal extends unchanged: on dark, red is an accent and a fill
(the 2px rule, a chip's left bar, a dragged scrollbar thumb), never a label.
`ButtonSecondaryOnDark` keeps the red border and takes a light label.

Every ratio in §3.8 and §10.1 is **computed from `Colors.xaml`** by
`tests/test_filterpane_ui.py`, not transcribed. That gate earned itself
immediately: this entry originally claimed light Error Red was 2.30:1 on dark.
It is **3.56:1**. The arithmetic said so before the document shipped.

### Docked to the right, it laid out for neither shape

`WrapPanel` was 0.2.0's answer to "one control does both shapes". It reflows,
but it does not re-align, re-margin, or move anything else on the panel. Docked
right the result was: one button centred in a column of dead space, the second
clipped off the edge behind a **horizontal** scrollbar, the Clear/Refresh pair
still docked to the right eating the narrow width, and the status line
truncated mid-sentence.

0.3.0 decides the orientation from the pane's measured size and applies it to
four things at once:

| | Docked top / bottom | Docked left / right |
| --- | --- | --- |
| Rules | run across | stack down |
| Scrolls | horizontally | vertically |
| Actions | docked right | docked top |
| Chip | centred label, capped at 220px | full width, left label, ellipsized |

There is still **one element tree** -- only its properties move -- so the two
shapes cannot drift apart the way two layouts would. Exactly one axis scrolls:
leaving the other on `Auto` is what drew a horizontal scrollbar under a column
with nothing to scroll sideways. The relayout is gated on the orientation
actually flipping, because `SizeChanged` fires on every pixel of a drag.

`_wants_vertical` is a plain function of two numbers, so the suite lifts it out
of a module that cannot be imported without Revit and **runs it** -- six docked
shapes, checked for real rather than asserted about in prose.

### Everything in it centred itself

A dockable pane is given whatever height the user dragged it to. Content that
centres itself therefore floats in the middle of an empty panel, which is
exactly what the screenshot showed. Everything is `Top`/`Left` aligned now, and
a gate fails on any `VerticalAlignment="Center"` outside a control template
(inside one it means "centred in this 28px button", which is right).

### The inline theme is now provably verbatim, and a quarter the size

§12.3 says an inline theme must be a verbatim copy of `Resources/*.xaml`. The
old gate asserted each key *existed* in another tool's inline copy -- which
catches an invented key and nothing else. A hand-tuned hex passed. A changed
trigger passed.

The new gate lifts the source lines of every key from both files and compares
them, so drift fails with the two blocks side by side. `pane.xaml` was
regenerated by that same extraction rather than typed.

It also has to be **reachable**: a key nothing references is a style that can
rot unnoticed, and it is how the file reached 637 lines to theme three buttons
and a line of text. `pane.xaml` is **382 lines** and inlines a TextBox,
ComboBox, CheckBox, ToggleSwitch, ListBox and card style exactly never. The gate
found five orphans in the first draft of this release, including two I had just
added.

### Also

- The status line takes a colour that agrees with its words -- muted, green or
  the **lifted** red. Colour is never the only signal (§10.4); the sentence
  says it too.
- It wraps in a side dock and ellipsizes in a top strip, instead of being cut
  off mid-sentence in both.
- A rule chip's label is a `TextBlock` with `TextTrimming`, not a bare
  `ContentPresenter`, so a long rule name ellipsizes in a narrow dock rather
  than overflowing.
- `DockablePaneProviderData` had been imported and never used since the spike.
  Removed.
- **§12.4 is orientation-aware.** It described only the tall shape
  (`MinWidth=240 / MaxWidth=360`) and now states both, what each one scrolls,
  the `WrapPanel` trap, the top-align rule and the `VisibleByDefault` default.
  `ARCHITECTURE.md` §7.3's reconciliation item is closed.
- Design system **v3.0 → v3.3**.
- 39 new tests (1279 → 1318). Ten faults were put back one at a time to confirm
  each gate catches the thing it is named after; one did not, and was rewritten
  until it did.

---

## 0.2.1 - 2026-09-10

Two faults the first in-Revit run of 0.2.0 found, and the spike doing exactly
what a spike is for.

### The panel: the spike asked for the wrong name, and said so

The footer read *"The panel could not be registered at Revit start: no
UIControlledApplicatio..."* -- which is a **successful spike**. It is the answer
that could not be got any other way, it cost nothing, and nothing else broke
while it was wrong.

The guess was `__uicontrolledapplication__`. **pyRevit binds `__revit__`** --
and `tests/test_scripts.py` has listed it among the injected names the whole
time, in this repository, where it could have been read.

Fixed by not guessing. The startup script now tries `__revit__`,
`__uicontrolledapplication__`, `__uiapp__` and `pyrevit.HOST_APP.uiapp` in
turn, and **records which one answered and what type it was**. The candidate is
chosen by asking for `RegisterDockablePane` rather than by type, because
`UIApplication` and `UIControlledApplication` both have it and which one a
startup script is handed was precisely the unknown.

When none of them answers, the record now names **every place it looked and
what was there instead**, rather than saying there was none. A list that
records which name answered cannot make this mistake twice.

### Remove condition: built, wired, working, invisible

Reported as *"i can add conditions but can't see the remove conditions or it is
never built"* -- and it **was** built. It sat directly **under** a fixed-height
list inside a `ScrollViewer`, which put it below the visible fold. It could
only be reached by scrolling past the list, and nothing suggested it was there.

**A control the user cannot find is a control that does not exist.**

The button now sits **beside** the list, in the same row, so it is on screen
exactly when its target is and no amount of scrolling can separate them. The
list is a little shorter to pay for it, and **double-clicking a condition
removes it too** -- the affordance a modeller reaches for first, at the cost of
one wiring line.

A test pins it: an action button must be a **sibling** of the list it acts on.
Proved to bite by putting it back underneath.

### On rules surviving a restart

They are written to
`%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json` the moment Save
rule is pressed -- not held in memory and flushed on close. So closing Revit,
or losing it, cannot cost a saved rule. Confirming that across a real restart is
still worth doing; nothing in this repository counts as verified until it has
run in Revit.

## 0.2.0 - 2026-09-10

The dockable panel, and the spike that had to come first.

### CRIT-3, answered as far as it can be answered here

**Registration and visibility are different things**, and the whole design
turned on it. `RegisterDockablePane` must be called during `OnStartup`, before
any document is open -- a pushbutton runs far too late and Revit refuses it.
But a registered pane stays **hidden** until something calls `Show()`. So the
requirement holds exactly as it was asked: nothing appears until the button is
pressed, and registration costs no UI, needs no document, and is invisible.

### `startup.py` now registers the pane, and cannot take pyRevit down doing it

That file's own docstring is the standard: *"a startup script that throws takes
pyRevit's load with it, and a broken bridge must never cost the user their
other tools."* A broken **panel** must not either -- more so, since it is a
convenience on top of one tool, not the tool. The call is wrapped twice, every
entry point in `anongee_filterpane` returns a result rather than raising, and
what happened is written to its own record.

**The record is the point of a spike.** When registration is the thing that
failed there is no pane to look at and no route to ask, and three causes look
identical from a ribbon with no panel on it: pyRevit gave no
`UIControlledApplication`, Revit refused the registration, or the control would
not build. The record names which. Pressing **Panel** in the window reads it
back and reports it -- the window is CPython and the registration is
IronPython, so that file is the only channel between them.

### The architecture paid off

`anongee_filterpane` imports `anongee_filterrules` and gets the entire rule
engine -- the store, the queries, the isolate -- **without one line of it being
duplicated**. That is the reason the engine went in `lib/` rather than beside
the script, written to run on both engines, back in 0.0.3. The panel is 200
lines because everything it needed was already there and already tested.

- `__init__.py` is **Revit-free on purpose**, so the CPython window can import
  it to read the record. `provider.py` is the half that touches Revit and is
  only ever loaded by `startup.py`.
- Pressing a rule button goes through an `ExternalEvent`, and that is not
  ceremony: a dockable pane is **not a command**, nothing hands it an
  `ExternalCommandData`, and `ExternalEvent.Execute` being given the
  `UIApplication` is the only way the pane can reach the active document.
- The layout is a `WrapPanel`, so it reads the same docked under the ribbon
  (buttons across) as dragged to an edge (buttons down) -- one layout, not two
  kept in step.
- Registering **twice** is guarded. pyRevit reloads extensions without
  restarting Revit, so this is reachable a second time in one session and Revit
  raises on a GUID it already knows. The first pane still works, so it is
  recorded as registered with a note rather than reported as a failure.
- The pane's GUID is a **constant, forever**. Revit remembers where the user
  docked a pane by it; changing it orphans that and registers a second, empty
  pane beside the first.

### Tests

The dual-engine gate now covers **both** packages -- no Python-3-only syntax,
`from __future__ import division`, pure ASCII, no `re`, no `anongee_toolkit`,
and the pure half of each importing no Revit. Proved to bite on the new package
by putting an f-string in `provider.py` and `import clr` in `__init__.py`.

Six tests on the record itself, in their own prefs directory, because `register`
writes it and a test that reads it must not be answering a file another test
just left behind.

### Still unproven, and only Revit can say

Whether pyRevit hands a startup script a `UIControlledApplication` at all, and
whether Revit accepts the registration in this version. That is what the record
is for. **If it failed, 0.1.2 is untouched** -- the window does not depend on
the panel, and Panel reports rather than breaks.

## 0.1.2 - 2026-09-10

**The Conditions row offered no parameters at all.** Reported from a model with
**151 structural column types loaded and no columns placed**: the footer read
*"2 famil(ies), 151 type(s), 0 parameter(s)"* and the parameter combo was empty,
with nothing said about why.

**Cause: it looked in one place, and that place was empty.** `parameters()`
sampled **placed elements** only. No columns placed, no elements to sample, no
parameters -- even though 151 types were sitting right there carrying every type
parameter the rule could have used.

**It reads three sources now**, in an order that matters because the first entry
wins a name collision:

1. **What Revit says is filterable for the category.** Needs no elements at all,
   so it answers in an empty model, and it is the only source whose `filterable`
   flag has actually been *asked* of Revit rather than assumed. A project or
   shared parameter is an element and the document knows its name; a built-in
   one is not, so `LabelUtils` turns the `BuiltInParameter` behind the id into
   the words this Revit shows -- localised, which is right, because the rest of
   the window is showing the user their own Revit's labels.
2. **A sample of placed elements**, own parameters and their type's -- still the
   only source for an instance parameter a project bound that Revit does not
   consider filterable.
3. **A sample of the types.** Types exist long before anything is placed, and
   this is the source that was missing.

### Two more faults the same screenshot showed

- **The hint said "Pick a category to begin" with a category already picked.**
  Nothing re-validated after the cascade came back from Revit's thread, so the
  line was answering a question from before the click. It re-validates now.
- **An empty parameter list said nothing.** Three causes look identical from
  the window -- nothing placed, no types answering, Revit offering nothing --
  and it now names all three rather than showing a blank combo. Root
  `todo-list.md` BUG-5 is the standing lesson: *the tool built to explain a
  failure explained nothing.*

### And one duplication removed

`families()`, `types()` and `parameters()` each wrote the same dedupe loop by
hand. It is `names.dedupe()` now -- one function, seven tests, and the thing
that makes merging three parameter sources safe rather than fiddly.

## 0.1.1 - 2026-09-09

**The button was not on the ribbon.** Everything in 0.1.0 was built, tested and
merged, and Revit showed nothing -- no error, no warning, just an absent tool.

**Cause: it was alone in a stack.** `RibbonPanel.AddStackedItems()` has
overloads for **two** items and for **three**, and none for one. pyRevit cannot
build a one-item stack, so it skips it and everything inside goes with it.
`Dev.panel` already had three full stacks, so 0.1.0 opened a `col3.stack` for
this one button -- and that is precisely what made it invisible.

The evidence was in the repository the whole time: every stack that works holds
three, except `BIM.stack` which holds two. None holds one.

**Fixed by putting the button directly on the panel**, which is what
`AutoLevel` does on Essential and `cad2bim` does on Core. `col3.stack` is gone
and `Dev.panel`'s layout names `Testing`, `col1`, `col2`, `FilterViewManager`.

**And by a test, because nothing else could have caught it.**
`tests/test_repo_docs.py` now refuses any `.stack` that does not hold two or
three child bundles. Proved to bite by putting the button back in a stack of
one.

**`METHODOLOGY.md` said the wrong rule.** It read *"a stack takes at most three
buttons"*, which is true and useless -- the limit that mattered was the floor,
not the ceiling. It now says two or three, never one, and says what happens when
you get it wrong.

### Also

- **The README's tool count is checked now.** It said 30 over 31 rows: this
  branch moved 29 → 30 and `claude/cad2bim` added CAD2BIM Audit without touching
  the number, so neither side was wrong alone. A gate holds the stated count to
  the row count.

## 0.1.0 - 2026-09-09

The window. The first build a person would call the tool: build a rule, name
it, save it, press it, and only what it matches is left in the view.

**Pressing a rule temporarily isolates its matches in the active view, and
writes nothing to the project.** No `ParameterFilterElement`, nothing in
Manage > Filters, no trace for a colleague opening the model. It lasts the
session, does not print, and Clear puts the view back -- the same thing Revit's
own Reset Temporary Hide/Isolate does.

### The window

- **Saved rules on the left**, with New, Duplicate, Delete, Move up and Move
  down. Selecting one loads it into the editor. Delete asks first, and only
  that rule goes.
- **The cascade on the right.** Categories are a searchable ticked list -- the
  ticks survive a search, because the search filters what is *shown*, not what
  is *chosen*. Family and Type are optional; leaving them on "any" is how "all
  the walls" is said.
- **Conditions are added one at a time** and listed, rather than edited inside
  a grid. That is a deliberate scope choice: in-grid combo columns are where
  §12.7's worst traps live (checkbox coercion, edit-commit cancellation,
  per-row ItemsSource), and none of them can happen to a list.
- **The footer carries all the transient state** -- the badge, the status line
  and the live count -- because §12.6 says the header holds the title only.
- **Count, Select, Apply, Clear.** Count changes nothing; Select pushes the
  matches into Revit's selection; Apply isolates; Clear restores.
- **Every control has a tooltip**, and a test refuses one that does not.

### Modeless, done the way this repository already proved

- The handler carries `__namespace__`, has **no `__init__`**, and is defined
  **once per Revit session** behind a `sys.modules` cache. All three fail at
  instantiation or on the *second* press, and a test checks each.
- The same module holds the live window, so pressing the ribbon button again
  **activates the open window** instead of stacking a second one.
- Requests cross to Revit's thread as plain data -- a rule travels as the dict
  it saves as, and comes back as ints and strings. A Revit object cannot cross
  to the WPF thread, and a test refuses a `serve()` that returns anything but a
  dict.
- Results come back through the window's `Dispatcher`, which is the only place
  a control is written.

### Two traps avoided on purpose

- **The category tick is the native `ListBoxItem.IsSelected`, never a Python
  bool.** §12.7.Q: a Python bool does not coerce in this engine -- the tick
  looks permanently disabled and TwoWay write-back is unreliable. Python
  mirrors `SelectedItems`, not the other way round.
- **Lists are rebuilt behind a flag, not by detaching the handler.**
  `event -= self._handler` may remove nothing at all: `self._handler` builds a
  new bound method on every attribute access, so pythonnet can wrap a different
  delegate. A flag cannot be got wrong, and a test refuses `SelectionChanged -=`.

### The theme is the sanctioned copy, spliced rather than written

`ui.xaml` carries the inline theme **verbatim** from
`Dev.panel/Testing.stack/Modeless.pushbutton/ui.xaml` (§12.3 strategy 2), copied
by script so it cannot drift. **This tool adds no styles of its own** -- the
implicit `ListBoxItem` and `ScrollBar` styles already theme the three lists, and
everything else is a key that block defines. A test refuses any resource key
that is not in the sanctioned theme.

### Tests

`tests/test_filterview_ui.py`, 28 static checks, modelled on
`test_autolevel_ui.py`. Every `{StaticResource}` resolves, no `x:Key` twice, no
`{StaticResource}` on the root `Window`, no literal mistaken for markup, every
`Style` matches its element, every trigger targets its own template, every
binding path has a `__slots__` entry, **every `FindName` resolves and every
`x:Name` is looked up** (36 and 36, exactly), every control has a tooltip, no
`re`, no pyRevit, and the version agrees across four files.

Proved to bite by reintroducing five faults: a resource key that is not there,
a removed tooltip, a binding with no slot, a lookup with no control, and an
`__init__` on the handler.

### Four faults found while reviewing this build

- **`event -= self._handler` was used to suppress selection callbacks** during
  a rebuild. See above -- it may remove nothing.
- **The family and type of a loaded rule were stored and never restored.** The
  cascade is fetched on Revit's thread, so they cannot be selected until it
  comes back; they are now held and applied when it does, matched Revit's way.
- **`clear` was parsed as though it carried a rule**, which it does not.
- **A guard was inserted above a docstring**, which demotes the docstring to a
  dead expression.

### Not in this version

The dockable panel. It needs a startup-time component and is its own milestone,
blocked on proving `CRIT-3` in Revit. Writing the **project** rule store is
FEAT-14 -- project rules are read and badged, and Save writes the machine store.

## 0.0.4 - 2026-09-09

The Revit half of the rule engine, and a probe button that runs it against a
real model. 155 tests. The tool itself -- the modeless window -- is still 0.1.0.

- **`revit_query`** -- what a rule can be built from and what it matches.
  Categories, families, types, parameters, and the four-stage narrowing:
  category through a view-scoped `FilteredElementCollector`, then family, then
  type, then **only the parameters the rule's conditions name**. Reading every
  parameter of every element is the difference between a live count and a
  frozen window on a real model.
- **Both family shapes answer through one accessor.** A system family (Basic
  Wall, Floor) has no `Family` element at all and its name comes from the
  type's `FamilyName`; a loadable family has a real `Family` and the same
  property returns it. The picker never has to know which it is looking at, and
  never shows an empty level for one of them.
- **`revit_apply`** -- `IsolateElementsTemporary` on the active view, and
  `DisableTemporaryViewMode` to put it back. The only module in the package
  that opens a transaction, gated `try/finally` per S12.9.4. A view that cannot
  be isolated is refused **before** the transaction opens, naming the view
  type. Isolating nothing is refused too: Revit would leave the view showing
  an empty sheet, which looks exactly like a broken tool.
- **`compat`** -- the `ElementId` Int32/Int64 change, `Element.Name`, and
  `List[ElementId]`, which is not optional: a raw Python list across the
  pythonnet bridge is a **fatal** marshalling fault, not an exception.
- **The split is now enforced, not just described.** The Revit half may not
  import `values` -- the comparison engine -- so no decision can drift into the
  half no test on this machine can reach. And no Revit module may carry more
  *statements* than the largest tested module, counted through the AST so
  documentation is free and code is not.
- **`ElementRow` and `select`** are the pure half of the collector, so "what
  does this rule actually match" is proved before a model ever sees it. A row
  is an int id and two names, because a Revit object cannot cross to the WPF
  thread (S12.8.7.2) and an int can.

### The button is a probe now, not a placeholder

It reads the model, builds a rule from what it finds, and will isolate it. It
writes nothing to the project. It exists because four things cannot be answered
anywhere but in Revit, and every one of them is load-bearing:

- whether `GetFilterableParametersInCommon` returns what CRIT-2 assumes;
- whether the cascade is right for a system family as well as a loadable one;
- whether `IsolateElementsTemporary` behaves in a view under a view template,
  and in one already isolated by hand;
- whether rules saved here survive a restart and open in another project.

The report is written to a file **and** printed to the pyRevit console. Root
`todo-list.md` BUG-5 is why: a dialog has to be retyped, a file can be pasted,
and three rounds of findings arrived as screenshots of a panel that said
nothing.

### Three things found while reviewing this build

- `families()` built a collector it never used -- dead work on every call.
- `revit_apply` imported `ViewType` and then kept a fake reference alive to
  stop it looking unused. The import is gone; view types are compared as text,
  which also means a name missing from an older or newer Revit never matches
  rather than raising at import.
- `categories()` also required `AllowsBoundParameters`, which was a guess
  dressed as a rule: it would have hidden any model category that holds
  elements but takes no bound parameters, and a rule isolates those fine.

### Not in this version

The window. **0.1.0** is the cascade picker, the live count, Apply/Clear and
save -- the first build a person would call the tool.

## 0.0.3 - 2026-09-09

The rule engine, built test-first. 131 tests, none of which need Revit. There is
still no window, so nothing is on the ribbon but the scaffold.

- **`lib/anongee_filterrules`** -- the four modules that decide everything about
  a rule that can be decided without a model open: `values` (parsing, units,
  operators), `names` (Revit's idea of the same name), `rules` (`Condition`,
  `Rule`, `RuleSet`), `store` (the JSON files).
- **It is in `lib/`, not beside the script**, which is the one deliberate
  deviation from the house pattern and is forced rather than chosen: the panel
  is registered from `startup.py` on IronPython 2.7, and *pyRevit puts
  `<extension>/lib` on sys.path but nothing below it*, so `lib/` is the only
  folder both engines can import from.
- **The dual-engine contract is enforced statically**, because there is no
  IronPython on the machine that runs the suite: no Python-3-only syntax, no
  annotations, no keyword-only arguments, no starred assignment targets,
  `from __future__ import division` in every module, no `unicode_literals`,
  pure ASCII throughout, no `re`, no `csv`, no `anongee_toolkit`, no Revit.
  An f-string here would otherwise be invisible everywhere except Revit's
  startup, where it would show up as a panel that fails to load.
- **The project store is decided: a JSON file in the model's own folder**,
  `<folder>/AnonGee/filter_view_rules.json`, one per folder rather than per
  model -- a job is a folder with ARC, STR and MEP in it, and a rule about
  columns is about the job. Revit's Extensible Storage was rejected on a point
  of principle rather than convenience: writing it **modifies the model** and
  needs a transaction, and PRD S6.1 says this tool writes nothing to the
  project. A file also stays visible, editable, diffable and shareable, and
  needs no schema GUID that can never be changed afterwards.
  *Workshared models:* `Document.PathName` points at the user's local copy, so
  the caller passes the central path when there is one. `project_path` is pure
  and neither knows nor cares which it was handed.
- **There is no precedence between the two stores.** Both are shown, each rule
  marked with where it came from, and the same name in both gives two rules.
  Picking a winner loses somebody's rule silently, which for a tool whose whole
  job is remembering things is the worst failure available.
- **A value is stored in the unit it was typed in**, and converted at compare
  time. Storing the converted number would lose which unit the rule was written
  in, and that cannot be recovered afterwards.
- **A comma in a value box is refused rather than guessed at.** `1,5` is
  one-and-a-half in half of Europe and fifteen everywhere else.
- **A missing parameter never matches a real comparison.** A wall with no
  Comments is not `Comments = X`, and it is not `Comments != X` either -- it has
  no Comments to disagree with. Only `is empty` says yes.
- **Writing is atomic** -- temp file in the same directory, then rename -- so a
  save that fails costs the new rule rather than every old one, and a reader
  never sees a half-written file.

### One fault the tests found

`Condition` silently folded an unrecognised operator to `equals`. A typo in a
hand-edited rules file would have become a rule that quietly meant something
else, and `problems()` would have had nothing to report. The operator is now
kept as given and named in `problems()`; `matches()` already answered `False`
for anything it could not evaluate, so keeping it costs nothing. The `match`
mode still folds to `all`, and the code says why the two differ.

### Not in this version

The Revit half -- `revit_query`, `revit_apply` -- and the window. **0.1.0** is
the first build that applies a rule to a view.

## 0.0.2 — 2026-09-09

Still nothing runs. What it will do is now decided and written down, and one of
the decisions came back corrected.

- **What pressing a rule does is settled: it temporarily isolates, in the active
  view only.** Saving a rule applies nothing — it adds a button to the list. So
  the tool never writes to the project: no `ParameterFilterElement`, nothing in
  the Filters list, no trace for a colleague opening the model. The alternative
  — writing real view filters — is recorded as FEAT-13 because the parameter
  flag below pays for it, not because it is wanted.
- **Any parameter may be used, with the non-filterable ones flagged.** Because a
  rule isolates rather than filtering, a parameter Revit refuses in a view filter
  still makes a perfectly good button. The flag is honest about the limit today
  and is exactly the check FEAT-13 would need later.
- **Rules live at machine level**, in
  `%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json` — the
  `cad2bim/prefs.py` pattern, so they follow the user into the next project. A
  per-project override is wanted; its location and its precedence are two open
  questions in `todo-list.md` §6, and guessing either can lose somebody's rules.
- **One answer needed correcting, and the correction is the finding.** The panel
  was asked for as *"does not need to start with Revit, only when the user
  clicks the pushbutton"*. That is right about **visibility** and wrong about
  **registration**: `RegisterDockablePane` must be called from
  `OnStartup`, before any document is open, and a pushbutton runs far too late.
  A registered pane is hidden until something calls `Show()` — so the
  requirement holds exactly as stated, and it still costs a startup component.
- **The startup component lands on IronPython, and that was already measured
  here.** pyRevit loads `startup.py` on its core engine, IronPython 2.7, where
  `lib/py3` is not on the path — `/anongee/ping` reported it from inside
  `startup.py` and it is recorded in the platform architecture spec. So the
  window and the panel cannot share a module, and the bridge's own answer
  applies unchanged: **share a folder, not a module.**
- **`PRD.md`** — what a rule is, what pressing one does, the two surfaces, where
  rules live, the seven non-negotiables, the six things it will explicitly not
  do, the staging, and what success looks like in Revit rather than in a test
  runner.
- **`ARCHITECTURE.md`** — the dual-engine constraint and what it costs, the rule
  core that both engines run, the JSON contract and its five rules, four-stage
  matching, why units are stored with the number, applying to a view, the
  dockable pane's registration-vs-visibility split, the failure model, and the
  build order.
- **`FOLDER_STRUCTURE.md`** — where each file goes and why. The rule core sits in
  `lib/`, not beside the script, because *pyRevit puts `<extension>/lib` on
  sys.path but nothing below it* and `startup.py` could never reach a package
  inside a pushbutton bundle. That is the one deviation from the house pattern
  and it is forced, not chosen. Also: what comes from `anongee_toolkit`, what
  deliberately does not, and the six files outside this tool that will need
  touching.
- **The highest-value test in the plan is named**: the core is compiled under
  Python 2.7 syntax rules. There is no IronPython on the CI machine, so an
  f-string in the core is invisible on every developer machine and shows up as a
  dockable panel that fails to load at Revit start.

### Not in this version

Everything, still. **0.1.0** is the modeless window — cascade, conditions, live
count, Apply/Clear, save — and nothing now blocks it.

---

## 0.0.1 — 2026-09-09

The bundle exists. Nothing runs.

- **The ribbon slot is real from the first commit**, so the tool is covered by
  the repository's own checks straight away rather than at the end:
  `tests/test_scripts.py` holds the `#! python3` shebang and every name the
  script reads, and `tests/test_repo_docs.py` holds the README to the folder.
- **Pressing it says so.** A placeholder that opened an empty window would look
  like a broken tool; this one names its version, says what the tool will do,
  and points at the three documents beside it. The first thing anybody presses a
  new button for is to find out what it is.
- **`METHODOLOGY.md`** — how this repository works and what this tool has to
  obey: the engine and its stripped stdlib, the persistent-engine interface
  rules, what `anongee_toolkit` already provides, the design-system rules that
  are load-blockers, the three window modes, how settings survive a session, the
  two-level versioning, and the documentation contract the tests enforce. Plus
  the constraints this tool specifically will run into — §13.
- **`todo-list.md`** — the queue, seeded. Three `CRIT` items, twelve `FEAT`
  items, and four open questions for the project owner. Nothing is specified
  yet; specification is the PRD's job.
- **Placed on `Dev.panel/col3.stack`.** Dev is where tools with no in-Revit
  confirmation live — RC Automation is there for the same reason. A new stack,
  because `Testing`, `col1` and `col2` each already hold pyRevit's maximum of
  three buttons. Promotion to Advance.panel, beside the FilterParameter tools it
  is related to, belongs to the build that is confirmed working.
- **The extension version was deliberately left at 2.0.0.** Adding a tool is a
  MINOR extension change, but this one ships no capability; bumping now would
  claim one. The bump belongs in the commit that ships 0.1.0.

### Not in this version

Everything. There is no rule model, no picker, no persistence, no window, and
no dockable panel. **0.1.0** will be the first build that applies a rule to a
view, and it is blocked on `CRIT-1` and `CRIT-2` in `todo-list.md`.
