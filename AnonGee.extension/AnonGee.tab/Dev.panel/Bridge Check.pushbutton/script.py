#! python3
# -*- coding: utf-8 -*-
"""Ask the bridge whether it is there, from inside Revit.

**The first line selects the engine and it is not decoration.** Without it
pyRevit runs this on IronPython 2.7, where the CPython 3 toolkit is not on the
path — and the symptom was a ``NameError`` phrased *"global name 'os' is not
defined"*, Python 2 wording that named the missing import and said nothing about
the missing engine. Every CPython tool in this repository carries it; these two
were written without it.

The bridge's routes are served by pyRevit from **inside this Revit process**
(see ``AnonGee.extension/startup.py``). When a button in Excel gets no answer,
there are five reasons and they look identical from Excel: the Routes server is
off, the startup script did not register, Revit is busy, no document is open, or
something between the two is blocking a local port.

This tool calls the same two URLs Excel calls, from the machine Revit is on, and
shows exactly what comes back. It removes the network from the question, which
is the one thing Excel cannot do for itself.

Read-only. No transaction, no model change, nothing written anywhere.

    /anongee/ping      the server, with no Revit in the question

**``/status`` is deliberately not called from here, and cannot be.** It declares
``uiapp``, so pyRevit runs it as an External Event — which fires only when Revit
is idle. Revit is not idle: it is busy running *this tool*, which would be
blocking on the response. The two wait for each other until every timeout
expires, and a run of 0.5.0 did exactly that and then reported *"the External
Event marshalling is not [up]"* — **which was false**. The marshalling had
already been proved from Excel. The tool was deadlocking itself and blaming the
bridge for it.

A tool inside Revit can never test that route. Excel can, because Excel is not
holding Revit's thread. What this does instead is read the document **directly**
— it is already inside Revit and does not need a round trip to know what is
open.
"""

__title__ = "Bridge\nCheck"
__author__ = "AnonGee"
__doc__ = """Ask the AnonGee Bridge whether it is running.

Probes the port, calls /ping, and reports the open document — the three things
that can be known from inside Revit.

/status is NOT called from here. It runs as an External Event, which fires only
when Revit is idle, and Revit is busy running this tool: the two would wait for
each other until every timeout expired. Test that route from Excel, where
nothing is holding Revit's thread.

If nothing answers, the report says which of three things is wrong — the Routes
server switched off, the startup script failing to register, or the extension
never reloading — and what to do about each.

Read-only. Nothing is written to the model. The report also prints to the
pyRevit console, where it can be selected and pasted."""

__version__ = "0.6.0"

import os
import sys

HOST = "localhost"
PORT = 48884
API = "anongee"

#: The ceiling for anything not otherwise bounded. Nothing this tool calls
#: should come near it — ``/status``, the one route that legitimately waits, is
#: not called from here at all.
TIMEOUT_SECONDS = 20

#: For ``/ping``, which touches no Revit and should answer at once.
PING_TIMEOUT_SECONDS = 5

#: For the TCP probe. A refused connection comes back in microseconds; this is
#: only the ceiling for a port that is being silently dropped.
PROBE_TIMEOUT_SECONDS = 1.0


def url_for(route):
    """The same string the Excel macro builds, from the same three parts."""
    return "http://{0}:{1}/{2}/{3}".format(HOST, PORT, API, route)


def port_open(host=HOST, port=PORT, seconds=PROBE_TIMEOUT_SECONDS):
    """Is anything listening at all? ``(open, note)``. One second, at most.

    Asked **before** any HTTP, and it is the difference between an answer and a
    wait. A run of the previous version took minutes and showed nothing: four
    ways to the wire, tried twice, and ``WebClient.DownloadString`` carries a
    **hundred-second default timeout** that was never set. When nothing is
    listening, none of that is worth doing — a refused TCP connection says so in
    microseconds.
    """
    import socket
    connection = None
    try:
        connection = socket.create_connection((host, port), seconds)
        return True, ""
    except Exception as error:
        return False, "{0}".format(error)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _by_web_client(url, seconds=TIMEOUT_SECONDS):
    """``System.Net.WebClient``. Needs its own assembly reference on .NET 8.

    The first version of this imported it and nothing else, and a real run said
    *Cannot import name WebClient*. On .NET Framework it came in by default; on
    .NET 8 — which Revit 2025 runs on — it lives in its own assembly and has to
    be asked for. That was the whole finding, and it is why this file now tries
    five things and says which one worked.
    """
    import clr
    try:
        clr.AddReference("System.Net.WebClient")
    except Exception:
        pass                                    # already referenced is fine
    from System.Net import WebClient
    return WebClient().DownloadString(url)


def _by_http_client(url, seconds=TIMEOUT_SECONDS):
    """``System.Net.Http.HttpClient`` — the one .NET 8 actually prefers."""
    import clr
    try:
        clr.AddReference("System.Net.Http")
    except Exception:
        pass
    from System.Net.Http import HttpClient
    from System import TimeSpan
    client = HttpClient()
    client.Timeout = TimeSpan.FromSeconds(seconds)
    return client.GetStringAsync(url).Result


