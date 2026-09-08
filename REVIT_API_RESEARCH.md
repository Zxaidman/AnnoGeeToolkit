# Revit API research

**What this file is.** The Revit API members this programme actually uses,
checked against the published reference rather than recalled, with the trap
attached to each. It exists because four separate rounds have now been lost to
an API detail that a thirty-second lookup would have settled, and the last one —
stairs — failed on a *namespace*.

**What it is not, and this matters.** It is not every Revit API. The 2025+ API
publishes on the order of ten thousand public members across `RevitAPI.dll` and
`RevitAPIUI.dll`, and no useful document contains them all: an index that large
is a search engine with worse search. A file claiming completeness would also be
the file nobody checks a claim against, which is exactly the failure it is meant
to prevent.

So the rule here is **coverage by contact**: a member earns a place when this
repository calls it, or when it was considered and rejected. Everything below is
one of those. When something new is needed, §0 says how to settle it before the
first line is written, and the answer gets added here.

---

## 0. Settle it before you write it

Five rules, each of which has cost this project at least one round in a live
model.

### 0.1 A namespace is not guessable

`StairsEditScope` is in **`Autodesk.Revit.DB`**. `Stairs`, `StairsRun`,
`StairsType`, `StairsRunType` and `StairsRunJustification` are all in
**`Autodesk.Revit.DB.Architecture`**. There is no rule that gets you from one to
the other, and the run that assumed there was placed nothing five times:

```
cannot import name 'StairsEditScope' from 'Autodesk.Revit.DB.Architecture'
```

Import the namespace, not the name, when there is any doubt — the failure then
happens at the call site, where it is readable, rather than at import:

```python
import Autodesk.Revit.DB as DB
import Autodesk.Revit.DB.Architecture as Arch
scope = DB.StairsEditScope(doc, "…")          # DB, not Arch
run = Arch.StairsRun.CreateStraightRun(...)   # Arch, not DB
```

### 0.2 A property is not a parameter

`LookupParameter("MaxRiserHeight")` returns `None`. The API surfaces
`StairsType.MaxRiserHeight` as a **CLR property**; the *parameter* a user sees is
called "Maximum Riser Height". Guessing the parameter name from the property name
fails silently — it returns `None` and the code moves on.

This produced a whole run reporting:

> created stair type 'CH-1200 X 150' … **but could not set Monolithic, Waist,
> Tread, Riser on it**

Four for four. Prefer the property. Reach for `LookupParameter` only for
family-authored parameters, and for those use the name **as the UI shows it**.

### 0.3 A raw Python list is not a .NET list

`List[GeometryObject]()`, never `[]`, and never `List[object]()` — `object` is
Python's builtin, not `System.Object`, and pythonnet answers:

```
type(s) expected
```

Third time this has cost a round. `§12.9.4`.

### 0.4 A CLR interface subclass needs `__namespace__` **on the class**

At module scope it does nothing. It also cannot be declared at import time,
because the interface does not exist off Revit — so the class is built lazily
and cached, since defining it twice gives two incompatible CLR types and
`Duplicate type name within an assembly` on the second press.

```python
_CLR = {}

def _preprocessor():
    from Autodesk.Revit.DB import FailureProcessingResult, IFailuresPreprocessor
    if "swallow" not in _CLR:
        class Swallow(IFailuresPreprocessor):
            __namespace__ = "AnonGeeStairs"      # on the class
            def PreprocessFailures(self, accessor):
                accessor.DeleteAllWarnings()
                return FailureProcessingResult.Continue
        _CLR["swallow"] = Swallow
    return _CLR["swallow"]()
```

### 0.5 An edit scope is not a transaction, and will not start inside one

`StairsEditScope.Start` throws if a transaction is open, and opens a transaction
group of its own. Everything else this repository writes runs *inside* a
transaction the caller opened, so stairs needed a second write strategy —
`commands/_placement.outside_a_transaction` — that keeps the group and leaves the
transaction to the scope.

---

## 1. Stairs

Everything here is checked against the reference; the citations are at the end
of the section. **Untested in a model at the time of writing** — the previous
attempt never got past the import.

### 1.1 The shape of a stair

