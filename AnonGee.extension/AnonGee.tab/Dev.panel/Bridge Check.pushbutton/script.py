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

__version__ = "0.2.0"

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
    """``(headline, detail)`` for one route."""
    url = url_for(route)
    body, how, errors = fetch(url)
    if not body:
        return ("{0}\n  no answer".format(url),
                "{0}\n  {1}".format(url, "\n  ".join(errors)))
    detail = "{0}\n  reached by {1}".format(url, how)
    if errors:
        detail += "\n  tried first: " + "; ".join(errors)
    return "{0}\n  {1}".format(url, body), detail


def main():
    ping_line, ping_detail = describe("ping")
    status_line, status_detail = describe("status")

    from Autodesk.Revit.UI import TaskDialog
    dialog = TaskDialog("AnonGee · Bridge Check")
    dialog.MainInstruction = "The bridge, as Excel would see it"
    dialog.MainContent = "\n\n".join([ping_line, status_line])
    dialog.ExpandedContent = "\n\n".join([
        ping_detail, status_detail,
        "Neither answered? The Routes server is off. pyRevit Settings → "
        "Routes → Routes Server (Beta), then restart Revit. It reports "
        "'listening on http://0.0.0.0:48884' when it is up.",
        "Ping answered and status did not? The server is up and the External "
        "Event marshalling is not — a finding, not a failure, and it belongs "
        "in the report."])
    dialog.Show()


main()
