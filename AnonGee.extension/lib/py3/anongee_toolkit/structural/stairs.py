# -*- coding: utf-8 -*-
"""Real Revit stairs, from the sheet. Writes — and owns its own transactions.

**Option A, chosen by the project owner on 2026-08-27**, over the waist-slab
version that shipped in 1.24.0:

    building stairs with beam and slab is management nightmare and scheduling
    for use Revit own stairs if need use stairs sketch

Which is the right call, and the review document said so: a waist modelled as a
framing member lands in every Structural Framing schedule and has to be
filtered out of each one, for ever. That cost does not go away, and no amount of
work on the other side would have removed it.

**The one thing that makes this module different from every other writer here.**
``StairsEditScope.Start`` throws if a transaction is already open, and it has to
open one of its own. Every other command runs inside a transaction the caller
opened. So this one is handed a document with only a *transaction group* open —
see ``commands._placement.outside_a_transaction`` — and each flight opens, uses
and commits its own scope.

The consequence is worth stating: a run that fails on the fourth of five flights
leaves three built. The others roll back whole. That is a real difference and it
is reported rather than smoothed over.

**What a Revit stair takes from the sheet, and what it decides for itself.** The
type carries the tread depth, the maximum riser and — for a monolithic stair —
the structural depth, which is the waist. The instance carries the riser count.
Revit then works out the riser height by dividing the rise by that count, which
is the same rule :mod:`rc_automation.flight` applies, so the two agree by
construction rather than by luck.
"""

__version__ = "0.2.0"

#: The ``StairsType`` **properties** an RC stair needs. Properties, not
#: parameters: ``LookupParameter("MaxRiserHeight")`` returns ``None`` because
#: the parameter a user sees is called *Maximum Riser Height*. A whole run
#: reported "could not set Monolithic, Waist, Tread, Riser" — four for four —
#: on exactly that mistake. REVIT_API_RESEARCH §0.2.
TREAD = "MinTreadDepth"
RISER = "MaxRiserHeight"
RUN_WIDTH = "MinRunWidth"

#: The waist. It is on the **run** type, not the stair type, and it reads back
#: as 0.0 unless the run is monolithic — so the construction method has to be
#: set first or this writes to nothing and says nothing. §1.5.
WAIST = "StructuralDepth"

#: What a monolithic stair's construction method is called. **Not hard-coded**:
#: the enum's member names could not be confirmed from the public reference, so
#: it is read at runtime and the member whose name contains this wins. §0.1
#: applied to an enum — guessing a name is what cost the last round.
MONOLITHIC_HINT = "monolith"

#: Cached CLR types. A class that subclasses a Revit interface can only be
#: defined once per session — defining it again gives a second, incompatible
#: type — and it cannot be defined at import time because the interface does
#: not exist outside Revit. Same pattern the listener uses for its external
#: event handler.
_CLR = {}


def stairs_types(doc):
    """``[(label, name, ElementId)]`` of the loaded stair types."""
    from Autodesk.Revit.DB import FilteredElementCollector
    from Autodesk.Revit.DB.Architecture import StairsType

    found = []
    for stair_type in (FilteredElementCollector(doc)
                       .OfClass(StairsType)
                       .ToElements()):
        found.append((_name(stair_type), _name(stair_type), stair_type.Id))
    return sorted(found, key=lambda item: item[0])


def ensure_type(doc, wanted, sizes, cache=None, name=None):
    """``(ElementId, note)`` for a stair type — found, or duplicated and sized.

    **Requires a transaction**, which is the awkward part: this has to happen
    *before* the edit scope opens, because a scope cannot start inside a
    transaction and a type cannot be made without one.
    """
    from anongee_toolkit.structural import typemaker

    cache = cache if cache is not None else {}
    key = _fold(name or wanted)
    if key in cache:
        return cache[key], ""

    loaded = stairs_types(doc)
    if not loaded:
        return None, ("this model has no stair type at all, so there is "
                      "nothing to duplicate one from")

    # House name first, the same rule the other four categories follow.
    index, note = typemaker.choose(
        [(label, type_name, "", type_id)
         for label, type_name, type_id in loaded], name, wanted)
    if index is not None:
        cache[key] = loaded[index][2]
        return loaded[index][2], note

    wanted_name = typemaker.sanitise(name or wanted) or wanted
    base = doc.GetElement(loaded[0][2])
    try:
        made = base.Duplicate(wanted_name)
    except Exception as error:
        return None, ("Revit would not create a stair type called {0!r}: "
                      "{1}: {2}".format(wanted_name, type(error).__name__,
                                        _short(error)))

    missed = _size_type(doc, made, sizes)
    cache[key] = made.Id
    note = "created stair type {0!r} from {1!r}".format(wanted_name,
                                                        _name(base))
    if missed:
        note = "{0}, but could not set {1} on it".format(note,
                                                         ", ".join(missed))
    return made.Id, note


