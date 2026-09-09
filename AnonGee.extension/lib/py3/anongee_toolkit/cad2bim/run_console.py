# -*- coding: utf-8 -*-
"""The run's voice: a deferred console and the two progress bars.

DEFERRED OUTPUT. Printing is what opens pyRevit's console window, and a clean
run should not open one at all -- the user asked for that explicitly. So every
line the run produces is buffered and only REVEALED when something goes wrong,
at which point the whole log comes out at once: phase counts, per-member notes,
the lot. `_OUT.finish()` ends a good run in silence; `_OUT.fail()` flushes.

TWO BARS, NOT ONE. Linking and reading the CAD happens BEFORE the dialog opens,
so a single bar sat at whatever percent the read had reached while the user
filled the dialog in, and then looked like it RESET when the build began. The
read bar closes when the dialog opens; the build bar opens when Run is pressed.
A multi-storey run reports one continuous 0-100 across every storey rather than
restarting per floor -- `_storey_span` tells the bar which storey of how many is
building, and the step count is offset into that.

Names keep their leading underscore because this is a pure move out of the
pushbutton: every call site reads exactly as it did.
"""

try:
    from anongee_toolkit.ui.progressbar import ProgressBar as _CpyProgressBar
except Exception:
    _CpyProgressBar = None


_REAL_PRINT = print   # the genuine print; only the buffer uses it


class _DeferredOut(object):
    def __init__(self):
        self._buf = []
        self.live = False
        self.failed = False
        self.empty = []

    def say(self, msg=""):
        if self.live:
            _REAL_PRINT(msg)
        else:
            self._buf.append(msg)

    def fail(self):
        """Mark the run as failed: the log is shown when it finishes."""
        self.failed = True

    def flush(self):
        for msg in self._buf:
            _REAL_PRINT(msg)
        self._buf = []
        self.live = True

    def finish(self, outcomes=None):
        """Reveal the log only when the run failed; stay silent otherwise.

        An outcome with errors, a rollback, or a category that produced nothing
        while it was asked for all count as failure -- those are exactly the
        runs where the console is worth opening.

        THE THIRD OF THOSE WAS ONLY EVER IN THIS DOCSTRING. The code checked
        errors and rollbacks and nothing else, so a category that built not one
        element ended the run in silence -- and the owner's test17 built **zero
        slabs on all sixteen storeys**, reported 0 errors and 0 skips, and said
        nothing at all. He found it by looking at the model.

        An outcome only exists when the user ticked that category (`script.py`
        builds the dict behind `if selections["create_slabs"]` and its
        siblings), so "an outcome that created nothing" IS "asked for and got
        nothing", with no guessing about intent. Zero created with zero skipped
        and zero errors is the strongest form of it: the pass did not even
        find anything to try, which is a fault upstream of the builder --
        almost always a layer that reached it unmapped.
        """
        self.empty = []
        pending = [(name, value) for name, value in (outcomes or {}).items()]
        while pending:                      # per-storey runs nest one level
            name, outcome = pending.pop()
            if not isinstance(outcome, dict):
                continue
            if outcome.get("errors") or outcome.get("rolled_back"):
                self.failed = True
            if _built_nothing(outcome):
                self.failed = True
                self.empty.append(name)
            pending.extend((key, value) for key, value in outcome.items()
                           if isinstance(value, dict))
        if self.empty:
            self.say("")
            self.say("NOTHING WAS BUILT for: {0}. The console is open because "
                     "of it -- a category that was asked for and produced no "
                     "element is a failed run, whatever the error count says. "
                     "The usual cause is a layer that reached the builder "
                     "unmapped: check the layer table against the counts above."
                     .format(", ".join(sorted(set(self.empty)))))
        if self.failed:
            self.flush()
        else:
            self._buf = []


def _built_nothing(outcome):
    """True when a requested category produced no element at all.

    Only an outcome that COUNTS creations is judged: `created` is the key every
    builder reports and nothing else has it, so a nested detail dict or a
    materials tally is never mistaken for a category that failed.

    Zero created is the whole test. A pass that skipped things tried and said
    why; a pass that created nothing did not put one element in the model, and
    that is what the user is looking at when they say it did not work.
    """
    if "created" not in outcome:
        return False
    try:
        return int(outcome.get("created") or 0) <= 0
    except (TypeError, ValueError):
        return False


_OUT = _DeferredOut()


def _say(msg=""):
    _OUT.say(msg)


def _say_each(prefix, messages):
    """Say each DISTINCT message once, with a count when it repeated.

    A skip list is one message per skipped thing, and on a big drawing that is
    the same sentence hundreds of times over. test17 printed

        step: a fold region of 0.9 m2 sits inside no outline: nothing to step

    roughly two hundred times in a row, burying the twelve lines around it that
    said something. Counting the repeats says exactly as much in one line.

    First-appearance order is kept: the console is read top to bottom as the
    run's story, and sorting it by frequency would scramble that.
    """
    seen, order = {}, []
    for message in messages or []:
        text = str(message)
        if text not in seen:
            order.append(text)
            seen[text] = 0
        seen[text] += 1
    for text in order:
        times = seen[text]
        _say("{0}{1}{2}".format(
            prefix, text, "" if times == 1 else "  [x{0}]".format(times)))


