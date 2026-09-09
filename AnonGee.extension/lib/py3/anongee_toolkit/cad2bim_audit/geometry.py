# -*- coding: utf-8 -*-
"""Plain-float geometry for the audit. No Revit, no ezdxf, no numpy.

Every function takes a list of (x, y, z) tuples and tolerates the degenerate
cases a real drawing produces -- an empty list, a single point, a "polyline"
whose vertices are all identical. A report is a diagnostic: it must describe
broken geometry, not fall over on it. So nothing here raises; the answer to
"what is the centroid of nothing" is None, and callers show a blank cell.

Coordinates are millimetres by the time they reach here (see space.py).
"""

import math


#: Below this plan area (mm^2) a ring has no usable area centroid and the
#: vertex mean is used instead. A hair's width squared: small enough that no
#: real member falls through, large enough to keep the division stable.
_DEGENERATE_AREA = 1e-6


def centroid(points):
    """The anchor an item is matched on, or None if it has no points.

    For anything enclosing an area this is the AREA centroid, and that is not a
    refinement -- it is what makes matching work at all. The vertex mean depends
    on how a shape was written down rather than on where it is:

      * a ring whose closing vertex repeats the first pulls the mean toward that
        corner. The same 3000x3000 hatch read by two passes, one of which closes
        the ring explicitly, anchored 300 mm apart -- outside the 100 mm match
        radius, so it reconciled as two separate members, each missing from the
        other's stage. Two false findings from one correct hatch.
      * a bulged polyline flattens to many vertices along its arcs and few along
        its straight runs, dragging the mean toward the curved side.

    The area centroid is immune to both: it depends on the shape, not on its
    vertex list. Open paths and degenerate rings (a line, a point, a zero-area
    sliver) have no area centroid, so they keep the vertex mean -- which is
    correct for them and is what they are compared against anyway.

    Z is always the vertex mean: the plan position is what matching uses, and a
    flat drawing has nothing to say about height.
    """
    if not points:
        return None
    count = float(len(points))
    mean_z = sum(p[2] for p in points) / count

    if len(points) >= 3:
        area2 = 0.0        # twice the signed area
        cx = cy = 0.0
        for a, b in zip(points, points[1:] + points[:1]):
            cross = a[0] * b[1] - b[0] * a[1]
            area2 += cross
            cx += (a[0] + b[0]) * cross
            cy += (a[1] + b[1]) * cross
        if abs(area2 / 2.0) > _DEGENERATE_AREA:
            return (cx / (3.0 * area2), cy / (3.0 * area2), mean_z)

    return (sum(p[0] for p in points) / count,
            sum(p[1] for p in points) / count, mean_z)


def bbox(points):
    """(xmin, ymin, zmin, xmax, ymax, zmax), or None if there are no points."""
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def extent(points):
    """(width, depth, height) of the bounding box, or None."""
    box = bbox(points)
    if box is None:
        return None
    return (box[3] - box[0], box[4] - box[1], box[5] - box[2])


def axis_aligned_plan_size(points):
    """(short, long) of the axis-aligned plan bounding box, or None."""
    size = extent(points)
    if size is None:
        return None
    return (min(size[0], size[1]), max(size[0], size[1]))


def plan_size(points):
    """(short_side, long_side) of the member, allowing for its ORIENTATION.

    Ordered rather than (x, y) so a 400x750 column compares equal to a 750x400
    one -- otherwise every column drawn the other way round reads as a different
    size.

    Oriented rather than axis-aligned because an axis-aligned box is not a size:
    a 400x400 column at 45 degrees measures 566x566 inside one, so the audit
    either flags every rotated column in the plan as 166 mm oversized or has to
    stop checking sizes at all. This bit the Revit side visibly -- the reader
    carried a note apologising for it -- but the DXF side had exactly the same
    fault and no note.

    Two candidate orientations are tried: axis-aligned, and aligned to the
    longest edge. For a rectangle at any angle the longest edge IS a side of the
    minimum-area rectangle, so this is EXACT for the shapes it matters
    for -- columns, footings, pad bases -- while staying O(n). A full
    rotating-calipers hull would be exact for arbitrary shapes and quadratic,
    which on a 20,000-item export is not a trade worth making for an
    L-shaped slab whose size is not the number anyone argues about anyway.
    """
    axis_aligned = axis_aligned_plan_size(points)
    if axis_aligned is None:
        return None
    angle = principal_angle_deg(points)
    if angle is None:
        return axis_aligned
    rotated = axis_aligned_plan_size(_rotated(points, -angle))
    if rotated is None:
        return axis_aligned
    # The smaller area is the tighter description of the same shape.
    if rotated[0] * rotated[1] < axis_aligned[0] * axis_aligned[1]:
        return rotated
    return axis_aligned


