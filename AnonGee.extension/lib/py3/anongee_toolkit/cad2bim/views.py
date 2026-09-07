# -*- coding: utf-8 -*-
"""Which view the run may link into, and which one it should end in.

`Document.Link` does not take any view. It draws the import into the one it is
given, so it needs a view with a drawing surface, and it refuses anything else
before a single element is created:

    Autodesk.Revit.Exceptions.ArgumentException: The view is not printable.
    Parameter name: pDBView

The owner hits that whenever the run starts from a schedule or a sheet, which is
where a structural engineer actually works. His instruction was not to report it
better but to stop reporting it at all: the tool knows the view is wrong and
knows which view is right, so it should simply go there.

Revit-free on purpose. The decision is a rule about view TYPE and NAME, and
those arrive here as plain strings, so the rule can be argued with offline and
`script.py` is left with nothing but the two Revit calls that act on it.
"""


# A LINK NEEDS SOMEWHERE TO BE DRAWN. This is an allow-list rather than a list
# of what to refuse, because Revit's ViewType enum grows with every release and
# a new member should default to "not a host" rather than to a crash inside the
# Link call. Names are `ViewType` members, matched exactly.
HOST_VIEW_TYPES = (
    "FloorPlan",
    "CeilingPlan",
    "EngineeringPlan",       # the structural plan the tool is usually run from
    "AreaPlan",
    "Elevation",
    "Section",
    "Detail",
    "ThreeD",
    "DraftingView",
)

# What the owner asked to be taken to, in the order they are preferred. Revit's
# default 3D view is called `{3D}`; a per-user one is `{3D - <username>}`, which
# is why the match is on the leading brace rather than on the whole name.
_DEFAULT_3D_PREFIX = "{3D"


def can_host_link(view_type, is_template=False):
    """Whether `Document.Link` will accept a view of this type.

    A view TEMPLATE is refused whatever its type: it has the type of the views
    it governs and no drawing surface of its own.
    """
    if is_template:
        return False
    return str(view_type) in HOST_VIEW_TYPES


def choose_host(views):
    """Index of the view to link into, or None when the model has none.

    `views` is [(name, view_type, is_template)]. The order is the owner's: the
    default `{3D}` first, then any other 3D view, then a plan -- and a plan only
    because a model that has had its 3D view deleted should still build rather
    than stop.
    """
    best = None
    for index, view in enumerate(views or []):
        name, view_type, is_template = _unpack(view)
        if not can_host_link(view_type, is_template):
            continue
        rank = _rank(name, view_type)
        if best is None or rank < best[0]:
            best = (rank, index)
    return None if best is None else best[1]


def _rank(name, view_type):
    """Lower is better. Only ever called for a view that CAN host the link."""
    if str(view_type) == "ThreeD":
        return 0 if str(name).startswith(_DEFAULT_3D_PREFIX) else 1
    if str(view_type) in ("FloorPlan", "EngineeringPlan"):
        return 2
    return 3


def choose_3d(views):
    """Index of the 3D view to finish in, or None when there is not one.

    FEAT-11's half of the same question, and deliberately narrower than
    `choose_host`: "open the 3D view" means a 3D view or nothing. Falling back
    to a plan here would leave the owner looking at the same plan he started in
    while the tool claimed it had shown him the model.
    """
    best = None
    for index, view in enumerate(views or []):
        name, view_type, is_template = _unpack(view)
        if is_template or str(view_type) != "ThreeD":
            continue
        rank = 0 if str(name).startswith(_DEFAULT_3D_PREFIX) else 1
        if best is None or rank < best[0]:
            best = (rank, index)
    return None if best is None else best[1]


def _unpack(view):
    """(name, view_type, is_template) from a tuple or from a Revit view."""
    if isinstance(view, (tuple, list)):
        name = view[0] if len(view) > 0 else ""
        view_type = view[1] if len(view) > 1 else ""
        is_template = view[2] if len(view) > 2 else False
        return name, view_type, bool(is_template)
    return (getattr(view, "Name", ""),
            getattr(view, "ViewType", ""),
            bool(getattr(view, "IsTemplate", False)))


def format_elapsed(seconds):
    """How long it took, for a person reading one line of it.

    Seconds alone stop being readable at about a minute -- "412.7 s" is a number
    to convert, not to read -- so this switches to minutes and seconds there,
    and to hours beyond that. Under ten seconds keeps a decimal, because the
    difference between 2 and 2.4 seconds is the whole of a fast run.
    """
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "-"
    if seconds < 0:
        return "-"
    if seconds < 10:
        return "{0:.1f} seconds".format(seconds)
    if seconds < 60:
        return "{0:.0f} seconds".format(seconds)
    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return "{0} min {1:02d} sec".format(minutes, rest)
    hours, minutes = divmod(minutes, 60)
    return "{0} hr {1:02d} min {2:02d} sec".format(hours, minutes, rest)
