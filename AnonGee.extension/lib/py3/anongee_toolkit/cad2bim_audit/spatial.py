# -*- coding: utf-8 -*-
"""A uniform grid, so nothing here is ever quadratic.

Every pairwise question the audit asks -- which items are duplicates, which
member does this label size, which group does this item join -- is "what is near
this point". Answered by scanning, each is O(n*m): on the 19,896-item export the
matcher alone would be tens of millions of distance tests.

A grid keyed at the search radius makes them near-linear, because only the nine
cells around a point can hold a match. Anything further away is outside the
radius by construction.

`add_span` exists for members with extent. A beam filed only where its midpoint
falls is invisible to a probe at its far end, however correct the distance test
afterwards -- which is how correctly-placed labels on 6 m beams came to be
reported as sizing nothing.

Revit-free, and deliberately free of any notion of what it is indexing.
"""

from . import geometry


class Grid(object):
    """Payloads filed by cell, retrievable by proximity."""

    def __init__(self, cell):
        # A zero or negative cell would put everything in one bucket and quietly
        # restore the quadratic behaviour this exists to avoid.
        self.cell = float(cell) if cell and cell > 0 else 1.0
        self.buckets = {}

    def key(self, point):
        return (int(point[0] // self.cell), int(point[1] // self.cell))

    def add(self, point, payload):
        self.buckets.setdefault(self.key(point), []).append(payload)

    def add_span(self, points, payload):
        """File a payload into every cell its path crosses.

        Sampled at half the cell size so no cell along the run is skipped.
        """
        if not points:
            return
        if len(points) == 1:
            self.add(points[0], payload)
            return
        step = self.cell / 2.0
        keys = set()
        for a, b in zip(points, points[1:]):
            length = geometry.plan_distance(a, b) or 0.0
            steps = max(1, int(length / step) + 1)
            for index in range(steps + 1):
                t = float(index) / steps
                keys.add(self.key((a[0] + (b[0] - a[0]) * t,
                                   a[1] + (b[1] - a[1]) * t)))
        for cell_key in keys:
            self.buckets.setdefault(cell_key, []).append(payload)

    def near(self, point):
        """Every payload in the nine cells around `point`. May repeat a payload
        filed across several cells -- callers that care deduplicate by identity."""
        cx, cy = self.key(point)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found.extend(self.buckets.get((cx + dx, cy + dy), ()))
        return found

    def move(self, old_point, new_point, payload):
        """Re-file a payload whose position drifted into a different cell."""
        old_key, new_key = self.key(old_point), self.key(new_point)
        if old_key == new_key:
            return
        bucket = self.buckets.get(old_key)
        if bucket and payload in bucket:
            bucket.remove(payload)
        self.buckets.setdefault(new_key, []).append(payload)
