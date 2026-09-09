# -*- coding: utf-8 -*-
"""Generate the audit's fixture DXF: one drawing containing every known gap.

Run: python3 make_audit_plan.py [out.dxf]

The fixture is deliberately small and deliberately nasty. Each feature exists to
pin one behaviour the raw reader claims, so a regression shows up as a named
test failure rather than as a count that drifted:

  * two plain columns and a beam           -- the baseline that must survive
  * a column polyline with BULGES          -- straight chords in cad2bim's reader
  * a hatch with an island + a textbox path -- islands dropped by cad2bim
  * a hatch built from an ARC EDGE path    -- centre-as-vertex bug in cad2bim
  * a DIMENSION, a SOLID and an XLINE      -- types cad2bim drops entirely
  * a block nested five deep               -- past cad2bim's depth limit of 3
  * an empty TEXT                          -- dropped by both, and that is correct
"""

import sys

import ezdxf
from ezdxf.enums import TextEntityAlignment


def build(path):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4          # millimetres
    msp = doc.modelspace()

    for name in ("S-COLS", "S-BEAM", "S-GRID", "S-FND", "S-TEXT", "S-ANNO"):
        doc.layers.add(name)

    # --- baseline: two rectangular columns, 400x400 and 600x400 -------------
    _rect(msp, 0, 0, 400, 400, "S-COLS")
    _rect(msp, 5000, 0, 600, 400, "S-COLS")

    # --- a beam between them, as a pair of parallel lines -------------------
    msp.add_line((400, 150), (5000, 150), dxfattribs={"layer": "S-BEAM"})
    msp.add_line((400, 250), (5000, 250), dxfattribs={"layer": "S-BEAM"})

    # --- a grid line --------------------------------------------------------
    msp.add_line((-1000, 200), (7000, 200), dxfattribs={"layer": "S-GRID"})

    # --- size labels --------------------------------------------------------
    msp.add_text("C1 400x400", dxfattribs={"layer": "S-TEXT", "height": 100}
                 ).set_placement((200, 600), align=TextEntityAlignment.CENTER)
    msp.add_text("C2 600x400", dxfattribs={"layer": "S-TEXT", "height": 100}
                 ).set_placement((5300, 600), align=TextEntityAlignment.CENTER)
    # Empty text: both readers drop it, and the report must call that expected.
    msp.add_text("   ", dxfattribs={"layer": "S-TEXT", "height": 100}
                 ).set_placement((0, 900))

    # --- a column whose outline has BULGES (rounded corners) ----------------
    # get_points("xy") reads these four vertices as a straight-sided square;
    # the true outline is a rounded rectangle.
    bulged = msp.add_lwpolyline(
        [(10000, 0, 0, 0, 0.4), (10400, 0, 0, 0, 0.4),
         (10400, 400, 0, 0, 0.4), (10000, 400, 0, 0, 0.4)],
        format="xyseb", dxfattribs={"layer": "S-COLS"})
    bulged.close(True)

    # --- a hatch with an island and a textbox path --------------------------
    hatch = msp.add_hatch(color=7, dxfattribs={"layer": "S-FND"})
    hatch.set_pattern_fill("ANSI31", scale=10)
    hatch.paths.add_polyline_path(
        [(0, 3000), (3000, 3000), (3000, 6000), (0, 6000)], is_closed=True, flags=1)
    hatch.paths.add_polyline_path(          # island: a hole in the footing
        [(1000, 4000), (2000, 4000), (2000, 5000), (1000, 5000)],
        is_closed=True, flags=16)
    hatch.paths.add_polyline_path(          # textbox: hatch clipped around a label
        [(200, 3200), (900, 3200), (900, 3400), (200, 3400)],
        is_closed=True, flags=8)

    # --- a hatch whose boundary is an EDGE path with an ARC ------------------
    # cad2bim's _boundary_points takes the arc's CENTRE as a vertex here.
    edge_hatch = msp.add_hatch(color=5, dxfattribs={"layer": "S-FND"})
    edge_hatch.set_solid_fill()
    edge_path = edge_hatch.paths.add_edge_path(flags=1)
    edge_path.add_line((6000, 3000), (9000, 3000))
    edge_path.add_arc((7500, 3000), radius=1500, start_angle=0, end_angle=180)

    # --- types cad2bim's reader does not handle at all ----------------------
    msp.add_linear_dim(base=(0, -800), p1=(0, 0), p2=(5600, 0),
                       dxfattribs={"layer": "S-ANNO"}).render()
    msp.add_solid([(12000, 0), (12400, 0), (12000, 400), (12400, 400)],
                  dxfattribs={"layer": "S-COLS"})
    msp.add_xline((0, -2000), (1, 0), dxfattribs={"layer": "S-ANNO"})

    # --- a block nested five deep -------------------------------------------
    # Level 5 sits past cad2bim's depth limit of 3, so its square is invisible
    # to that reader while being present in the drawing.
    inner = doc.blocks.new("LEVEL5")
    _rect(inner, 0, 0, 300, 300, "S-COLS")
    previous = "LEVEL5"
    for level in (4, 3, 2, 1):
        name = "LEVEL{0}".format(level)
        block = doc.blocks.new(name)
        block.add_blockref(previous, (0, 0))
        previous = name
    msp.add_blockref("LEVEL1", (14000, 0), dxfattribs={"layer": "S-COLS"})

    # --- faults the finer checks exist to catch ----------------------------
    # All placed beyond x=20000 so they cannot disturb the reader-gap
    # assertions, which select the baseline geometry by position.
    for layer in ("S-JUNK",):
        doc.layers.add(layer)

    # drawn twice, exactly on top of itself
    _rect(msp, 20000, 0, 400, 400, "S-COLS")
    _rect(msp, 20000, 0, 400, 400, "S-COLS")

    # an outline left open at a junction cut: never becomes a member
    msp.add_lwpolyline([(22000, 0), (22400, 0), (22400, 400),
                        (22000, 400), (22000, 120)],
                       dxfattribs={"layer": "S-COLS"})

    # stray Z in a plan drawing
    msp.add_line((24000, 0, 0), (25000, 0, 250), dxfattribs={"layer": "S-JUNK"})

    # zero-length line: occupies no space, costs every pass time
    msp.add_line((26000, 0), (26000.1, 0), dxfattribs={"layer": "S-JUNK"})

    # C1 is already 400x400 beside the first column; here it is 300x300, and
    # this one sizes nothing at all
    msp.add_text("C1 300x300", dxfattribs={"layer": "S-TEXT", "height": 100}
                 ).set_placement((30000, 0), align=TextEntityAlignment.CENTER)

    doc.saveas(path)
    return path


def _rect(layout, x, y, width, height, layer):
    poly = layout.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        dxfattribs={"layer": layer})
    poly.close(True)
    return poly


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "audit_plan.dxf"
    print("wrote", build(target))