def _size_type(doc, stair_type, sizes):
    """Put the sheet's numbers on the type. ``[what would not take]``.

    **Monolithic first.** ``StairsRunType.StructuralDepth`` reads back as 0.0
    unless the run is monolithic, so setting the waist before the construction
    method writes to nothing and reports success.
    """
    from anongee_toolkit.revit.units import mm_to_ft

    missed = []
    if not _make_monolithic(stair_type):
        missed.append("Monolithic")

    for name, value_mm, label in ((RISER, sizes.get("riser_mm"), "Riser"),
                                  (TREAD, sizes.get("tread_mm"), "Tread"),
                                  (RUN_WIDTH, sizes.get("width_mm"), "Width")):
        if not value_mm:
            continue
        if not _set_property(stair_type, name, mm_to_ft(value_mm)):
            missed.append(label)

    if sizes.get("waist_mm") and not _set_waist(doc, stair_type,
                                                mm_to_ft(sizes["waist_mm"])):
        missed.append("Waist")
    return missed


def _make_monolithic(stair_type):
    """Set ``ConstructionMethod`` to whichever member means monolithic.

    Read rather than named, because the enum's members could not be confirmed
    from the public reference and a guessed name is what cost the last round.
    """
    try:
        current = stair_type.ConstructionMethod
    except Exception:
        return False
    for name in dir(type(current)):
        if MONOLITHIC_HINT not in name.lower():
            continue
        try:
            stair_type.ConstructionMethod = getattr(type(current), name)
            return True
        except Exception:
            continue
    return False


def _set_waist(doc, stair_type, value_ft):
    """The waist, on the run type rather than the stair type."""
    try:
        run_type = stair_type.RunType
    except Exception:
        return False
    if run_type is None:
        return False
    return _set_property(run_type, WAIST, value_ft)


def _set_property(owner, name, value):
    """A CLR property, with a named parameter as the fallback.

    The property is the documented member; ``LookupParameter`` is tried second
    because a family-authored type may surface the same idea under the name the
    UI shows. Both are reported as one answer, so the caller says *could not set
    the waist* rather than *could not find StructuralDepth*.
    """
    try:
        setattr(owner, name, value)
        return True
    except Exception:
        pass
    return _set_by_name(owner, name, value)


def create(doc, start_mm, direction, base_level, top_level, flight,
           stairs_type_id, mark=""):
    """Build one flight as a real ``Stairs``. ``(Stairs, note)``.

    **Must be called with no transaction open.** ``StairsEditScope`` starts one
    of its own and refuses if there is already one.
    """
    # StairsEditScope is in Autodesk.Revit.DB. StairsRun and its justification
    # are in .Architecture. There is no rule that gets you from one to the
    # other, and assuming there was placed nothing five times:
    #   cannot import name 'StairsEditScope' from 'Autodesk.Revit.DB.Architecture'
    # REVIT_API_RESEARCH §0.1.
    from Autodesk.Revit.DB import Line, StairsEditScope, Transaction, XYZ
    from Autodesk.Revit.DB.Architecture import (StairsRun,
                                                StairsRunJustification)
    from anongee_toolkit.revit.units import mm_to_ft

    scope = StairsEditScope(doc, "AnonGee stair {0}".format(mark or ""))
    stairs_id = scope.Start(base_level.Id, top_level.Id)

    transaction = Transaction(doc, "AnonGee stair run {0}".format(mark or ""))
    try:
        transaction.Start()
        stairs = doc.GetElement(stairs_id)
        if stairs_type_id is not None:
            try:
                stairs.ChangeTypeId(stairs_type_id)
            except Exception:
                pass

        # The riser count is the instance's, and it is what makes the flight
        # land on the floor. Revit divides the rise by it exactly as
        # `rc_automation.flight` does, so the two agree by construction.
        stairs.DesiredRisersNumber = flight.risers

        base = XYZ(mm_to_ft(start_mm[0]), mm_to_ft(start_mm[1]),
                   base_level.Elevation)
        head = XYZ(mm_to_ft(start_mm[0] + direction[0] * flight.run_mm),
                   mm_to_ft(start_mm[1] + direction[1] * flight.run_mm),
                   base_level.Elevation)
        run = StairsRun.CreateStraightRun(doc, stairs_id,
                                          Line.CreateBound(base, head),
                                          StairsRunJustification.Center)
        try:
            run.ActualRunWidth = mm_to_ft(flight.width_mm)
        except Exception:
            pass

        _set_string(stairs, "ALL_MODEL_MARK", mark)
        transaction.Commit()
    except Exception as error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        try:
            scope.Cancel()
        except Exception:
            pass
        raise error

    scope.Commit(_swallow_warnings())
    return doc.GetElement(stairs_id), ""


