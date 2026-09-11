# -*- coding: utf-8 -*-
"""A uniform grid index, because the honest version of "nearest" is too slow.

Rule M005 asks, for every size label, how far the nearest member is. Done
directly that is texts x records, and on the corpus's largest drawing that is
tens of thousands times hundreds of thousands -- a QA tool that takes longer
than the conversion it is checking will not be run.

A uniform grid answers it in one pass. Cell size is the SEARCH RADIUS, so
anything within the radius is guaranteed to sit in the queried cell or one of
its eight neighbours, and nine cell lookups replace the whole corpus. No
balancing, no tree, no dependency -- for points spread over a building plan a
uniform grid is not a compromise, it is the right structure.

Distances and coordinates are in whatever unit the caller puts in; the class
never converts. Callers work in millimetres.
"""

import math

__version__ = "1.0.0"


class GridIndex(object):
    """Points bucketed into square cells of side `cell`, for radius queries."""

    def __init__(self, cell):
        if cell <= 0:
            raise ValueError("cell size must be positive, got {0!r}".format(cell))
        self.cell = float(cell)
        self._buckets = {}
        self._count = 0

    def __len__(self):
        return self._count

    def add(self, x, y, payload=None):
        """Index one point. `payload` comes back from :meth:`nearest`."""
        self._buckets.setdefault(self._key(x, y), []).append((x, y, payload))
        self._count += 1

    def extend(self, points):
        """Index an iterable of (x, y) or (x, y, payload)."""
        for item in points:
            if len(item) >= 3:
                self.add(item[0], item[1], item[2])
            else:
                self.add(item[0], item[1])
        return self

    def nearest(self, x, y, radius=None):
        """``(distance, payload)`` for the closest indexed point, or None.

        Searches the query cell and its eight neighbours, which covers every
        point within one cell width. `radius` beyond the cell size would need a
        wider ring and is refused rather than silently under-reporting -- a
        nearest-neighbour query that quietly misses neighbours is worse than
        one that says it cannot answer.
        """
        if radius is not None and radius > self.cell:
            raise ValueError(
                "radius {0} exceeds cell size {1}; build the index with "
                "cell=radius".format(radius, self.cell))
        cx, cy = self._key(x, y)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py, payload in self._buckets.get((cx + dx, cy + dy), ()):
                    distance = math.hypot(px - x, py - y)
                    if radius is not None and distance > radius:
                        continue
                    if best is None or distance < best[0]:
                        best = (distance, payload)
        return best

    def _key(self, x, y):
        return (int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))


def centroid(points):
    """The mean of a point run, or None when it carries none.

    The mean rather than the polygon centroid on purpose: a QA check asks
    "roughly where is this thing", and the mean is stable on an OPEN run, which
    a polygon centroid is not -- and open runs are exactly what this tool
    spends its time looking at.
    """
    if not points:
        return None
    total_x = total_y = 0.0
    for point in points:
        total_x += point[0]
        total_y += point[1]
    count = float(len(points))
    return (total_x / count, total_y / count)