def _rotated(points, degrees):
    """The points turned about the origin. Plan only; z is carried through."""
    radians = math.radians(degrees)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return [(p[0] * cos_a - p[1] * sin_a,
             p[0] * sin_a + p[1] * cos_a,
             p[2]) for p in points]


def distance(a, b):
    """Straight-line distance between two points; None if either is missing."""
    if a is None or b is None:
        return None
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def plan_distance(a, b):
    """Distance in plan only (ignores z); None if either point is missing.

    The audit matches in plan because a linked DXF is flat while the model it
    produces is not: a column runs floor to floor, so its 3D centroid sits a
    storey height away from the outline that created it and no 3D radius could
    match them.
    """
    if a is None or b is None:
        return None
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def point_to_segment_distance(point, start, end):
    """Distance in plan from a point to a finite segment (not its infinite line).

    Needed because a beam label sits ALONG its beam, often nearer an end than
    the middle. Measuring to the member's centroid asks "is the label near the
    middle of the beam", which for a 6 m beam is the wrong question and answers
    no for most correctly-placed labels.
    """
    ax, ay = start[0], start[1]
    bx, by = end[0], end[1]
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 1e-12:
        return plan_distance(point, start)
    # Projection parameter, clamped to the segment so the answer is never to a
    # point beyond either end.
    t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / span
    t = max(0.0, min(1.0, t))
    return plan_distance(point, (ax + t * dx, ay + t * dy, 0.0))


def path_distance(point, points):
    """Shortest plan distance from a point to a polyline. None if it has none."""
    if not points:
        return None
    if len(points) == 1:
        return plan_distance(point, points[0])
    best = None
    for a, b in zip(points, points[1:]):
        distance = point_to_segment_distance(point, a, b)
        if distance is not None and (best is None or distance < best):
            best = distance
    return best


def path_length(points):
    """Summed segment length along the vertices. 0.0 for fewer than two points."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                           + (a[2] - b[2]) ** 2)
    return total


def polygon_area(points):
    """Absolute shoelace area of the ring in plan. 0.0 for fewer than 3 points.

    Absolute because the audit never cares about winding direction, and a hatch
    boundary arrives in whichever direction the drafter drew it. The ring is
    closed implicitly (last vertex back to first), so both a closed and an
    unclosed vertex list give the same answer.
    """
    if len(points) < 3:
        return 0.0
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2.0


def is_closed(points, tol):
    """True when the path returns to its start within `tol`.

    Used to tell an outline (which can become a member) from an open run of
    strokes (which cannot) -- the distinction cad2bim's `open_path` status turns
    on, reproduced here so the audit can report it independently.
    """
    if len(points) < 3:
        return False
    gap = distance(points[0], points[-1])
    return gap is not None and gap <= tol


def principal_angle_deg(points):
    """Angle of the longest segment, in degrees, folded to [0, 180). None if flat.

    Folded because a member has no direction: a beam drawn left-to-right and the
    same beam drawn right-to-left must not read as 180 degrees of rotation error.
    """
    best = None
    best_length = 0.0
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length > best_length:
            best_length = length
            best = (dx, dy)
    if best is None or best_length <= 0.0:
        return None
    return math.degrees(math.atan2(best[1], best[0])) % 180.0


def angle_delta_deg(a, b):
    """Smallest angle between two folded [0, 180) headings. None if either is None."""
    if a is None or b is None:
        return None
    raw = abs(a - b) % 180.0
    return min(raw, 180.0 - raw)