def _swallow_warnings():
    """A failure preprocessor that lets Revit's stair warnings through.

    A stair almost always produces at least one — *the stair does not satisfy
    the required riser height* is routine on a sheet-driven flight — and an
    unhandled one aborts the whole edit scope. Warnings are deleted; **errors
    are left alone**, so a stair that genuinely cannot be built still fails.
    """
    from Autodesk.Revit.DB import (FailureProcessingResult,
                                   IFailuresPreprocessor)

    if "swallow" not in _CLR:
        class SwallowStairWarnings(IFailuresPreprocessor):
            # On the class, not the module. pythonnet needs a namespace to
            # build the CLR type into, and a module-level ``__namespace__``
            # does nothing at all — which is a fault the Bridge Listener
            # shipped with for a release because IronPython did not care.
            __namespace__ = "AnonGeeStairs"

            def PreprocessFailures(self, accessor):
                try:
                    accessor.DeleteAllWarnings()
                except Exception:
                    pass
                return FailureProcessingResult.Continue

        _CLR["swallow"] = SwallowStairWarnings
    return _CLR["swallow"]()


def placed(doc):
    """``[(ElementId, (x, y), level_name, type_name)]`` of the stairs there now.

    Keyed on the **midpoint of the first run's path**, which is what the planner
    matches against, and which is the same point the sheet's two grid
    intersections give. A stair whose path cannot be read is skipped rather
    than guessed at.
    """
    from Autodesk.Revit.DB import FilteredElementCollector
    from Autodesk.Revit.DB.Architecture import Stairs
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for stairs in (FilteredElementCollector(doc)
                   .OfClass(Stairs)
                   .WhereElementIsNotElementType()
                   .ToElements()):
        point = _midpoint(doc, stairs, ft_to_mm)
        if point is None:
            continue
        found.append((stairs.Id, point, _base_level_name(doc, stairs),
                      _type_name(doc, stairs)))
    return found


def _midpoint(doc, stairs, ft_to_mm):
    try:
        run_ids = list(stairs.GetStairsRuns())
    except Exception:
        run_ids = []
    for run_id in run_ids:
        run = doc.GetElement(run_id)
        if run is None:
            continue
        try:
            for curve in run.GetStairsPath():
                start = curve.GetEndPoint(0)
                end = curve.GetEndPoint(1)
                return (ft_to_mm((start.X + end.X) / 2.0),
                        ft_to_mm((start.Y + end.Y) / 2.0))
        except Exception:
            continue
    return None


def set_type(doc, stairs, stairs_type_id):
    """Change a placed stair's type. True when it took."""
    try:
        stairs.ChangeTypeId(stairs_type_id)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The small Revit awkwardnesses
# ---------------------------------------------------------------------------

def _set_by_name(element, name, value):
    try:
        parameter = element.LookupParameter(name)
        if parameter is None or parameter.IsReadOnly:
            return False
        return bool(parameter.Set(value))
    except Exception:
        return False


def _set_string(element, built_in_name, value):
    from Autodesk.Revit.DB import BuiltInParameter
    built_in = getattr(BuiltInParameter, built_in_name, None)
    if built_in is None or not value:
        return False
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            return bool(parameter.Set(value))
    except Exception:
        pass
    return False


#: What a stair's base level is called, across Revit versions. Asked by name
#: rather than by attribute, because a missing member on the enum raises at
#: import in one version and works in the next.
BASE_LEVEL_PARAMETERS = ("STAIRS_BASE_LEVEL_PARAM", "STAIRS_BASE_LEVEL")


def _base_level_name(doc, stairs):
    from Autodesk.Revit.DB import BuiltInParameter
    for name in BASE_LEVEL_PARAMETERS:
        built_in = getattr(BuiltInParameter, name, None)
        if built_in is None:
            continue
        try:
            parameter = stairs.get_Parameter(built_in)
            if parameter is None:
                continue
            level = doc.GetElement(parameter.AsElementId())
            if level is not None:
                return _name(level)
        except Exception:
            continue
    try:
        return _name(doc.GetElement(stairs.LevelId))
    except Exception:
        return ""


def _type_name(doc, stairs):
    try:
        return _name(doc.GetElement(stairs.GetTypeId()))
    except Exception:
        return ""


def _name(element):
    try:
        return element.Name
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)
    except Exception:
        return ""


def _short(error):
    text = " ".join("{0}".format(error).split())
    return text[:240] if len(text) > 240 else text


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