| | Namespace | What it is |
| --- | --- | --- |
| `StairsEditScope` | `Autodesk.Revit.DB` | The session inside which a stair may be built |
| `Stairs` | `…DB.Architecture` | The stair element |
| `StairsRun` | `…DB.Architecture` | One flight |
| `StairsLanding` | `…DB.Architecture` | One landing |
| `StairsType` | `…DB.Architecture` | The stair's type |
| `StairsRunType` | `…DB.Architecture` | The **run's** type — where the waist lives |
| `StairsRunJustification` | `…DB.Architecture` | `Center`, `Left`, `Right` |

### 1.2 The creation sequence, and its order is load-bearing

```python
scope = StairsEditScope(doc, "New Stairs")          # no transaction open
stairs_id = scope.Start(base_level.Id, top_level.Id)
t = Transaction(doc, "Add runs")                     # now a transaction
t.Start()
run = StairsRun.CreateStraightRun(doc, stairs_id, line, StairsRunJustification.Center)
run.ActualRunWidth = width_ft
t.Commit()
scope.Commit(failure_preprocessor)                   # takes IFailuresPreprocessor
```

`Start(bottomLevelId, topLevelId)` returns the new stair's `ElementId`. The
`line` is drawn **in plan at the base level's elevation**; the climb comes from
the two levels, never from the line.

`scope.Commit` **requires** an `IFailuresPreprocessor`. A sheet-driven flight
routinely raises *the stair does not satisfy the required riser height*, and an
unhandled warning aborts the whole scope — so warnings are deleted and errors
are left to fail.

### 1.3 `Stairs` — the members worth having

| Member | Type | Note |
| --- | --- | --- |
| `DesiredRisersNumber` | `int`, get/set | **What makes a flight land on the floor.** Revit divides the rise by it |
| `ActualRisersNumber` | `int`, read-only | What was built. Compare the two |
| `ActualRiserHeight` | `double`, read-only | Feet |
| `ActualTreadsNumber` | `int`, read-only | |
| `ActualTreadDepth` | `double`, get/set | |
| `Height` | `double` | Base to top level |
| `BaseElevation` / `TopElevation` | `double` | |
| `MultistoryStairsId` | `ElementId` | |
| `NumberOfStories` | `int` | 1 for a single-storey stair |
| `GetStairsRuns()` | `ICollection<ElementId>` | |
| `GetStairsLandings()` | `ICollection<ElementId>` | |
| `GetStairsSupports()` | `ICollection<ElementId>` | |
| `GetAssociatedRailings()` | | |
| `IsInEditMode()` | `bool` | |

**There is no base-level property on `Stairs`.** `BaseElevation` is a number, not
a level. Reach the level through `BuiltInParameter.STAIRS_BASE_LEVEL_PARAM`, and
fall back to matching `BaseElevation` against the model's levels.

### 1.4 `StairsType` — properties, not parameters

| Property | Type | |
| --- | --- | --- |
| `MaxRiserHeight` | `double` | Feet. `> 0`, `<= 30000` |
| `MinTreadDepth` | `double` | Feet |
| `MinRunWidth` | `double` | Feet |
| `ConstructionMethod` | `StairsConstructionMethod` | Monolithic vs assembled |
| `RunType` | `StairsRunType` | **The waist is on this, not here** |
| `LandingType` | `StairsLandingType` | |
| `LeftSideSupportType` / `RightSideSupportType` / `MiddleSupportType` | `StairsSupportType` | |
| `HasMiddleSupports` | `bool` | |
| `MiddleSupportsNumber` | `int` | |
| `LeftLateralOffset` / `RightLateralOffset` | `double` | |
| `NotchExtension` / `NotchThickness` / `NotchHorizontalGap` / `NotchVerticalGap` | `double` | |
| `EndConnectionType` | `StairsLandingConnectionType` | |

### 1.5 `StairsRunType` — and the waist

| Property | Type | |
| --- | --- | --- |
| `StructuralDepth` | `double`, get/set | **The waist.** Only meaningful for a monolithic run — *returns 0.0 if the run is not monolithic* |
| `TreadThickness` | `double` | |
| `RiserThickness` | `double` | |

**So the order is forced:** make the stair monolithic first, then set
`StructuralDepth`. Setting the waist on a non-monolithic run writes to something
that reads back as zero, and nothing complains.

