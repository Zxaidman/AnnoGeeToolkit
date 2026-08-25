# -*- coding: utf-8 -*-
"""What actually runs when the bridge is asked for something.

The third package, and the one that joins the other two. ``rc_automation`` reads
workbooks and has no Revit in it; ``structural`` writes to Revit and knows
nothing about jobs; ``bridge`` is the pure transport. A **command** is where a
job meets a model.

Every handler has the same shape::

    def run(uiapp, envelope):
        return summary, findings, note

*summary* is a dict of counts for the panel and the log — ``created``,
``modified``, ``matched``, ``skipped``. *findings* are dicts in the shape
``envelope.FINDING_FIELDS`` describes, which is the shape
``rc_automation.models.Issue`` already has. *note* is one sentence, or empty.

**A handler is called on Revit's own thread**, inside the listener's external
event, and must open its own transaction if it writes. It must not assume a
document is open — a job can arrive at any time, including while the user has
nothing loaded — and returning a rejection is how it says so.
"""

__version__ = "0.1.0"


def register_all():
    """Bind every handler into the registry. ``[names]``.

    Called once by the listener. Import happens here rather than at module
    scope so that a handler which fails to import takes itself out rather than
    taking the listener with it — a bridge that will not start because one
    unfinished command has a typo is worse than a bridge missing one command.
    """
    from anongee_toolkit.bridge import registry

    bound = []
    for name, module_name, function in (
            ("bridge.echo", "echo", "run"),
            ("levels.sync", "levels", "run"),
            ("grids.sync", "grids", "run"),
            ("footings.sync", "footings", "run"),
            ("columns.sync", "columns", "run"),
            ("beams.sync", "beams", "run"),
            ("slabs.sync", "slabs", "run"),):
        try:
            module = __import__(
                "anongee_toolkit.commands." + module_name,
                fromlist=[module_name])
            ok, _note = registry.bind(name, getattr(module, function))
            if ok:
                bound.append(name)
        except Exception:
            continue
    return bound