# The mark an error line carries. It is TEXT, not markup: see `_say_error`.
ERROR_MARK = "!! "


def _say_error(msg=""):
    """An ERROR line, marked so it stands apart from the notes around it.

    THIS PRINTED HTML AND THE HTML DID NOT RENDER. The belief was that pyRevit's
    output window is an HTML view and colours markup printed into it, so an
    error was wrapped in a red-and-bold `<span>`. Under the CPython3 engine it
    is not: the owner's console shows the tag itself, so every error line read

        <span style="color:#c00000;font-weight:bold"> slab: ... DECLINED ...</span>

    -- the tag competing for attention with the sentence it was supposed to
    emphasise, on the lines that matter most. Worse, the message was ESCAPED to
    protect markup that was never interpreted, so an error quoting a Revit
    string containing `&`, `<` or `>` reached the screen as `&amp;` and `&lt;`.
    Both are gone. A mark is TEXT now, which needs nothing to render it.

    Red would still be better than a mark, and there is no way to get it from
    here: colour would mean importing pyRevit's output module, and the pyRevit
    IronPython modules crash this engine (see the pushbutton header). A mark
    every console shows beats a colour this one does not.

    EVERY LINE IS MARKED ON ITS OWN. A Revit exception arrives as a paragraph --
    message, then "Parameter name:", then a stack -- and a single mark in front
    of the first line leaves the rest looking like ordinary notes.
    """
    for line in str(msg).split("\n"):
        if not line.strip():
            _OUT.say("")
            continue
        _OUT.say(ERROR_MARK + line)


class _NullProgress(object):
    """Last resort: no window, no crash."""
    cancelled = False
    title = ""
    status = ""

    def show(self):
        return self

    def close(self):
        pass

    def update_progress(self, *args, **kwargs):
        pass


_BAR = _NullProgress()


_READ_STEPS = 2


_BUILD_STEPS = 10
# A multi-storey run repeats the build once per storey. Reporting each storey
# 0-100 made the bar restart five times; instead the storey being built is an
# OFFSET into one continuous 0-100 over storeys x steps.


# A multi-storey run repeats the build once per storey. Reporting each storey
# 0-100 made the bar restart five times; instead the storey being built is an
# OFFSET into one continuous 0-100 over storeys x steps.
_STOREY_INDEX = 0


_STOREY_COUNT = 1


def _storey_span(index, count):
    """Tell the bar which storey of how many is being built."""
    global _STOREY_INDEX, _STOREY_COUNT
    _STOREY_INDEX = max(0, int(index))
    _STOREY_COUNT = max(1, int(count))


def _open_progress(phase):
    """Open a bar for one phase ("read" or "build"), closing any previous one."""
    global _BAR
    _close_progress()
    if _CpyProgressBar is None:
        return _BAR
    caption = ("cad2bim - reading CAD" if phase == "read"
               else "cad2bim - building model")
    try:
        _BAR = _CpyProgressBar(title=caption + ": {value}/{max_value}",
                               cancellable=False, show_eta=True)
        _BAR.show()
        _BAR._caption = caption
    except Exception:
        _BAR = _NullProgress()      # no host window / no WPF: run headless
    return _BAR


def _close_progress():
    global _BAR
    try:
        _BAR.close()
    except Exception:
        pass
    _BAR = _NullProgress()


def _progress(done, total, label):
    """Move the current bar and log the same step to the deferred console.

    The console line survives into the log a failed run prints; the bar is what
    the user watches while a big drawing is being read or built. In a
    multi-storey run the step is folded into ONE span over every storey, so the
    bar climbs to 100 once rather than restarting per floor.
    """
    if total == _BUILD_STEPS and _STOREY_COUNT > 1:
        done = _STOREY_INDEX * _BUILD_STEPS + done
        total = _STOREY_COUNT * _BUILD_STEPS
        label = "storey {0}/{1}: {2}".format(_STOREY_INDEX + 1, _STOREY_COUNT,
                                             label)
    try:
        caption = getattr(_BAR, "_caption", "cad2bim")
        _BAR.title = "{0}: {1}  ({{value}}/{{max_value}}, {{eta}} left)".format(
            caption, label)
        _BAR.update_progress(done, total)
    except Exception:
        pass
    frac = (float(done) / total) if total else 1.0
    fill = int(round(frac * 10))
    _say("[{0}{1}] {2:3d}%  {3}".format("#" * fill, "-" * (10 - fill),
                                        int(round(frac * 100)), label))
