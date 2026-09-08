# -*- coding: utf-8 -*-
"""Every command the bridge knows, declared once.

A command is named here and nowhere else. The HTTP route, the file drop, the
listener and — later — an MCP layer all read this, so a command cannot work in
one place and be missing from another. The alternative is three lists that
drift, and the symptom is a button that works in Revit and not from Excel.

Two halves, and keeping them apart is the point:

**What a command is** — its name, the sheet it reads, whether it writes to the
model, and a sentence saying what it does. Pure data, declared at import, and
readable by anything.

**What runs it** — a callable, bound at runtime by the listener. It lives in the
Revit half and must never be imported from here, or this module stops being
importable off Revit and takes the tests with it.

The name is ``noun.verb`` and the verb is nearly always ``sync``, because there
is no ``create``: every command matches first, then creates, modifies, skips or
reports. Pressing a button twice must not build the job twice.
"""

__version__ = "0.1.0"


class Command(object):
    """One thing the bridge can be asked to do."""

    __slots__ = ("name", "sheet", "writes", "summary", "handler")

    def __init__(self, name, sheet="", writes=True, summary=""):
        self.name = name
        #: Which workbook sheet it reads. Empty for a command that reads none.
        self.sheet = sheet
        #: Whether a real run touches the model. A read-only command needs no
        #: dry run and no undo step, and saying so is what lets the UI stop
        #: asking about both.
        self.writes = writes
        self.summary = summary
        #: Bound by the listener, in the Revit half. ``None`` here always.
        self.handler = None

    @property
    def bound(self):
        return self.handler is not None

    def __repr__(self):
        return "<Command {0}{1}>".format(self.name,
                                         "" if self.bound else " unbound")


#: Declared in the order they were built, which is also the order of the stages.
COMMANDS = {}


def declare(name, sheet="", writes=True, summary=""):
    """Add a command to the registry. Returns it."""
    command = Command(name, sheet, writes, summary)
    COMMANDS[name] = command
    return command


def bind(name, handler):
    """Attach the callable that runs a declared command.

    ``(ok, note)``. Binding an undeclared name is refused rather than accepted
    quietly — a handler nobody declared is a command the workbook cannot name
    and the UI cannot list, so it would never run and nothing would say why.
    """
    command = COMMANDS.get(name)
    if command is None:
        return False, "{0} is not a declared command".format(name)
    command.handler = handler
    return True, ""


def get(name):
    return COMMANDS.get((name or "").strip())


def known():
    """Every command name, sorted. What the UI lists and the route reports."""
    return sorted(COMMANDS)


def unbound():
    """Declared but with nothing to run them. A build check, not a runtime one."""
    return sorted(name for name, command in COMMANDS.items()
                  if not command.bound)


# ---------------------------------------------------------------------------
# The commands
# ---------------------------------------------------------------------------
# Stage 0 — proving the wire. Reads nothing, writes nothing, and exists so that
# an end-to-end job can be run before any command that would touch a model.
declare("bridge.echo", writes=False,
        summary="Answer with what was asked, and what the model is. Touches "
                "nothing — the job a first run should be.")

# Stage 1 — datum. The sheets are declared before the handlers exist, so the
# workbook can be built and validated against a registry that already knows
# what it is going to be asked for.
declare("levels.sync", sheet="LEVELS",
        summary="Match the LEVELS sheet against the model's levels, then "
                "create, modify or leave each one alone.")
declare("grids.sync", sheet="GRIDS",
        summary="Match the GRIDS sheet against the model's grids, then create, "
                "modify or leave each one alone.")

# Stage 3 - structure. Declared before they are written, for the same reason
# the datum commands were: the sample workbook can then be built and checked
# against a registry that already knows what it will be asked for, and pressing
# an unbuilt button answers "declared but not built yet" rather than failing
# obscurely. The owner's first run proved that reads as a clear failure.
declare("footings.sync", sheet="FOOTING_PLACEMENT",
        summary="Create the pad footings the placement sheet lists, as "
                "structural floors so an arbitrary outline can be drawn.")
declare("columns.sync", sheet="COLUMN_PLACEMENT",
        summary="Create the structural columns the placement sheet lists, one "
                "per storey, between the base and top levels it names.")
declare("beams.sync", sheet="BEAM_PLACEMENT",
        summary="Create the structural framing the placement sheet lists, "
                "between the grid intersections it names.")
declare("slabs.sync", sheet="SLAB_PLACEMENT",
        summary="Create the floor slabs the placement sheet lists, from the "
                "outline each one carries.")
declare("stairs.sync", sheet="STAIR_PLACEMENT",
        summary="Create the RC stairs the placement sheet lists — a waist "
                "slab, a landing and the steps, as separate elements that "
                "each carry their own volume.")

# The first command that answers into a sheet rather than a model. It needs no
# document and opens no transaction, and it ignores Write? because there is
# nothing in Revit to be careful about.
declare("naming.refresh", sheet="NAMING", writes=False,
        summary="Rewrite the NAMING sheet's Example, Fields and What it names "
                "columns from the patterns beside them, so the sheet cannot "
                "disagree with itself.")
