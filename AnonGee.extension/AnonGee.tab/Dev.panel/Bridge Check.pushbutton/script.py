# -*- coding: utf-8 -*-
"""Ask the bridge whether it is there, from inside Revit.

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
    /anongee/status    the model, through an External Event

**If ping answers and status does not**, the server is fine and the External
Event marshalling is not — which is the whole reason there are two routes rather
than one.
"""

__title__ = "Bridge\nCheck"
__author__ = "AnonGee"
__doc__ = """Ask the AnonGee Bridge whether it is running.

Calls the two routes pyRevit serves from inside this Revit session — the same
URLs an Excel button calls — and shows what comes back.

  ping    the Routes server, answered even while Revit is busy
  status  the open model, answered only once Revit is idle

If ping answers and status does not, the server is up and the External Event
marshalling is not. If neither answers, the Routes server is off: turn it on in
pyRevit Settings and restart Revit.

Read-only. Nothing is written to the model."""

__version__ = "0.3.0"

HOST = "localhost"
PORT = 48884
API = "anongee"

#: Long enough for a busy Revit, short enough that the dialog is not a hang.
TIMEOUT_SECONDS = 15


def url_for(route):
    """The same string the Excel macro builds, from the same three parts."""
    return "http://{0}:{1}/{2}/{3}".format(HOST, PORT, API, route)


def _by_web_client(url):
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


def _by_http_client(url):
    """``System.Net.Http.HttpClient`` — the one .NET 8 actually prefers."""
    import clr
    try:
        clr.AddReference("System.Net.Http")
    except Exception:
        pass
    from System.Net.Http import HttpClient
    from System import TimeSpan
    client = HttpClient()
    client.Timeout = TimeSpan.FromSeconds(TIMEOUT_SECONDS)
    return client.GetStringAsync(url).Result


def _by_urllib(url):
    """The standard library, which this engine ships only part of.

    A real run said *No module named request*. Kept in the chain because the
    engine may gain it, and because a probe that stops asking stops being a
    probe.
    """
    from urllib.request import urlopen
    return urlopen(url, timeout=TIMEOUT_SECONDS).read().decode("utf-8", "replace")


def _by_socket(url):
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

    connection = socket.create_connection((host, port), TIMEOUT_SECONDS)
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


#: In the order they are tried. The name travels with the answer, because
#: *which* of these worked is itself a finding — it says what the CPython 3
#: engine can reach the network with, and every later part of the bridge that
#: has to make a request needs to know.
WAYS = (("System.Net.WebClient", _by_web_client),
        ("System.Net.Http.HttpClient", _by_http_client),
        ("urllib.request", _by_urllib),
        ("raw socket", _by_socket))


def fetch(url):
    """``(body, how, errors)``. Never raises.

    Every way is tried and the failures are all kept. A chain that reports only
    the last error tells you the floor gave way and not that the four rungs
    above it did — and on this engine the interesting part is which rungs are
    missing.
    """
    errors = []
    for name, way in WAYS:
        try:
            body = way(url)
            if body:
                return body, name, errors
            errors.append("{0}: empty response".format(name))
        except Exception as error:
            errors.append("{0}: {1}".format(name, error))
    return "", "", errors


def describe(route):
    """``(headline, detail)`` for one route.

    **The reason goes in the headline, not the detail.** A run reported "no
    answer" twice with the cause folded away behind *See details*, which nobody
    expands — so the tool built to explain a failure explained nothing, for the
    second release running.
    """
    url = url_for(route)
    body, how, errors = fetch(url)
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


def main():
    ping_line, ping_detail = describe("ping")
    status_line, status_detail = describe("status")
    record, loaded = startup_record()

    answered = "no answer" not in ping_line

    if answered:
        verdict = "The bridge is up."
    elif loaded:
        verdict = ("The startup script ran, so the extension is loaded. "
                   "Nothing is listening — switch the Routes server on: "
                   "pyRevit Settings → Routes → Routes Server (Beta), then "
                   "restart Revit.")
    else:
        verdict = ("The startup script has not run in this session, so there "
                   "is nothing to listen. Reload pyRevit or restart Revit.")

    from Autodesk.Revit.UI import TaskDialog
    dialog = TaskDialog("AnonGee · Bridge Check")
    dialog.MainInstruction = "The bridge, as Excel would see it"
    dialog.MainContent = "\n\n".join(
        [ping_line, status_line, "\n".join(record), verdict])
    dialog.ExpandedContent = "\n\n".join([
        ping_detail, status_detail,
        "Ping answered and status did not? The server is up and the External "
        "Event marshalling is not — a finding, not a failure, and it belongs "
        "in the report."])
    dialog.Show()


main()
