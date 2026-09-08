#! python3
# -*- coding: utf-8 -*-
"""Ask the bridge whether it is there, from inside Revit.

The bridge routes are served by pyRevit from inside this Revit process. This
read-only diagnostic probes the port, calls ``/ping`` and reads the current Revit
document directly. It deliberately does not call ``/status`` from inside Revit:
that route runs as an External Event and would wait for Revit to become idle
while this command is itself holding Revit's thread.
"""

__title__ = "Bridge\nCheck"
__author__ = "AnonGee"
__doc__ = """Ask the AnonGee Bridge whether it is running.

Probes the port, calls /ping, and reports the open document. /status is not
called from here because it needs Revit to become idle; test that route from
Excel instead.

Bridge runtime state lives under
%LOCALAPPDATA%\\Zxaidman\\AnonGee\\bridge by default. ANONGEE_BRIDGE_HOME
remains the explicit override. %APPDATA%\\AnonGee\\bridge is retained only as
the legacy/fallback location.

Read-only. Nothing is written to the model. The report also prints to the
pyRevit console, where it can be selected and pasted."""

__version__ = "0.6.1"

import os
import sys

HOST = "localhost"
PORT = 48884
API = "anongee"
TIMEOUT_SECONDS = 20
PING_TIMEOUT_SECONDS = 5
PROBE_TIMEOUT_SECONDS = 1.0


def url_for(route):
    return "http://{0}:{1}/{2}/{3}".format(HOST, PORT, API, route)


def port_open(host=HOST, port=PORT, seconds=PROBE_TIMEOUT_SECONDS):
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
    import clr
    try:
        clr.AddReference("System.Net.WebClient")
    except Exception:
        pass
    from System.Net import WebClient
    return WebClient().DownloadString(url)


def _by_http_client(url, seconds=TIMEOUT_SECONDS):
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
    from urllib.request import urlopen
    return urlopen(url, timeout=seconds).read().decode("utf-8", "replace")


def _by_socket(url, seconds=TIMEOUT_SECONDS):
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


WAYS = (("System.Net.Http.HttpClient", _by_http_client),
        ("raw socket", _by_socket),
        ("urllib.request", _by_urllib),
        ("System.Net.WebClient (unbounded timeout)", _by_web_client))


def fetch(url, seconds=TIMEOUT_SECONDS):
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


STARTUP_RECORD = "startup.json"
ENV_HOME = "ANONGEE_BRIDGE_HOME"
LOCALAPPDATA_PARTS = ("Zxaidman", "AnonGee", "bridge")
APPDATA_PARTS = ("AnonGee", "bridge")
HOME_PARTS = (".anongee", "bridge")


def bridge_home():
    """Same path contract as startup.py and bridge/jobs.py."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return os.path.join(localappdata, *LOCALAPPDATA_PARTS)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, *APPDATA_PARTS)
    return os.path.join(os.path.expanduser("~"), *HOME_PARTS)


def startup_record():
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
    lines = ["AnonGee Bridge Check {0}".format(__version__),
             "this tool is on {0}".format(sys.version.split()[0]
                                          if sys.version else "?"),
             "bridge home: {0}".format(bridge_home()),
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
    try:
        lines, _ok = report()
    except Exception as error:
        lines = ["Bridge Check itself failed: {0}".format(error),
                 "",
                 "That is a bug in this tool, not in the bridge. The bridge "
                 "may well be fine."]

    text = "\n".join(lines)
    print(text)
    try:
        from Autodesk.Revit.UI import TaskDialog
        dialog = TaskDialog("AnonGee \u00b7 Bridge Check")
        dialog.MainInstruction = "The bridge, as Excel would see it"
        dialog.MainContent = "\n".join(lines[:14])
        dialog.ExpandedContent = text
        dialog.Show()
    except Exception:
        pass


main()
