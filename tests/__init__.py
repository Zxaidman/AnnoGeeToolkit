# -*- coding: utf-8 -*-
"""Makes ``tests`` a package, so the whole suite runs from one command.

Until this file existed every test file ran on its own::

    python3 tests/test_repo_docs.py

and ``python3 -m unittest discover -s tests -t .`` failed outright with
*"Start directory is not importable"*. Sixteen files, sixteen invocations, and
nothing that ran them all — so "the suite is green" was a claim nobody could
check in one step, which is exactly the kind of gap this repository's own
documentation tests exist to close.

With this file::

    python3 -m unittest discover -s tests -t .        # everything
    python3 -m unittest tests.test_repo_docs -v       # one module
    python3 tests/test_repo_docs.py                   # still works, unchanged

Running a file directly still works because every test module computes its own
``_ROOT`` from ``__file__`` and inserts what it needs onto ``sys.path`` itself;
none of them rely on being imported as ``tests.something``.

Deliberately empty otherwise. ``_rc_loader`` is imported by path, not through
this package, and putting anything importable here would run it sixteen times
for no reason.
"""
