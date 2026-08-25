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


def _elevation_mm(point, ft_to_mm):
    """One base point's elevation above the internal origin, in millimetres."""
    try:
        return ft_to_mm(point.Position.Z), ""
    except Exception as error:
        return None, "its position could not be read: {0}".format(error)
