# -*- coding: utf-8 -*-
"""cad2bim_audit -- what the drawing had, what Revit saw, what got built.

cad2bim's own JSON export answers "what did the run decide". It cannot answer
the question you actually ask when something is wrong, which is *where* it went
wrong -- because by the time that JSON is written, everything the run discarded
is already gone. A column absent from the model looks identical whether the DXF
never had it, the reader dropped it, Revit's import mangled it, or the builder
declined to place it.

So this package reads the same job FOUR times, independently, and puts the four
answers side by side:

    A  the DXF, through ezdxf                      what the drawing HAS
    B  the same DXF linked into Revit              what Revit SEES
    C  the Revit model                             what got BUILT
    D  a cad2bim run's JSON (optional)             what the run INTENDED

A missing member is then attributable to a stage rather than to the pipeline as
a whole: present in A, absent in B is Revit's import; present in B, absent in D
is classification or a builder gate; present in D, absent in C is Revit refusing
the creation.

Two passes per source
---------------------
Each of A and B is read twice: once by an independent full-fidelity walker in
this package, once through cad2bim's own reader. The delta between those two
columns is precisely what cad2bim's readers throw away -- which is invisible to
any report built on the readers alone. Two known gaps it exists to surface:
`geometry_reader` ignores solids, meshes and points outright, and `dxf_reader`
swallows every malformed entity in a bare `except: continue`.

Read-only with respect to cad2bim
---------------------------------
This package IMPORTS cad2bim (config, classify.layers, readers, model) and never
modifies it. Nothing here can change what cad2bim builds; a bug in this package
produces a wrong report, never a wrong model. The one write it performs against
Revit is optionally linking the DXF the user picked, in its own transaction --
the same call cad2bim makes, and skipped entirely when an existing link is used.

Layering (which modules need Revit)
-----------------------------------
Only `readers/revit_geometry.py`, `readers/revit_elements.py` and the pushbutton
import Autodesk.Revit. Everything else -- the item model, the coordinate space,
the matcher, the findings, the sheet model -- is plain Python and is tested
outside Revit through `tests/_loader.py`.
"""

__version__ = "0.1.0"   # Walking skeleton: four stages, matcher, workbook, sidecar.