def _by_urllib(url, seconds=TIMEOUT_SECONDS):
    """The standard library, which this engine ships only part of.

    A real run said *No module named request*. Kept in the chain because the
    engine may gain it, and because a probe that stops asking stops being a
    probe.
    """
    from urllib.request import urlopen
    return urlopen(url, timeout=seconds).read().decode("utf-8", "replace")


def _by_socket(url, seconds=TIMEOUT_SECONDS):
    """A GET written by hand, over a raw socket.

    The floor. ``socket`` is a built-in extension module rather than a pure
    Python one, so it survives a stdlib that has had ``re`` and ``csv`` taken
    out of it. Thirty lines, no dependencies, and it is the reason this tool
    cannot be left with nothing to try.
    """
    import socket
    rest = url.split("://", 1)[-1]
    hostport, _, path = rest.partition("/")
    host, _, port = hostport.partition(":")
    port = int(port or 80)

    request = ("GET /{0} HTTP/1.1\r\nHost: {1}\r\n"
               "Connection: close\r\n\r\n").format(path, hostport)

    connection = socket.create_connection((host, port), seconds)
    try:
        connection.sendall(request.encode("ascii"))
        chunks = []
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        connection.close()

    text = b"".join(chunks).decode("utf-8", "replace")
    return text.split("\r\n\r\n", 1)[-1]


#: In the order they are tried, and the order is now **by whether the timeout
#: can be bounded**. ``WebClient`` cannot have one set without subclassing it,
#: and its default is a hundred seconds — which is how a diagnostic ended up
#: taking minutes and showing nothing. It goes last.
#:
#: The name still travels with the answer, because *which* of these worked says
#: what the CPython 3 engine can reach the network with, and every later part
#: of the bridge that has to make a request needs to know.
WAYS = (("System.Net.Http.HttpClient", _by_http_client),
        ("raw socket", _by_socket),
        ("urllib.request", _by_urllib),
        ("System.Net.WebClient (unbounded timeout)", _by_web_client))


def fetch(url, seconds=TIMEOUT_SECONDS):
    """``(body, how, errors)``. Never raises, and never waits long.

    Every way is tried and the failures are all kept. A chain that reports only
    the last error tells you the floor gave way and not that the rungs above it
    did — and on this engine the interesting part is which rungs are missing.
    """
    errors = []
    for name, way in WAYS:
        try:
            body = way(url, seconds)
            if body:
                return body, name, errors
            errors.append("{0}: empty response".format(name))
        except Exception as error:
            errors.append("{0}: {1}".format(name, error))
    return "", "", errors


def describe(route, seconds=TIMEOUT_SECONDS):
    """``(headline, detail)`` for one route.

    **The reason goes in the headline, not the detail.** A run reported "no
    answer" twice with the cause folded away behind *See details*, which nobody
    expands — so the tool built to explain a failure explained nothing, for the
    second release running.
    """
    url = url_for(route)
    body, how, errors = fetch(url, seconds)
    if not body:
        first = errors[0] if errors else "nothing to say"
        return ("{0}\n  no answer — {1}".format(url, first),
                "{0}\n  {1}".format(url, "\n  ".join(errors)))
    detail = "{0}\n  reached by {1}".format(url, how)
    if errors:
        detail += "\n  tried first: " + "; ".join(errors)
    return "{0}\n  {1}".format(url, body), detail


# ---------------------------------------------------------------------------
# The startup record
# ---------------------------------------------------------------------------
# When nothing answers there are three causes and they look identical: the
# Routes server is off, the startup script failed to register, or the extension
# never reloaded. They need different fixes. ``startup.py`` writes a record on
# every load precisely because when it is the guilty one there is no route left
# to ask.

STARTUP_RECORD = "startup.json"
ENV_HOME = "ANONGEE_BRIDGE_HOME"
APPDATA_PARTS = ("AnonGee", "bridge")
HOME_PARTS = (".anongee", "bridge")


