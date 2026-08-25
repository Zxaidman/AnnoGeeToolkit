# -*- coding: utf-8 -*-
"""Where a model's two reference points are, and what that means for a number.

A level has one elevation in Revit and two on a drawing. Revit stores one number
per level, measured from the internal origin; the drawing shows it measured from
either the **Project Base Point** or the **Survey Point**, and those are wherever
somebody put them.

So a level at 3.3 on a structural drawing and the same level at 103.3 on a site
drawing are the same level, and the difference between them is a property of the
model rather than of the sheet. This asks the model for it and reports what it
found, because guessing it is how a building ends up a hundred metres in the air.

**It never moves either point.** Moving the survey point re-coordinates the whole
project, which is a decision somebody makes on purpose and not something a
spreadsheet import does on the way past.
"""

__version__ = "0.1.0"


def survey_offset_mm(doc):
    """``(offset_mm, note)`` — what the survey point reads where the project
    base point reads zero, or ``(None, why not)``.

    ``None`` is a real answer and the callers treat it as one: it means a survey
    elevation cannot be converted, so a row that asked to be measured from the
    survey point is reported rather than built somewhere approximate.
    """
    try:
        from Autodesk.Revit.DB import BasePoint
        from anongee_toolkit.revit.units import ft_to_mm
    except Exception as error:                          # pragma: no cover
        return None, "the Revit API would not load: {0}".format(error)

    try:
        project = BasePoint.GetProjectBasePoint(doc)
        survey = BasePoint.GetSurveyPoint(doc)
    except Exception as error:
        return None, "this model has no base points: {0}".format(error)

    if project is None or survey is None:
        return None, "this model has no project base point or survey point"

    project_mm, project_note = _elevation_mm(project, ft_to_mm)
    if project_mm is None:
        return None, "the project base point: {0}".format(project_note)

    survey_mm, survey_note = _elevation_mm(survey, ft_to_mm)
    if survey_mm is None:
        return None, "the survey point: {0}".format(survey_note)

    # Both are measured from the internal origin, so the difference is what the
    # survey reads where the project base reads zero.
    offset = project_mm - survey_mm
    return offset, "survey point is {0:g} mm below the project base point".format(
        offset)


def set_survey_offset_mm(doc, wanted_mm):
    """Move the survey point so it reads *wanted_mm* where the project base
    point reads zero. ``(moved, note)``. **Requires a transaction.**

    The one thing in this module that writes, and it is off unless the workbook
    asks — because moving a survey point re-coordinates a whole project. Every
    shared coordinate, every linked model's alignment, every site drawing. That
    is a decision somebody makes on purpose, not a convenience a spreadsheet
    import helps itself to.

    The survey point is **pinned** in a fresh model, and setting a pinned
    element's parameter fails silently rather than loudly. So it is unpinned,
    moved, and pinned again exactly as it was found.
    """
    try:
        from Autodesk.Revit.DB import BasePoint, BuiltInParameter
        from anongee_toolkit.revit.units import ft_to_mm, mm_to_ft
    except Exception as error:                          # pragma: no cover
        return False, "the Revit API would not load: {0}".format(error)

    current, note = survey_offset_mm(doc)
    if current is not None and abs(current - wanted_mm) < 0.5:
        return False, "the survey point is already {0:g} mm".format(wanted_mm)

    try:
        project = BasePoint.GetProjectBasePoint(doc)
        survey = BasePoint.GetSurveyPoint(doc)
    except Exception as error:
        return False, "this model has no base points: {0}".format(error)
    if project is None or survey is None:
        return False, "this model has no project base point or survey point"

    was_pinned = False
    try:
        was_pinned = bool(survey.Pinned)
        if was_pinned:
            survey.Pinned = False
    except Exception:
        pass

    try:
        # The offset is project-base minus survey, both measured from the
        # internal origin — so moving the survey point down by the difference
        # is what makes the offset come out right.
        wanted_z = ft_to_mm(project.Position.Z) - wanted_mm
        parameter = survey.get_Parameter(
            BuiltInParameter.BASEPOINT_ELEVATION_PARAM)
        if parameter is None or parameter.IsReadOnly:
            return False, "the survey point's elevation cannot be written here"
        parameter.Set(mm_to_ft(wanted_z))
        moved = True
        message = "the survey point now reads {0:g} mm where the project " \
                  "base point reads zero".format(wanted_mm)
    except Exception as error:
        moved = False
        message = "the survey point would not move: {0}".format(error)
    finally:
        try:
            if was_pinned:
                survey.Pinned = True
        except Exception:
            pass

    del note
    return moved, message


def _elevation_mm(point, ft_to_mm):
    """One base point's elevation above the internal origin, in millimetres."""
    try:
        return ft_to_mm(point.Position.Z), ""
    except Exception as error:
        return None, "its position could not be read: {0}".format(error)