`StairsConstructionMethod`'s member names could not be confirmed from the public
reference. **Do not hard-code one** — read the enum at runtime and take the
member whose name contains `monolith`, and report what was found. That is the
§0.1 lesson applied to an enum.

### 1.6 What an RC stair maps to

| Workbook | Where it goes |
| --- | --- |
| `Width` | `StairsRun.ActualRunWidth` (per run), `StairsType.MinRunWidth` |
| `Waist` | `StairsRunType.StructuralDepth`, monolithic first |
| `Tread` | `StairsType.MinTreadDepth` |
| `Riser` | `StairsType.MaxRiserHeight`, and the **count** on `Stairs.DesiredRisersNumber` |

Sources:
[StairsEditScope](https://www.revitapidocs.com/2015/47e4576e-4b01-ed1f-6dc1-885b6780aa07.htm) ·
[Creating and Editing Stairs](https://help.autodesk.com/cloudhelp/2024/ITA/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Stairs_and_Railings/Revit_API_Revit_API_Developers_Guide_Revit_Geometric_Elements_Stairs_and_Railings_Creating_and_Editing_Stairs_html.html) ·
[Stairs members](https://www.revitapidocs.com/2023/e306937c-0f0e-288f-6a5b-ac4e9c41fe42.htm) ·
[StairsType members](https://www.revitapidocs.com/2015/03e9941e-aa3e-64e9-125a-5d94d319e673.htm) ·
[MaxRiserHeight](https://www.revitapidocs.com/2025.3/70999f80-decb-bdbb-d251-662dfcd1bf10.htm) ·
[StairsRunType.StructuralDepth](https://apidocs.co/apps/revit/2025/796c6515-9e91-e455-d0e8-91b15241074c.htm) ·
[CreateStraightRun](https://www.revitapidocs.com/2015/54fd7462-c16c-41bf-705f-ede3af0bc572.htm)

---

## 2. Types, and duplicating them

What every placement command does before it places anything.

| Call | Note |
| --- | --- |
| `ElementType.Duplicate(name)` | Throws when *name* is already used **in that family**. A name already taken means the type exists — but **a name is not a size**, so check what it measures before reusing it |
| `FamilySymbol.Activate()` | A symbol must be active before `NewFamilyInstance`. Follow with `doc.Regenerate()` |
| `FamilySymbol.Family.GetFamilySymbolIds()` | The siblings, for finding a name collision before provoking one |
| `Element.Name` | Raises on some elements; fall back to `Element.Name.GetValue(element)` |
| `BuiltInParameter.ALL_MODEL_TYPE_MARK` | The Type Mark. Writing it is what makes a created type findable on the second run |
| `Floor.Create(doc, IList<CurveLoop>, typeId, levelId)` | Pads and slabs. The loops must be a typed list |

**Names Revit refuses:** `\ : { } [ ] | ; < > ? \` ~` and leading or trailing
spaces. `Duplicate` throws rather than sanitising.

---

## 3. Units

Revit's internal unit is the **decimal foot**, whatever the project's display
units say. A foot is 304.8 mm exactly. Every number crossing into the API is
converted; every number coming out is converted back. There is no exception to
this and no parameter that quietly honours millimetres.

---

# Part 2 — Reinforcement

The original contents of this file, kept whole. Gathered after a real run
reported `Constrained rebar isn't a free form rebar element`.

## 1. Shape-driven and free-form are two different APIs

Almost every confusing thing about rebar constraints comes from this split.

| | Shape-driven (what we create) | Free-form |
| --- | --- | --- |
| Created by | `Rebar.CreateFromCurves` / `CreateFromRebarShape` | `Rebar.CreateFreeForm` |
| Constraints are | **chosen from candidates Revit offers** | **constructed** with `RebarConstraint.Create` |
| `GetConstraintCandidatesForHandle` | returns the possibilities | returns an **empty list** |
| "current" vs "preferred" | different things — preferred overrides Revit's default pick | the same thing |

So for our bars the sequence is *ask, then pick* — never *build*:

```python
manager = rebar.GetRebarConstraintsManager()
for handle in manager.GetAllHandles():
    for candidate in manager.GetConstraintCandidatesForHandle(handle, host.Id):
        if candidate.IsToCover():
            manager.SetPreferredConstraint(candidate)
            break
manager.ApplyRebarConstraints()
```

`SetPreferredConstraint` takes **the constraint alone** — it already knows its
handle. The earlier code passed `(handle, constraint)`, which is the free-form
signature.

### `RebarConstraintsManager` — the useful members

| Member | Why it matters |
| --- | --- |
| `GetAllHandles()` | every handle on the bar — ends, plane, faces |
| `GetAllConstrainedHandles()` | only the ones already tied to something |
| `GetConstraintCandidatesForHandle(handle, ElementId)` | **the one to use** — everything on that host the handle could be tied to |
| `GetConstraintCandidatesForHandle(handle, Reference)` | narrower: candidates against one face |
| `GetCurrentConstraintOnHandle(handle)` | what is acting now |
| `GetPreferredConstraintOnHandle(handle)` | what we asked for |
| `SetPreferredConstraintForHandle(handle, constraint)` | **the one that works.** Obsolete from 2025 in favour of the handle-less form, and still the only one that takes |
| `SetPreferredConstraint(constraint)` | the 2025 replacement. Reported success and changed nothing on the build a real run used, so it is tried and verified rather than trusted |
| `SetPreferredConstraintsToSurfaceForHandles(...)` | bulk form, worth trying for a whole face |
| `RemovePreferredConstraintFromHandle(handle)` | back to Revit's own choice |
| `ApplyRebarConstraints(...)` | **not parameterless.** Calling it as `ApplyRebarConstraints()` raises *"No method matches given arguments"*. Setting the preferred constraint on the handle is itself the commit, so nothing needs it |
| `HasValidRebar()` | the bar survived whatever else happened |
| `HighlightHandleConstraintPairInAllViews(...)` | **diagnostic gold** — shows on screen what a handle is tied to |

### `RebarConstraint` — how to recognise the right candidate

| Member | Use |
| --- | --- |
| `IsToCover()` | **the test that matters** — this candidate follows the cover, not a bare face |
| `IsToHostFaceOrCover()` / `IsFixedDistanceToHostFace()` | the weaker alternatives |
| `GetTargetCoverType()` | which `RebarCoverType` it follows — lets us verify we tied to the cover we set |
| `GetTargetElement()` | confirm it is our footing and not a neighbour |
| `GetRebarConstraintTargetHostFaceType()` | Top / Bottom / Side, so ends and plane can be told apart. For the report; not reliable enough to *choose* on |
| `GetDistanceToTargetCover()` | **how the right candidate is chosen.** A pad offers a cover candidate for every face, so `IsToCover()` narrows the list and does not pick from it; the handle's own face is the one it is nearest. **Signed** — compare absolute values, or the most negative wins and that is the face furthest behind the handle |
| `SetDistanceToTargetCover(d)` | an offset from the cover, for a layer that sits behind another. Set to 0 for a handle already on its cover, so the model carries a round number rather than a rounding artefact — never for one with a real offset, which would move the steel |
| `GetConstraintType()` | the enum, for reporting |
| `IsValid()` | before relying on any of it |

---

## 2. Varying-length sets are a property, not a method

The ribbon's **Varying Rebar Set** — "allows varying lengths of individual bars
within a host … will snap to the host cover in both variable distribution
applications and skewed orientations" — is one flag:

```python
accessor = rebar.GetShapeDrivenAccessor()
accessor.UseRebarConstraintsToProduceVaryingBars = True
```

It only does anything once the handles are constrained, which is why it belongs
*after* the constraint step. The name says it: the constraints produce the
variation.

### `RebarShapeDrivenAccessor` — the rest of it

| Member | Note |
| --- | --- |
| `UseRebarConstraintsToProduceVaryingBars` | the varying-set flag |
| `SetLayoutAsMaximumSpacing(spacing, arrayLength, barsOnNormalSide, includeFirst, includeLast)` | what the manual workflow uses — Revit fills the span |
| `SetLayoutAsNumberWithSpacing(count, spacing, …)` | when the schedule states both |
| `SetLayoutAsFixedNumber(count, arrayLength, …)` | count only |
| `SetLayoutAsMinimumClearSpacing(spacing, arrayLength, …)` | clear distance rather than centres — closer to how detailers think |
| `SetLayoutAsSingle()` | one bar |
| `ArrayLength` | the distribution length — **readable after constraining**, which is how to check Revit filled what we expected |
| `Normal`, `BarsOnNormalSide` | the plane, and which side bars sit |
| `GetDistributionPath()` → `Line` | where the set actually runs; a good assertion |
| `GetBarPositionTransform(i)` | where bar *i* ended up — the way to verify a varying set from code |
| `ComputeDrivingCurves()` | the curves Revit derived, versus the ones we handed it |
| `ScaleToBox(origin, xVec, yVec)` | fit a shape to a box |
| `FlipRebarSet()` | when the normal came out backwards |

`GetBarPositionTransform` and `ArrayLength` together are how a run can *check
itself* after writing, instead of trusting that a set landed correctly.

---

## 3. The manual workflow, mapped to the API

The sequence a detailer follows by hand, and what each step is in code:

| # | By hand | In the API |
| --- | --- | --- |
| 1 | Sketch the foundation to the schedule | `Floor.Create(doc, loops, typeId, levelId)`, then `FLOOR_PARAM_IS_STRUCTURAL = 1` |
| 2 | Create the cover, apply it to the footing | `RebarCoverType.Create(doc, name, distance)`; set `CLEAR_COVER_TOP` / `_BOTTOM` / `_OTHER` |
| 3 | Model the bar in section, constrain each face to its cover line | `CreateFromCurves`, then candidates → `IsToCover()` → nearest by `abs(GetDistanceToTargetCover())` → `SetPreferredConstraintForHandle` |
| 4 | Set the set to maximum spacing; Revit fills the span cover to cover | `SetLayoutAsMaximumSpacing`; `ArrayLength` reads back what it filled |
| 5 | Turn on obscured rebar in all views | `SetSolidInView(view, True)` / `SetUnobscuredInView(view, True)` per view |

Step 4 is the one that changes our design: **once the ends are constrained to
cover, Revit derives the length.** We currently compute every bar's extent
ourselves by intersecting the outline. That still matters for planning and for
the bending schedule, but the model should be told the constraint and allowed to
do its own arithmetic — that is what makes the bars follow a later edit.

---

## 4. One set per distribution region

A varying set covers **one** region of varying depth. Told to vary across a
change of slope it interpolates straight through the corner and fans bars out
past the concrete — which is what a run against a house-shaped pad produced.

**The breaks are the outline's vertices, projected onto the array axis.**
Between two consecutive vertices the edges are straight, so bar length varies
linearly and one set describes the stretch. At a vertex the slope changes and it
cannot.

For a house — rectangle with a gable, apex at x=2250, eaves at y=3000:

| Layer | Regions | Behaviour |
| --- | --- | --- |
| X bars (arrayed along Y) | `y 0–3000`, `y 3000–4200` | one **plain** set across the rectangle, one **varying** set over the gable |
| Y bars (arrayed along X) | `x 0–2250`, `x 2250–4500` | **two varying** sets, one rising to the apex and one falling from it |

Implemented in `rebar_spec.region_breaks` and `split_into_regions`. Bar
positions are computed once across the whole layer and then *assigned* to
regions, so the spacing stays uniform across the pad and the split only decides
where one set ends and the next begins.

## 4a. `RebarHostData.SetCoverType` takes a face Reference

Not a face enum. An earlier attempt guessed at a `RebarCoverFaceType` that does
not exist, so nothing was written and nothing said so. The routes that work:

| Route | Note |
| --- | --- |
| `CLEAR_COVER_TOP` / `_BOTTOM` / `_OTHER` parameters | the practical one — but they do not exist on a floor until it is structural **and the document has regenerated** |
| `RebarHostData.SetCommonCoverType(coverType)` | all faces at once, no `Reference` needed — a good fallback |
| `RebarHostData.SetCoverType(Reference, RebarCoverType)` | per face, and needs a face `Reference` off the geometry |

`doc.Regenerate()` matters more than it looks in two places: after a floor is
made structural and before its cover is written, and after a bar is created and
before its constraint candidates are asked for. A thing Revit has not caught up
with yet has no parameters and no handles.

---

## 4b. Cover measures the steel, and the API is given centrelines

`Rebar.CreateFromCurves` takes the **centreline**. Cover is measured to the
outside of the bar. The two differ by half a diameter, and which way depends on
what the bar presents to the face:

| At | What faces the cover | Where the centreline goes |
| --- | --- | --- |
| A straight end | the bar's **end face** | on the cover plane |
| A turned-up leg | the bar's **barrel** | half a diameter inside the cover plane |

The inset at a bend is `d/2` and is independent of the bend radius. For a 90°
bend of centreline radius `r`, the arc centre sits `r` in from the corner and
the outer surface is `r + d/2` from that centre, so the outermost steel is
always `d/2` outside the corner point handed to the API.

This is what put every U-bar's legs outside the cover while the bars themselves
were inside the concrete: the corner was placed on the cover plane, so the
outside of each leg was half a bar past it. Neither an error nor a warning —
just wrong on a drawing.

The same reasoning fixes the leg's top. Top cover measures the leg's **end
face**, so the leg stops exactly on the cover plane and the constraint that
holds it there carries a distance of zero. Stopping half a bar short is safe
steel with an offset nobody scheduled and nobody can read off a drawing.

---

## 5. Other API worth having in the toolkit

Found while reading, useful beyond the immediate bugs:

| API | What it would give us |
| --- | --- |
| `RebarHostData.GetCoverType(face)` / `SetCoverType` | read and set cover **through the host** rather than by hunting built-in parameters per category — one call that works for floors, walls and family instances alike |
| `RebarHostData.GetRebarsInHost()` | already used; also the way to find what a re-run must leave alone |
| `Rebar.GetShapeDrivenAccessor().GetBarPositionTransform(i)` | verify placement after writing |
| `RebarBarType.GetBendData()` / `RebarBendData` | bend radii and hook geometry **from the model**, instead of recomputing BS 8666 ourselves — worth reconciling against `standards/BS_8666_2020.py` |
| `RebarShape` + `RebarShapeDefinitionBySegments` | define a shape once and place by shape rather than by curves; the BBS reads shape codes off the shape element, so this is how a placed bar gets the right code without inference |
| `Rebar.CreateFromRebarShape` | placement by shape, which pairs with the above |
| `RebarContainer` | group a footing's bars into one element — fewer things in the browser, and a natural unit for "everything this tool made for F1-A1" |
| `RebarRoundingManager` | project rounding for bar lengths, so our numbers agree with the schedule Revit prints |
| `FabricSheet` / `FabricArea` | mesh reinforcement, for slabs later |
| `RebarUpdateCurvesData` | for free-form bars driven by our own rules — a possible route for genuinely arbitrary pad shapes |
| `Rebar.SetHostId(doc, hostId)` | **exists after all** — worth verifying, because it would change the phase 3 plan, which assumes a bar cannot be re-hosted and has to be recreated |

That last row matters most: the phase 3 note in the feasibility review states
flatly that Revit has no re-host. If `SetHostId` does what it appears to, the
"capture → recreate → verify" dance for dependent rebar can be replaced by
moving the bar, and the reasoning recorded there needs revisiting before phase 3
is built.

---

## 6. What this changes in RC Automation

1. **Constraints** *(done, 0.5.0 and 0.7.0)*: stop calling
   `RebarConstraint.Create`; ask for candidates, narrow with `IsToCover()`,
   pick the **nearest by `abs(GetDistanceToTargetCover())`**, then
   `SetPreferredConstraintForHandle`. There is no `ApplyRebarConstraints()` to
   follow it with.
2. **Varying sets** *(done, 0.6.0)*: set
   `UseRebarConstraintsToProduceVaryingBars` after constraining, per
   distribution region.
3. **Layout**: prefer `SetLayoutAsMaximumSpacing` and let Revit fill between the
   constrained ends, rather than computing the span ourselves.
4. **Cover** *(partly done, 0.6.0 and 0.7.0)*: the built-in parameters are the
   route that works today, with `SetCommonCoverType` as the fallback; one cover
   type **per face**, keyed and matched by face as well as by value.
   `RebarHostData.SetCoverType` still wants a face `Reference`, which is worth
   revisiting.
5. **Regions** *(done, 0.6.0)*: cut a varying layer into one set per region of
   constant behaviour.
6. **Verification** *(partly done, 0.6.0)*: `ArrayLength` is read back;
   `GetBarPositionTransform` is not yet.
7. **Geometry** *(done, 0.7.0)*: the API takes centrelines and cover measures
   steel — a bend goes half a diameter inside the cover plane, a straight end on
   it. See §4b.