def bridge_home():
    """Same three rules as ``startup.py`` and ``bridge/jobs.py``."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, *APPDATA_PARTS)
    return os.path.join(os.path.expanduser("~"), *HOME_PARTS)


def startup_record():
    """``(lines, loaded)`` — what the startup script did, and when."""
    path = os.path.join(bridge_home(), STARTUP_RECORD)
    if not os.path.exists(path):
        return ([
            "No startup record at {0}".format(path),
            "  The startup script has never run in this pyRevit session.",
            "  Reload pyRevit (pyRevit tab → Reload) or restart Revit.",
        ], "")

    try:
        handle = open(path, "r")
        try:
            text = handle.read()
        finally:
            handle.close()
    except Exception as error:
        return (["Could not read {0}: {1}".format(path, error)], "")

    loaded = _value(text, "loaded")
    routes = _value(text, "registered")
    lines = [
        "Startup record: {0}".format(path),
        "  loaded    {0}".format(loaded or "?"),
        "  engine    {0}".format(_value(text, "implementation") or "?"),
        "  routes    {0}".format("yes" if routes == "true" else "NONE"),
    ]
    note = _value(text, "note")
    if note:
        lines.append("  note      {0}".format(note))
    return lines, loaded


def _value(text, key):
    """One value out of the record. Not a JSON parser — see the note below.

    Four fields out of a file this file's sibling wrote is not worth importing
    a parser for, and the CPython 3 engine's standard library has already
    surprised us twice about what it does and does not ship.
    """
    marker = '"{0}"'.format(key)
    at = text.find(marker)
    if at < 0:
        return ""
    colon = text.find(":", at + len(marker))
    if colon < 0:
        return ""
    rest = text[colon + 1:].strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        return rest[1:end] if end > 0 else ""
    for stop in (",", "\n", "}"):
        end = rest.find(stop)
        if end > 0:
            return rest[:end].strip()
    return rest.strip()


def document():
    """What this Revit session has open, read directly. ``[lines]``.

    No round trip: this code is already inside Revit, on Revit's own thread. It
    is what ``/status`` would have said, obtained the one way that cannot
    deadlock.
    """
    try:
        uiapp = __revit__                                     # noqa: F821
    except Exception as error:
        return ["Revit: could not be reached from here - {0}".format(error)]

    lines = []
    try:
        lines.append("Revit {0} {1}".format(
            uiapp.Application.VersionName, uiapp.Application.VersionBuild))
    except Exception as error:
        lines.append("Revit version could not be read: {0}".format(error))

    try:
        uidoc = uiapp.ActiveUIDocument
        if uidoc is None:
            lines.append("Document: none open")
        else:
            doc = uidoc.Document
            lines.append("Document: {0}".format(doc.Title))
            lines.append("  {0}".format(doc.PathName or "(unsaved)"))
    except Exception as error:
        lines.append("Document could not be read: {0}".format(error))
    return lines


def report():
    """The whole diagnosis as lines. Ordered so the answer comes first."""
    lines = ["AnonGee Bridge Check {0}".format(__version__),
             "this tool is on {0}".format(sys.version.split()[0]
                                          if sys.version else "?"),
             "expecting http://{0}:{1}/{2}/".format(HOST, PORT, API), ""]

    listening, why = port_open()
    record, loaded = startup_record()

    if not listening:
        lines.append("NOTHING IS LISTENING on {0}:{1}".format(HOST, PORT))
        lines.append("  {0}".format(why))
        lines.append("")
        lines.extend(record)
        lines.append("")
        if loaded:
            lines.append(
                "The startup script ran at {0}, so the extension is loaded "
                "and the routes exist. Switch the server on: pyRevit Settings "
                "-> Routes -> Routes Server (Beta), then restart Revit."
                .format(loaded))
        else:
            lines.append(
                "The startup script has not run in this session, so there is "
                "nothing to listen. pyRevit tab -> Reload, or restart Revit, "
                "then run this again.")
        return lines, False

    lines.append("The port is open. Asking /ping.")
    lines.append("")
    ping_line, ping_detail = describe("ping", PING_TIMEOUT_SECONDS)
    lines.extend([ping_line, ""])
    lines.extend(document())
    lines.append("")
    lines.extend(record)
    lines.append("")

    answered = "no answer" not in ping_line
    if answered:
        lines.append("The bridge is up.")
    else:
        lines.append(
            "Something is on the port but /ping does not answer. Either "
            "another program has {0}, or the routes did not register - the "
            "startup record above says which.".format(PORT))

    lines.append("")
    lines.append(
        "/status is not called from here and cannot be: it runs as an "
        "External Event, which fires only when Revit is idle, and Revit is "
        "busy running this tool. Test it from Excel.")

    lines.extend(["", "--- detail ---", ping_detail])
    return lines, answered


def main():
    """Say something, always.

    A run of the previous version showed nothing at all and left an empty
    console. **A diagnostic that can produce no output is broken by
    definition**, so everything below is wrapped and the failure becomes the
    report.
    """
    try:
        lines, _ok = report()
    except Exception as error:
        lines = ["Bridge Check itself failed: {0}".format(error),
                 "",
                 "That is a bug in this tool, not in the bridge. The bridge "
                 "may well be fine."]

    text = "\n".join(lines)

    # To the pyRevit console as well as the dialog, and this is the important
    # half: console output can be selected and pasted. A dialog has to be
    # retyped or screenshotted, which is how the last three rounds of findings
    # arrived - and a screenshot of a collapsed panel is how one of them said
    # nothing at all.
    print(text)

    try:
        from Autodesk.Revit.UI import TaskDialog
        dialog = TaskDialog("AnonGee \u00b7 Bridge Check")
        dialog.MainInstruction = "The bridge, as Excel would see it"
        dialog.MainContent = "\n".join(lines[:14])
        dialog.ExpandedContent = text
        dialog.Show()
    except Exception:
        pass                       # the console already has all of it


main()
