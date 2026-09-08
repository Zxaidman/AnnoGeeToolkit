@echo off
set "_SCRIPT=%~dp0auto_provision.py"

rem Single source of truth for the targeted CPython version used by BOTH this
rem launcher and tools/auto_provision.py. Change it here (and update
rem TARGET_PY_VERSION in auto_provision.py) to retarget, e.g. "3.12" -> "3.14".
rem Keep it as "Major.Minor" (no leading/trailing spaces).
set "_PY_VERSION=3.12"

rem Prefer the `py` launcher pinned to the target version (python.org /
rem py-installer layout). auto_provision.py still re-verifies the real version
rem at runtime, so this is a hint, not a guarantee.
where py >nul 2>nul
if not errorlevel 1 (
    py -%_PY_VERSION% "%_SCRIPT%"
) else (
    rem No `py` launcher: fall back to the default python on PATH. The script
    rem itself hard-checks for the target version and relaunches under it when
    rem available, otherwise it stops cleanly without touching anything.
    python "%_SCRIPT%"
)

if errorlevel 1 (
    echo.
    echo [!] Provisioning did not complete - see the message above.
    echo.    This is almost always "Python %_PY_VERSION% not installed on this machine".
)
pause
