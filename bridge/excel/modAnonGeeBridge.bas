Attribute VB_Name = "modAnonGeeBridge"
' AnonGee Bridge - the Excel end of the spike (CRIT-1)
' ===========================================================================
' Two subs, and between them they answer whether an Excel button can reach
' Revit at all:
'
'   AnonGeeBridge_Ping     the Routes server, with no Revit in the question
'   AnonGeeBridge_Status   the open model, through Revit's own thread
'
' Ping deliberately asks for nothing from Revit. If Ping answers and Status
' does not, the server is fine and the External Event marshalling is not --
' which is the difference between knowing what to fix and guessing.
'
' Nothing here writes to a model and nothing here is the product. The real
' bridge posts a job and polls for a result; this proves the wire exists.
'
' HOW TO RUN
'   1. In Revit: pyRevit tab -> Settings -> turn the Routes server on, restart
'      Revit. (Confirming exactly where that switch is, is part of this spike.)
'   2. In Excel: Alt+F11 -> File -> Import File -> this .bas
'   3. Alt+F8 -> AnonGeeBridge_Ping -> Run
'
' KEEP THIS SMALL. Anything the macro knows is a thing that has to be kept in
' step with Python by hand. It marshals nothing and holds no data model, and
' it must stay that way -- the command envelope carries which sheet to read,
' and Revit opens the workbook itself with the reader that already exists.
' ===========================================================================

Option Explicit

' ---------------------------------------------------------------------------
' THIS FILE MUST BE PURE ASCII.
'
' Excel's VBA importer reads a .bas as the machine's ANSI code page, not UTF-8.
' Two em dashes in message strings arrived in the dialogs as "a-hat-euro" --
' mojibake in the one place a user actually reads. It is the same lesson as the
' result TSV, one layer further out: a file crossing into VBA has no way to
' declare its encoding, so it must not need one.
'
' tests/test_bridge.py fails on any byte above 127 in this file.
' ---------------------------------------------------------------------------

' Sleep, so polling does not spin a core. Excel has no wait that yields.
#If VBA7 Then
    Public Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal milliseconds As Long)
#Else
    Public Declare Sub Sleep Lib "kernel32" (ByVal milliseconds As Long)
#End If

' The host and path also live in AnonGee.extension/startup.py, and a test in
' tests/test_bridge.py holds the two together. A URL that disagrees with its
' route costs an afternoon and looks like a network problem the whole time.
Public Const BRIDGE_HOST As String = "localhost"
Public Const BRIDGE_PORT As Long = 48884
Public Const BRIDGE_API As String = "anongee"

' Long enough for Revit to finish what it is doing, short enough that a user
' does not think Excel has hung. The real bridge posts and polls instead of
' waiting, precisely because this number can never be right for every job.
Public Const BRIDGE_TIMEOUT_SECONDS As Long = 15

' How the macro waits for a result file. Polling, because Excel cannot host a
' listener without a great deal of unpleasantness.
Public Const POLL_EVERY_MS As Long = 500
Public Const GIVE_UP_AFTER_SECONDS As Long = 300

' The CONTROL sheet's columns are found by these names, never by number.
'
' They were numbers once. Adding a Built? column to the workbook moved Write?
' from 5 to 6, the macro went on reading 5, and every run was a dry run that
' could not be switched off -- while the status it wrote landed in the Write?
' cell and made the switch say "done". BUG-16. A name cannot be moved by
' inserting a column beside it, so names it is.
Public Const CONTROL_SHEET As String = "CONTROL"
Public Const COLUMN_COMMAND As String = "Command"
Public Const COLUMN_WRITE As String = "Write?"
Public Const COLUMN_STATUS As String = "Last status"
Public Const COLUMN_WHEN As String = "When"
Public Const COLUMN_NOTE As String = "Note"

' Where the unit for the whole workbook is kept. Revit works in internal feet
' whatever a project's display units say, so the number in a cell means nothing
' until something says which unit it is in.
Public Const INFO_SHEET As String = "INFO"
Public Const INFO_UNITS_KEY As String = "UNITS"
Public Const INFO_URL_KEY As String = "BRIDGE_URL"
Public Const UNITS_DEFAULT As String = "mm"

' How many ports past the default to try when nothing answers. pyRevit takes
' 48884 when it can and the next free one when it cannot.
Public Const PORT_SEARCH_RANGE As Long = 8

' And how long to wait on each. One second, not the usual fifteen: nine ports
' at fifteen seconds is over two minutes of Excel not responding, and a
' diagnostic slower than the user's patience is worse than none. BUG-8.
Public Const PROBE_TIMEOUT_MS As Long = 1000

' How far down a sheet a header row is looked for. Deep enough for a title
' block above the table, shallow enough to be instant.
Public Const HEADER_SEARCH_ROWS As Long = 30

' Columns that stay in millimetres whatever the workbook is set to.
'
' Metres were chosen so a level reads as 3.30 rather than 3300. By the same
' argument a cover of 0.05 and a bar of 0.012 read worse than 50 and 12, so
' consistency here would cost the thing it was bought for.
Public Const PINNED_TO_MM As String = "cover,dia,diameter,bardia"

' How a length is shown once converted. Millimetres whole, metres to two.
Public Const FORMAT_MM As String = "#,##0"
Public Const FORMAT_M As String = "0.00"

' The font, in order of preference. The first one installed wins.
Public Const FONT_STACK As String = "Segoe UI Semibold,Inter,Segoe UI,Cambria,Calibri"
Public Const SIZE_TITLE As Long = 14
Public Const SIZE_HEADER As Long = 11
Public Const SIZE_BODY As Long = 10
Public Const ROW_HEIGHT As Long = 20

' What a button is: a rounded rectangle the same shape as the ones already on
' CONTROL. Anything named with this prefix belongs to us and is replaced on a
' rebuild; anything else on the sheet is somebody's and is left alone.
Public Const BUTTON_PREFIX As String = "AnonGeeRun_"
Public Const BUTTON_TEMPLATE As String = "AnonGeeButton_Template"

' A button sits exactly on its cell -- no inset -- and is set to move and size
' with it. So widening a column or dragging a row taller takes the button with
' it, and the sheet stays laid out on the gridlines rather than on a set of
' coordinates that were right when they were written.
Public Const BUTTON_INSET As Long = 0
Public Const BUTTON_BORDER As Long = 1

' ---------------------------------------------------------------------------
' EVERY module-level declaration lives above this line, and it has to.
'
' VBA requires all Const, Dim and Declare statements to come before the first
' procedure. Two of these were written next to the code that used them, further
' down the module, and the whole thing refused to compile with "Only comments
' may appear after End Sub, End Function, or End Property" -- an error that
' names the symptom and not the cause, and appears only when Excel compiles,
' which is after the import and long after any test here has passed.
'
' tests/test_bridge.py fails on a declaration below the first procedure now.
' ---------------------------------------------------------------------------


Public Function BridgeUrl(ByVal route As String) As String
    ' Where Revit is listening, from INFO if it says, from the constants if not.
    '
    ' **pyRevit's port is not fixed.** It takes 48884 when it can and the next
    ' free one when it cannot, so a second Revit session, or one that did not
    ' shut down cleanly, moves it. The project owner hit exactly that: pyRevit
    ' on 48885, INFO changed to match, and the macro still calling 48884 --
    ' because the port was a constant and the INFO row was decoration.
    Dim base As String
    base = ReadInfo(INFO_URL_KEY)
    If base = "" Then
        base = "http://" & BRIDGE_HOST & ":" & CStr(BRIDGE_PORT) & _
               "/" & BRIDGE_API
    End If
    Do While Right$(base, 1) = "/"
        base = Left$(base, Len(base) - 1)
    Loop
    BridgeUrl = base & "/" & route
End Function


Public Function ReadInfo(ByVal key As String) As String
    ' One value from the INFO sheet, by key. "" when it is not there.
    '
    ' The key may carry a unit -- SURVEY_OFFSET (m) -- so the brackets are
    ' stripped before comparing, which is the same rule ReadUnits uses.
    ReadInfo = ""
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(INFO_SHEET)
    On Error GoTo 0
    If sheet Is Nothing Then Exit Function

    Dim row As Long
    For row = 1 To HEADER_SEARCH_ROWS
        If Fold(StripUnit(CStr(sheet.Cells(row, 1).Value))) = Fold(key) Then
            ReadInfo = Trim$(CStr(sheet.Cells(row, 2).Value))
            Exit Function
        End If
    Next row
End Function


Public Function FindListeningPort() As Long
    ' Which nearby port answers a ping, or 0. Used only when a call has already
    ' failed, so its cost is paid once and only when it buys something.
    '
    ' Turning "nothing is listening" into "pyRevit is on 48885, put that in
    ' INFO" is the difference between a dead end and an instruction.
    FindListeningPort = 0
    Dim port As Long
    For port = BRIDGE_PORT To BRIDGE_PORT + PORT_SEARCH_RANGE
        If PortAnswers(port) Then
            FindListeningPort = port
            Exit Function
        End If
    Next port
End Function


Private Function PortAnswers(ByVal port As Long) As Boolean
    ' One ping, with a **one second** timeout rather than the usual fifteen.
    '
    ' Nine ports at the normal timeout is over two minutes of Excel not
    ' responding, which is how BUG-8 went: a diagnostic slow enough that the
    ' user gives up before it answers is worse than no diagnostic. A port that
    ' is open answers a ping immediately or is not the one being looked for.
    PortAnswers = False
    On Error GoTo Failed

    Dim winHttp As Object
    Set winHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    winHttp.SetTimeouts PROBE_TIMEOUT_MS, PROBE_TIMEOUT_MS, _
                        PROBE_TIMEOUT_MS, PROBE_TIMEOUT_MS
    winHttp.Open "GET", "http://" & BRIDGE_HOST & ":" & CStr(port) & "/" & _
                 BRIDGE_API & "/ping", False
    winHttp.Send
    PortAnswers = (winHttp.Status = 200)
    Exit Function

Failed:
    PortAnswers = False
End Function


' --- the two spike commands ------------------------------------------------

Public Sub AnonGeeBridge_Ping()
    Dim body As String
    body = HttpGet(BridgeUrl("ping"))
    ReportToSheet "PING", body
End Sub


Public Sub AnonGeeBridge_Status()
    Dim body As String
    body = HttpGet(BridgeUrl("status"))
    ReportToSheet "STATUS", body
End Sub


' --- the wire --------------------------------------------------------------

Public Function HttpGet(ByVal url As String) As String
    ' Two attempts, each in its own handler-free helper.
    '
    ' The first version chained them inside one function -- On Error GoTo
    ' UseMsxml, then On Error GoTo Failed inside that label -- and it does not
    ' work. **VBA does not leave the error handler until Resume, Exit or
    ' On Error GoTo -1**, so the second On Error GoTo was ignored and the
    ' MSXML2 failure escaped as an unhandled runtime error: "800c0005, the
    ' system cannot locate the resource specified", with a Debug button, from a
    ' function whose entire job was to return failures rather than raise them.
    '
    ' Two functions, one handler each, no nesting. The trap cannot recur
    ' because there is nothing left to nest.
    Dim answer As String

    answer = HttpGetWinHttp(url)
    If Left$(answer, 6) <> "ERROR:" Then
        HttpGet = answer
        Exit Function
    End If

    Dim firstError As String
    firstError = Mid$(answer, 7)

    answer = HttpGetMsxml(url)
    If Left$(answer, 6) <> "ERROR:" Then
        HttpGet = answer
        Exit Function
    End If

    ' The failure is the answer here, so it is returned rather than raised.
    ' "Nothing is listening" and "Revit is busy" look identical from Excel and
    ' are told apart by whether Ping answers while Status does not.
    HttpGet = "{""ok"": false, ""error"": """ & _
              JsonEscape(firstError & " / " & Mid$(answer, 7)) & _
              """, ""url"": """ & JsonEscape(url) & """}"
End Function


Private Function HttpGetWinHttp(ByVal url As String) As String
    ' WinHttp first: it is the only one with a settable timeout, and without
    ' one a busy Revit hangs Excel with no way back.
    On Error GoTo Failed
    Dim winHttp As Object
    Set winHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    winHttp.SetTimeouts BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000
    winHttp.Open "GET", url, False
    winHttp.Send
    HttpGetWinHttp = winHttp.ResponseText
    Exit Function
Failed:
    HttpGetWinHttp = "ERROR:WinHttp " & Err.Number & " " & Err.Description
End Function


Private Function HttpGetMsxml(ByVal url As String) As String
    On Error GoTo Failed
    Dim msxml As Object
    Set msxml = CreateObject("MSXML2.XMLHTTP")
    msxml.Open "GET", url, False
    msxml.Send
    HttpGetMsxml = msxml.ResponseText
    Exit Function
Failed:
    HttpGetMsxml = "ERROR:MSXML2 " & Err.Number & " " & Err.Description
End Function


' --- reporting -------------------------------------------------------------

Private Sub ReportToSheet(ByVal label As String, ByVal body As String)
    Dim sheet As Worksheet
    Set sheet = EnsureSheet("BRIDGE_SPIKE")

    Dim row As Long
    row = sheet.Cells(sheet.Rows.Count, 1).End(xlUp).row + 1
    If row < 2 Then
        sheet.Cells(1, 1).Value = "When"
        sheet.Cells(1, 2).Value = "Call"
        sheet.Cells(1, 3).Value = "OK"
        sheet.Cells(1, 4).Value = "Engine"
        sheet.Cells(1, 5).Value = "Document"
        sheet.Cells(1, 6).Value = "Raw response"
        sheet.Rows(1).Font.Bold = True
        row = 2
    End If

    sheet.Cells(row, 1).Value = Now
    sheet.Cells(row, 2).Value = label
    sheet.Cells(row, 3).Value = JsonValue(body, "ok")
    sheet.Cells(row, 4).Value = JsonValue(body, "version")
    sheet.Cells(row, 5).Value = JsonValue(body, "title")
    sheet.Cells(row, 6).Value = body
    sheet.Columns("A:E").AutoFit

    MsgBox label & ": " & Left$(body, 400), vbInformation, "AnonGee Bridge"
End Sub


Private Function EnsureSheet(ByVal name As String) As Worksheet
    On Error Resume Next
    Set EnsureSheet = ThisWorkbook.Worksheets(name)
    On Error GoTo 0
    If EnsureSheet Is Nothing Then
        Set EnsureSheet = ThisWorkbook.Worksheets.Add( _
            After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        EnsureSheet.name = name
    End If
End Function


' --- NOT a JSON parser -----------------------------------------------------
' It finds the first "key": value pair and returns the value as text, with
' string escapes undone. Good enough for the handful of scalar fields the post's
' answer carries, and no further -- it does not walk objects, arrays or nesting.
'
' The escaping half is not optional though, and that was the lesson: the answer
' carries a Windows path, JSON doubles every backslash in it, and a value
' returned verbatim is a path Windows may or may not accept. The result file it
' pointed at would simply never be found, and the macro would report a job that
' had in fact finished.

Private Function FindClosingQuote(ByVal rest As String) As Long
    ' The first quote that is not escaped. A Windows path in JSON is full of
    ' backslashes and a naive InStr would stop at the wrong one the moment a
    ' value ended with one.
    Dim index As Long
    index = 2
    Do While index <= Len(rest)
        Select Case Mid$(rest, index, 1)
            Case "\"
                index = index + 2          ' skip whatever it escapes
            Case """"
                FindClosingQuote = index
                Exit Function
            Case Else
                index = index + 1
        End Select
    Loop
End Function


Public Function JsonUnescape(ByVal text As String) As String
    ' The reason this exists, and it is not academic: the post's answer carries
    '   "resultTsv": "C:\\Users\\praka\\...\\inbox\\x.result.tsv"
    ' and JSON doubles every backslash. Returning that verbatim gave the macro
    ' a path with doubled separators to hand to Dir$ and Open -- which Windows
    ' may or may not collapse for you, and "may or may not" is not a design.
    Dim out As String
    Dim index As Long
    index = 1
    Do While index <= Len(text)
        If Mid$(text, index, 1) = "\" And index < Len(text) Then
            Select Case Mid$(text, index + 1, 1)
                Case "\": out = out & "\"
                Case """": out = out & """"
                Case "/": out = out & "/"
                Case "n": out = out & vbLf
                Case "r": out = out & vbCr
                Case "t": out = out & vbTab
                Case Else: out = out & Mid$(text, index + 1, 1)
            End Select
            index = index + 2
        Else
            out = out & Mid$(text, index, 1)
            index = index + 1
        End If
    Loop
    JsonUnescape = out
End Function


Public Function JsonValue(ByVal body As String, ByVal key As String) As String
    Dim marker As String
    marker = """" & key & """"

    Dim at As Long
    at = InStr(1, body, marker, vbTextCompare)
    If at = 0 Then
        JsonValue = ""
        Exit Function
    End If

    Dim colon As Long
    colon = InStr(at + Len(marker), body, ":")
    If colon = 0 Then
        JsonValue = ""
        Exit Function
    End If

    Dim rest As String
    rest = LTrim$(Mid$(body, colon + 1))

    If Left$(rest, 1) = """" Then
        Dim closing As Long
        closing = FindClosingQuote(rest)
        If closing = 0 Then
            JsonValue = ""
        Else
            JsonValue = JsonUnescape(Mid$(rest, 2, closing - 2))
        End If
        Exit Function
    End If

    Dim ends As Long
    ends = Len(rest) + 1
    Dim index As Long
    Dim ch As String
    For index = 1 To Len(rest)
        ch = Mid$(rest, index, 1)
        If ch = "," Or ch = "}" Or ch = "]" Then
            ends = index
            Exit For
        End If
    Next index
    JsonValue = Trim$(Left$(rest, ends - 1))
End Function


' ===========================================================================
' Running a job
' ===========================================================================
' Post, then wait for a file. Not "post and wait for the response" -- Revit
' cannot be driven while it is busy, so the route queues the job and answers
' immediately. A synchronous call that waited for a five-thousand-element run
' would time out and leave Excel hung while the job was still going.
'
' The macro never works out where the bridge folder is. The post's answer
' carries resultTsv, so there is exactly one implementation of those rules and
' it is not this one -- a third copy, in VBA, untestable, would be wrong the
' first time somebody set ANONGEE_BRIDGE_HOME.
'
' It waits for the TSV rather than the JSON because VBA has no JSON parser and
' should not be given a hand-written one. Revit writes both; this reads lines.
' ===========================================================================

Public Sub Run_Echo()
    RunCommand "bridge.echo", ""
End Sub

Public Sub Run_Levels()
    RunCommand "levels.sync", "LEVELS"
End Sub

Public Sub Run_Grids()
    RunCommand "grids.sync", "GRIDS"
End Sub


' The four below are declared in Revit and not written yet. They exist so the
' button exists: pressing one answers "declared but not built yet", which says
' where the work is. A button with no macro assigned answers with Excel's own
' "cannot find the macro", which says nothing.
Public Sub Run_Footings()
    RunCommand "footings.sync", "FOOTING_PLACEMENT"
End Sub


Public Sub Run_Columns()
    RunCommand "columns.sync", "COLUMN_PLACEMENT"
End Sub


Public Sub Run_Beams()
    RunCommand "beams.sync", "BEAM_PLACEMENT"
End Sub


Public Sub Run_Slabs()
    RunCommand "slabs.sync", "SLAB_PLACEMENT"
End Sub


Public Sub RunCommand(ByVal command As String, ByVal sheetName As String)
    ' The workbook on disk is what Revit reads, so it has to be the workbook
    ' you are looking at. Saving first is not a courtesy, it is the contract.
    On Error Resume Next
    ThisWorkbook.Save
    On Error GoTo 0

    Dim unreadable As String
    unreadable = ControlIsReadable(command)
    If unreadable <> "" Then
        MsgBox unreadable & vbCrLf & vbCrLf & _
               "Nothing was sent. A run that cannot read its own Write? " & _
               "switch would be a dry run that looks like Revit ignoring " & _
               "you, and that is worth refusing.", vbExclamation, "AnonGee Bridge"
        Exit Sub
    End If

    Dim dryRun As Boolean
    dryRun = ReadDryRun(command)

    Dim reply As String
    reply = HttpPost(BridgeUrl("jobs"), _
                     JobJson(command, sheetName, dryRun, ReadUnits()))

    Dim jobId As String
    jobId = JsonValue(reply, "jobId")
    If jobId = "" Then
        ' No id means the post never reached a route. Say which of the two
        ' halves is missing rather than showing the raw error and leaving the
        ' user to guess -- they are different switches in different places.
        If InStr(reply, """ok"": false") > 0 Then
            ' Before saying nothing is listening, look. pyRevit takes the next
            ' free port when 48884 is busy, so "nothing is listening" is often
            ' "something is listening, one port along" -- which is a thing to
            ' fix rather than a thing to despair at.
            Dim elsewhere As Long
            elsewhere = FindListeningPort()

            Dim advice As String
            If elsewhere > 0 Then
                advice = "But something IS answering on port " & elsewhere & _
                         "." & vbCrLf & vbCrLf & _
                         "pyRevit takes the next free port when its usual " & _
                         "one is busy. Put this in INFO -> " & INFO_URL_KEY & _
                         ":" & vbCrLf & vbCrLf & _
                         "    http://" & BRIDGE_HOST & ":" & elsewhere & "/" & _
                         BRIDGE_API & vbCrLf & vbCrLf & _
                         "then press the button again. Nothing else needs " & _
                         "changing."
            Else
                advice = "In Revit: pyRevit Settings -> Routes -> " & _
                         "Routes Server (Beta)" & _
                         ", then restart Revit." & vbCrLf & _
                         vbCrLf & "Then AnonGee tab -> Dev -> Bridge Check, " & _
                         "which says whether the startup script ran." & _
                         vbCrLf & vbCrLf & "Ports " & BRIDGE_PORT & " to " & _
                         (BRIDGE_PORT + PORT_SEARCH_RANGE) & " were all " & _
                         "tried and none answered."
            End If

            MsgBox "Nothing is listening at " & BridgeUrl("jobs") & vbCrLf & _
                   vbCrLf & advice & vbCrLf & vbCrLf & _
                   Left$(reply, 300), vbExclamation, "AnonGee Bridge"
            LogRow "", command, "unreachable", "", advice
            Exit Sub
        End If
        LogRow "", command, "rejected", "", _
               "no job id came back: " & Left$(reply, 200)
        MsgBox "The job was not queued." & vbCrLf & vbCrLf & Left$(reply, 400), _
               vbExclamation, "AnonGee Bridge"
        Exit Sub
    End If

    Dim resultPath As String
    resultPath = JsonValue(reply, "resultTsv")

    Dim body As String
    body = WaitForResult(resultPath)
    If body = "" Then
        LogRow jobId, command, "waiting", "", _
               "no result after " & GIVE_UP_AFTER_SECONDS & "s - the job may " & _
               "still be running. Is Bridge Listener switched on in Revit?"
        MsgBox "Queued as " & jobId & ", but no result yet." & vbCrLf & vbCrLf & _
               "Is Bridge Listener switched on in Revit?", _
               vbInformation, "AnonGee Bridge"
        Exit Sub
    End If

    WriteResult command, body
End Sub


Private Function JobJson(ByVal command As String, ByVal sheetName As String, _
                         ByVal dryRun As Boolean, ByVal units As String) As String
    ' Built by hand because it is five fields. Anything larger belongs in a
    ' sheet Revit reads for itself -- the envelope carries which sheet, never
    ' the data.
    '
    ' The unit travels with the job because a number in a cell means nothing
    ' without one. Revit is internal feet whatever the project units say, so
    ' something has to state what 3.3 was meant to be.
    JobJson = "{""envelope"": ""1.0""" & _
              ", ""command"": """ & command & """" & _
              ", ""workbook"": """ & JsonEscape(ThisWorkbook.FullName) & """" & _
              ", ""sheet"": """ & sheetName & """" & _
              ", ""options"": {""dryRun"": " & LCase$(CStr(dryRun)) & _
              ", ""units"": """ & units & """}}"
End Function


Public Function ReadUnits() As String
    ' The unit for the whole workbook, from INFO. "mm" when the sheet does not
    ' say -- every workbook before this one was millimetres, and a default that
    ' silently rescales an old sheet by a thousand is not a default.
    ReadUnits = UNITS_DEFAULT
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(INFO_SHEET)
    On Error GoTo 0
    If sheet Is Nothing Then Exit Function

    Dim row As Long
    For row = 1 To HEADER_SEARCH_ROWS
        If Fold(CStr(sheet.Cells(row, 1).Value)) = Fold(INFO_UNITS_KEY) Then
            ReadUnits = NormaliseUnit(CStr(sheet.Cells(row, 2).Value))
            Exit Function
        End If
    Next row
End Function


Public Function NormaliseUnit(ByVal text As String) As String
    ' "m" or "mm", from whatever was typed or picked.
    Dim folded As String
    folded = Fold(text)
    If folded = "" Then
        NormaliseUnit = UNITS_DEFAULT
    ElseIf Left$(folded, 2) = "mm" Then
        NormaliseUnit = "mm"
    ElseIf Left$(folded, 6) = "millim" Then
        NormaliseUnit = "mm"
    ElseIf Left$(folded, 1) = "m" Then
        NormaliseUnit = "m"
    Else
        NormaliseUnit = UNITS_DEFAULT
    End If
End Function


Public Function JsonEscape(ByVal text As String) As String
    JsonEscape = Replace(Replace(text, "\", "\\"), """", "\""")
End Function


Public Function HttpPost(ByVal url As String, ByVal body As String) As String
    ' One handler, no nesting -- see HttpGet for why that matters.
    On Error GoTo Failed
    Dim winHttp As Object
    Set winHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    winHttp.SetTimeouts BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000
    winHttp.Open "POST", url, False
    winHttp.SetRequestHeader "Content-Type", "application/json"
    winHttp.Send body
    HttpPost = winHttp.ResponseText
    Exit Function
Failed:
    HttpPost = "{""ok"": false, ""error"": """ & _
               JsonEscape(Err.Number & " " & Err.Description) & _
               """, ""url"": """ & JsonEscape(url) & """}"
End Function


Private Function WaitForResult(ByVal path As String) As String
    If path = "" Then Exit Function

    Dim giveUpAt As Date
    giveUpAt = DateAdd("s", GIVE_UP_AFTER_SECONDS, Now)

    Do While Now < giveUpAt
        If Len(Dir$(path)) > 0 Then
            WaitForResult = ReadAllText(path)
            If WaitForResult <> "" Then Exit Function
        End If
        ' DoEvents so Excel stays answerable while it waits. Without it the
        ' window greys out and the user decides it has crashed.
        DoEvents
        Sleep POLL_EVERY_MS
    Loop
End Function


Private Function ReadAllText(ByVal path As String) As String
    Dim handle As Integer
    Dim text As String
    On Error GoTo Failed
    handle = FreeFile
    Open path For Input As #handle
    text = Input$(LOF(handle), #handle)
    Close #handle
    ReadAllText = text
    Exit Function
Failed:
    ' Being written right now. The writer renames into place, so the next poll
    ' gets the whole thing.
    On Error Resume Next
    Close #handle
End Function


' ===========================================================================
' Reading the result
' ===========================================================================
' Two blocks, tab separated. #RESULT is key/value, #FINDINGS is a table. No
' quoting rules, no escaping, no parser -- which is the entire reason Revit
' writes this alongside the JSON.
' ===========================================================================

Private Sub WriteResult(ByVal command As String, ByVal body As String)
    Dim lines() As String
    lines = Split(Replace(body, vbCrLf, vbLf), vbLf)

    Dim inFindings As Boolean
    Dim jobId As String, status As String, note As String
    Dim counts As String
    Dim findings As Long

    Dim index As Long
    For index = LBound(lines) To UBound(lines)
        Dim line As String
        line = lines(index)
        If line = "#RESULT" Then
            inFindings = False
        ElseIf line = "#FINDINGS" Then
            inFindings = True
        ElseIf line <> "" Then
            Dim parts() As String
            parts = Split(line, vbTab)
            If inFindings Then
                If parts(0) <> "Severity" Then findings = findings + 1
            ElseIf UBound(parts) >= 1 Then
                Select Case parts(0)
                    Case "jobId": jobId = parts(1)
                    Case "status": status = parts(1)
                    Case "note": note = parts(1)
                    Case "command", "started", "finished"
                    Case Else
                        If parts(1) <> "" Then
                            counts = counts & parts(0) & "=" & parts(1) & "  "
                        End If
                End Select
            End If
        End If
    Next index

    LogRow jobId, command, status, counts, note
    ShowFindings body, command, jobId

    MsgBox command & ": " & status & vbCrLf & vbCrLf & _
           Trim$(counts) & vbCrLf & note & vbCrLf & vbCrLf & _
           findings & " finding(s) - see the FINDINGS sheet.", _
           vbInformation, "AnonGee Bridge"
End Sub


Private Sub ShowFindings(ByVal body As String, ByVal command As String, _
                         ByVal jobId As String)
    ' Write this job's findings, under a header saying whose they are.
    '
    ' The header is not decoration. This sheet used to be cleared by every
    ' result including one with nothing to say -- so pressing two unbuilt
    ' commands after a run that reported fifteen failures left an empty sheet,
    ' and an empty sheet is the same picture as a run that never reported.
    ' Fifteen columns went unexplained exactly that way. BUG-20.
    Dim sheet As Worksheet
    Set sheet = EnsureSheet("FINDINGS")
    sheet.Cells.Clear

    sheet.Cells(1, 1).Value = "Findings from"
    sheet.Cells(1, 2).Value = command
    sheet.Cells(1, 3).Value = jobId
    sheet.Cells(1, 4).Value = Now
    sheet.Rows(1).Font.Bold = True

    Dim lines() As String
    lines = Split(Replace(body, vbCrLf, vbLf), vbLf)

    Dim writing As Boolean
    Dim row As Long
    row = 3

    Dim index As Long
    For index = LBound(lines) To UBound(lines)
        If lines(index) = "#FINDINGS" Then
            writing = True
        ElseIf lines(index) = "#RESULT" Then
            writing = False
        ElseIf writing And lines(index) <> "" Then
            Dim parts() As String
            parts = Split(lines(index), vbTab)
            Dim column As Long
            For column = LBound(parts) To UBound(parts)
                sheet.Cells(row, column + 1).Value = parts(column)
            Next column
            row = row + 1
        End If
    Next index

    If row = 3 Then
        sheet.Cells(3, 1).Value = "No findings. This run had nothing to report."
    Else
        sheet.Rows(3).Font.Bold = True
    End If
    sheet.Columns("A:E").AutoFit
End Sub


Private Sub LogRow(ByVal jobId As String, ByVal command As String, _
                   ByVal status As String, ByVal counts As String, _
                   ByVal note As String)
    Dim sheet As Worksheet
    Set sheet = EnsureSheet("LOG")

    Dim row As Long
    row = sheet.Cells(sheet.Rows.Count, 1).End(xlUp).row + 1
    If row < 2 Then
        sheet.Range("A1:F1").Value = _
            Array("When", "Job", "Command", "Status", "Counts", "Note")
        sheet.Rows(1).Font.Bold = True
        row = 2
    End If

    sheet.Cells(row, 1).Value = Now
    sheet.Cells(row, 2).Value = jobId
    sheet.Cells(row, 3).Value = command
    sheet.Cells(row, 4).Value = status
    sheet.Cells(row, 5).Value = Trim$(counts)
    sheet.Cells(row, 6).Value = note
    sheet.Columns("A:F").AutoFit

    WriteControlStatus command, status, note
End Sub


Private Sub WriteControlStatus(ByVal command As String, ByVal status As String, _
                               ByVal note As String)
    ' The CONTROL sheet carries one row per command; find it by name and put
    ' the outcome beside the button that caused it.
    '
    ' Every column is found by its header. Writing to a fixed column number is
    ' how the status once landed in the Write? cell and turned the switch into
    ' the word "done" -- see BUG-16 and CONTROL_SHEET above.
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(CONTROL_SHEET)
    On Error GoTo 0
    If sheet Is Nothing Then Exit Sub

    Dim row As Long
    row = ControlRowFor(sheet, command)
    If row = 0 Then Exit Sub

    Dim header As Long
    header = ControlHeaderRow(sheet)
    If header = 0 Then Exit Sub

    PutCell sheet, row, ControlColumn(sheet, header, COLUMN_STATUS), status
    PutCell sheet, row, ControlColumn(sheet, header, COLUMN_WHEN), Now
    PutCell sheet, row, ControlColumn(sheet, header, COLUMN_NOTE), note
End Sub


Private Sub PutCell(ByVal sheet As Worksheet, ByVal row As Long, _
                    ByVal column As Long, ByVal value As Variant)
    ' A missing column is skipped rather than written to column zero. The
    ' report says which one was missing; guessing a position is what caused
    ' the bug this is here to prevent.
    If column = 0 Then Exit Sub
    sheet.Cells(row, column).Value = value
End Sub


Public Function ControlHeaderRow(ByVal sheet As Worksheet) As Long
    ' The row carrying the word Command. Found, not assumed: the CONTROL sheet
    ' has five lines of instructions above its table today and will grow more.
    ControlHeaderRow = 0
    Dim row As Long
    Dim column As Long
    For row = 1 To HEADER_SEARCH_ROWS
        For column = 1 To 30
            If Trim$(CStr(sheet.Cells(row, column).Value)) = COLUMN_COMMAND Then
                ControlHeaderRow = row
                Exit Function
            End If
        Next column
    Next row
End Function


Public Function ControlColumn(ByVal sheet As Worksheet, ByVal header As Long, _
                              ByVal name As String) As Long
    ' The column under this header, or 0. Compared folded, so "Write?" still
    ' matches after somebody types a space after it.
    ControlColumn = 0
    Dim column As Long
    For column = 1 To 30
        If Fold(CStr(sheet.Cells(header, column).Value)) = Fold(name) Then
            ControlColumn = column
            Exit Function
        End If
    Next column
End Function


Public Function ControlRowFor(ByVal sheet As Worksheet, _
                              ByVal command As String) As Long
    ' The row whose Command cell is this command, or 0.
    ControlRowFor = 0
    Dim header As Long
    header = ControlHeaderRow(sheet)
    If header = 0 Then Exit Function

    Dim commandColumn As Long
    commandColumn = ControlColumn(sheet, header, COLUMN_COMMAND)
    If commandColumn = 0 Then Exit Function

    Dim row As Long
    For row = header + 1 To header + 60
        If Trim$(CStr(sheet.Cells(row, commandColumn).Value)) = command Then
            ControlRowFor = row
            Exit Function
        End If
    Next row
End Function


Public Function Fold(ByVal text As String) As String
    ' Lower case, no spaces. Enough to survive a typed heading.
    Fold = LCase$(Replace(Trim$(text), " ", ""))
End Function


Private Function ReadDryRun(ByVal command As String) As Boolean
    ' True unless the Write? cell for this command says Yes.
    '
    ' The default is a dry run and stays that way through every failure below:
    ' no sheet, no header, no column, no row. The one thing this must never do
    ' is read some other column and let it decide -- that is BUG-16, where
    ' Built? said "yes", which is not "No", and so nothing could ever be built.
    ReadDryRun = True
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(CONTROL_SHEET)
    On Error GoTo 0
    If sheet Is Nothing Then Exit Function

    Dim header As Long
    header = ControlHeaderRow(sheet)
    If header = 0 Then Exit Function

    Dim writeColumn As Long
    writeColumn = ControlColumn(sheet, header, COLUMN_WRITE)
    If writeColumn = 0 Then Exit Function

    Dim row As Long
    row = ControlRowFor(sheet, command)
    If row = 0 Then Exit Function

    ReadDryRun = (Fold(CStr(sheet.Cells(row, writeColumn).Value)) <> "yes")
End Function


Public Function ControlIsReadable(ByVal command As String) As String
    ' "" when the CONTROL sheet can be read, or a sentence saying what is
    ' missing. RunCommand refuses rather than falling back to a dry run,
    ' because a silent dry run is indistinguishable from Revit ignoring you --
    ' which is exactly how BUG-16 cost a test round.
    ControlIsReadable = ""
    Dim sheet As Worksheet
    On Error Resume Next
    Set sheet = ThisWorkbook.Worksheets(CONTROL_SHEET)
    On Error GoTo 0
    If sheet Is Nothing Then
        ControlIsReadable = "This workbook has no CONTROL sheet."
        Exit Function
    End If

    Dim header As Long
    header = ControlHeaderRow(sheet)
    If header = 0 Then
        ControlIsReadable = "The CONTROL sheet has no row headed " & _
                            COLUMN_COMMAND & "."
        Exit Function
    End If

    If ControlColumn(sheet, header, COLUMN_WRITE) = 0 Then
        ControlIsReadable = "The CONTROL sheet has no " & COLUMN_WRITE & _
                            " column, so there is no way to say whether to " & _
                            "write. Rebuild it with build_sample_project.py."
        Exit Function
    End If

    If ControlRowFor(sheet, command) = 0 Then
        ControlIsReadable = "The CONTROL sheet has no row for " & command & "."
    End If
End Function


' ---------------------------------------------------------------------------
' Setup: the two things openpyxl cannot put in the file
' ---------------------------------------------------------------------------

Public Sub AnonGeeBridge_AddButtons()
    ' Draw a button on every CONTROL row, and one on INFO for ApplyUnits.
    '
    ' Shapes, not Form Controls. The project owner replaced the form controls
    ' with rounded rectangles, and they are right: a shape takes the workbook
    ' font and the theme colours, and a form control takes neither.
    '
    ' This has to be re-runnable rather than done once, because openpyxl
    ' deletes every drawing in a workbook it rewrites. A rebuild keeps the
    ' macros and loses the buttons, so the buttons have to be redrawable.
    On Error GoTo Failed

    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(CONTROL_SHEET)

    Dim header As Long
    header = ControlHeaderRow(sheet)
    If header = 0 Then
        MsgBox "The CONTROL sheet has no row headed " & COLUMN_COMMAND & _
               ", so there is nothing to put buttons beside.", _
               vbExclamation, "AnonGee Bridge"
        Exit Sub
    End If

    Dim commandColumn As Long
    commandColumn = ControlColumn(sheet, header, COLUMN_COMMAND)
    If commandColumn = 0 Then Exit Sub

    ' Copy the template before deleting anything, because the template is
    ' usually one of the buttons about to be deleted.
    Dim template As Shape
    Set template = FindTemplate(sheet)

    RemoveOurButtons sheet
    RemoveOurButtons ThisWorkbook.Worksheets(INFO_SHEET)

    Dim made As Long
    Dim row As Long
    Dim command As String
    For row = header + 1 To header + 60
        command = Trim$(CStr(sheet.Cells(row, commandColumn).Value))
        If command <> "" Then
            If MacroFor(command) <> "" Then
                DrawButton sheet, sheet.Cells(row, commandColumn), template, _
                           BUTTON_PREFIX & Replace(command, ".", "_"), _
                           Prettify(command), MacroFor(command)
                made = made + 1
            End If
        End If
    Next row

    ' ApplyUnits belongs beside the unit it applies, not on CONTROL.
    Dim info As Worksheet
    Set info = ThisWorkbook.Worksheets(INFO_SHEET)
    DrawButton info, info.Cells(UnitsRow(info), 4), template, _
               BUTTON_PREFIX & "ApplyUnits", "ApplyUnits", _
               "AnonGeeBridge_ApplyUnits"
    made = made + 1

    Dim anchored As Long
    anchored = CountAnchored()

    MsgBox made & " button(s) drawn, " & anchored & " of them set to move " & _
           "and size with their cells." & vbCrLf & vbCrLf & _
           "Save the workbook. Run this again after any rebuild -- a rebuild " & _
           "keeps the macros and loses the drawings.", _
           vbInformation, "AnonGee Bridge"
    Exit Sub

Failed:
    MsgBox "Could not draw the buttons: " & Err.Description, _
           vbExclamation, "AnonGee Bridge"
End Sub


Private Function CountAnchored() As Long
    ' How many of our buttons actually took the anchoring, workbook-wide.
    On Error Resume Next
    Dim sheet As Worksheet
    Dim shape As Shape
    For Each sheet In ThisWorkbook.Worksheets
        For Each shape In sheet.Shapes
            If Left$(shape.Name, Len(BUTTON_PREFIX)) = BUTTON_PREFIX Then
                If shape.Placement = xlMoveAndSize Then
                    CountAnchored = CountAnchored + 1
                End If
            End If
        Next shape
    Next sheet
End Function


Private Function FindTemplate(ByVal sheet As Worksheet) As Shape
    ' The shape a new button is copied from, or Nothing to build one.
    '
    ' A shape named AnonGeeButton_Template wins, so the look can be changed by
    ' drawing one and naming it. Failing that, any button already on the sheet
    ' -- which is how the owner's own rounded rectangles become the house
    ' style without anybody writing their fill colour down in code.
    On Error Resume Next
    Dim candidate As Shape

    For Each candidate In sheet.Shapes
        If candidate.Name = BUTTON_TEMPLATE Then
            Set FindTemplate = candidate
            Exit Function
        End If
    Next candidate

    For Each candidate In sheet.Shapes
        If candidate.Type = msoAutoShape Then
            If Left$(candidate.Name, Len(BUTTON_PREFIX)) = BUTTON_PREFIX _
               Or candidate.OnAction <> "" Then
                Set FindTemplate = candidate
                Exit Function
            End If
        End If
    Next candidate
End Function


Private Sub DrawButton(ByVal sheet As Worksheet, ByVal cell As Range, _
                       ByVal template As Shape, ByVal name As String, _
                       ByVal caption As String, ByVal macro As String)
    ' One button over one cell, copied from the template when there is one.
    On Error Resume Next

    ' Duplicate when the template is on this sheet, build one when it is not.
    '
    ' Not Copy and Paste: pasting a shape needs its target sheet to be the
    ' active one, so a cross-sheet paste either fails or starts flicking the
    ' user between sheets while it works. Duplicate stays on one sheet, and
    ' INFO gets a built one that matches.
    Dim button As Shape
    Dim usable As Boolean
    usable = False
    If Not template Is Nothing Then
        usable = (template.Parent.Name = sheet.Name)
    End If

    If usable Then
        Set button = template.Duplicate
    Else
        Set button = sheet.Shapes.AddShape(msoShapeRoundedRectangle, _
                                           cell.Left + BUTTON_INSET, _
                                           cell.Top + BUTTON_INSET, _
                                           cell.Width - 2 * BUTTON_INSET, _
                                           cell.Height - 2 * BUTTON_INSET)
        StyleButton button
    End If

    button.Left = cell.Left + BUTTON_INSET
    button.Top = cell.Top + BUTTON_INSET
    button.Width = cell.Width - 2 * BUTTON_INSET
    button.Height = cell.Height - 2 * BUTTON_INSET

    button.Name = name
    button.TextFrame2.TextRange.Text = caption
    button.OnAction = macro
    button.Line.Weight = BUTTON_BORDER
    AnchorToCell button
End Sub


Public Function AnchorToCell(ByVal button As Shape) As Boolean
    ' Move and size with the cell underneath. ``True`` when it took.
    '
    ' Set, then read back, then say so. The previous version set it inside a
    ' blanket On Error Resume Next and never checked -- so when the buttons did
    ' not follow their cells there was no way to tell whether the line had run,
    ' failed, or been overwritten, and the next round would have been another
    ' guess. A property worth setting is a property worth verifying.
    '
    ' Two attempts, because they fail differently: the Shape property is the
    ' documented one, and the ShapeRange form goes through a different code
    ' path in Excel that has been known to work where the first does not.
    AnchorToCell = False
    On Error Resume Next

    button.Placement = xlMoveAndSize
    If button.Placement = xlMoveAndSize Then
        AnchorToCell = True
        Exit Function
    End If

    button.Parent.Shapes.Range(button.Name).Placement = xlMoveAndSize
    AnchorToCell = (button.Placement = xlMoveAndSize)
End Function


Public Sub AnonGeeBridge_AnchorButtons()
    ' Re-anchor every AnonGee button on every sheet, and report the count.
    '
    ' Separate from AddButtons so the anchoring can be tested on its own. If a
    ' button still will not follow its cell after this says it did, the cause
    ' is in Excel rather than in the macro, and that is worth being able to
    ' establish in one press.
    On Error GoTo Failed

    Dim anchored As Long
    Dim refused As Long
    Dim sheet As Worksheet
    Dim shape As Shape

    For Each sheet In ThisWorkbook.Worksheets
        For Each shape In sheet.Shapes
            If Left$(shape.Name, Len(BUTTON_PREFIX)) = BUTTON_PREFIX Then
                If AnchorToCell(shape) Then
                    anchored = anchored + 1
                Else
                    refused = refused + 1
                End If
            End If
        Next shape
    Next sheet

    Dim message As String
    message = anchored & " button(s) now move and size with their cells."
    If refused > 0 Then
        message = message & vbCrLf & vbCrLf & refused & " would not take it. " & _
                  "That is Excel refusing, not the macro skipping -- the " & _
                  "property was set and read back, and it did not stick."
    End If
    If anchored = 0 And refused = 0 Then
        message = "No AnonGee buttons found. Run AnonGeeBridge_AddButtons first."
    End If
    MsgBox message, vbInformation, "AnonGee Bridge"
    Exit Sub

Failed:
    MsgBox "Could not re-anchor: " & Err.Description, vbExclamation, _
           "AnonGee Bridge"
End Sub


Private Sub StyleButton(ByVal button As Shape)
    ' Only reached when there is no template to copy, which is what a rebuild
    ' leaves behind: openpyxl deletes every drawing in a workbook it rewrites,
    ' so the last button on the sheet goes with them and there is nothing to
    ' duplicate from.
    '
    ' These numbers are read off the buttons the project owner drew, so a
    ' rebuilt sheet looks like the one they styled rather than like a default:
    ' rounded rectangle, theme text-2 at 60% lightness, a one-point border of
    ' the same colour, and 10pt bold black centred text. Theme colours rather
    ' than fixed ones, so the buttons follow the workbook's theme if it changes.
    On Error Resume Next
    button.Fill.ForeColor.ObjectThemeColor = msoThemeColorText2
    button.Fill.ForeColor.Brightness = 0.6
    button.Line.ForeColor.ObjectThemeColor = msoThemeColorText2
    button.Line.Weight = BUTTON_BORDER
    With button.TextFrame2.TextRange.Font
        .Name = InstalledFont()
        .Size = SIZE_BODY
        .Bold = msoTrue
        .Fill.ForeColor.RGB = RGB(0, 0, 0)
    End With
    button.TextFrame2.TextRange.ParagraphFormat.Alignment = msoAlignCenter
    button.TextFrame2.VerticalAnchor = msoAnchorMiddle
End Sub


Private Sub RemoveOurButtons(ByVal sheet As Worksheet)
    ' Only ours, and only by name -- deleting every shape would take a logo or
    ' a note somebody put there. Form controls from the previous release go
    ' too, so a workbook does not end up wearing both.
    On Error Resume Next
    Dim index As Long
    For index = sheet.Shapes.Count To 1 Step -1
        If Left$(sheet.Shapes(index).Name, Len(BUTTON_PREFIX)) = BUTTON_PREFIX Then
            sheet.Shapes(index).Delete
        End If
    Next index
    For index = sheet.Buttons.Count To 1 Step -1
        If Left$(sheet.Buttons(index).Name, Len(BUTTON_PREFIX)) = BUTTON_PREFIX Then
            sheet.Buttons(index).Delete
        End If
    Next index
    On Error GoTo 0
End Sub


Public Function Prettify(ByVal command As String) As String
    ' "levels.sync" -> "Levels.sync". The caption is derived from the command
    ' rather than kept beside it, so the two can never drift apart.
    If command = "" Then
        Prettify = ""
    Else
        Prettify = UCase$(Left$(command, 1)) & Mid$(command, 2)
    End If
End Function


Public Function UnitsRow(ByVal info As Worksheet) As Long
    ' The row on INFO whose key is UNITS, or 1.
    UnitsRow = 1
    Dim row As Long
    For row = 1 To HEADER_SEARCH_ROWS
        If Fold(StripUnit(CStr(info.Cells(row, 1).Value))) = Fold(INFO_UNITS_KEY) Then
            UnitsRow = row
            Exit Function
        End If
    Next row
End Function


Public Function MacroFor(ByVal command As String) As String
    ' The macro that runs a command. One place, so a button and a test can
    ' both ask rather than each keeping its own copy of the mapping.
    Select Case LCase$(Trim$(command))
        Case "bridge.echo":    MacroFor = "Run_Echo"
        Case "levels.sync":    MacroFor = "Run_Levels"
        Case "grids.sync":     MacroFor = "Run_Grids"
        Case "footings.sync":  MacroFor = "Run_Footings"
        Case "columns.sync":   MacroFor = "Run_Columns"
        Case "beams.sync":     MacroFor = "Run_Beams"
        Case "slabs.sync":     MacroFor = "Run_Slabs"
        Case Else:             MacroFor = ""
    End Select
End Function


Public Sub AnonGeeBridge_ApplyUnits()
    ' Convert every length in the workbook to the unit chosen on INFO.
    '
    ' Which cells are lengths is not a list kept somewhere -- it is written in
    ' the header. A column headed "Elevation (m)" is a length in metres, and
    ' this scales its values, its number format and its header. So the unit is
    ' visible where the number is, a column somebody adds is converted the
    ' moment they label it, and running this twice does nothing the second
    ' time.
    '
    ' Two shapes of sheet, because INFO is not a column table: it is key,
    ' value, description in rows. Its keys carry the unit instead, and it used
    ' to be walked straight past. BUG-17.
    On Error GoTo Failed

    Dim wanted As String
    wanted = ReadUnits()

    Dim converted As Long
    Dim sheet As Worksheet
    For Each sheet In ThisWorkbook.Worksheets
        If sheet.Name = INFO_SHEET Then
            converted = converted + ConvertKeyedRows(sheet, wanted)
        Else
            converted = converted + ConvertSheetUnits(sheet, wanted)
        End If
    Next sheet

    MsgBox converted & " column(s) and value(s) are now in " & wanted & _
           "." & vbCrLf & vbCrLf & _
           "A cell is converted when its header, or its key on INFO, names " & _
           "its unit -- like Elevation (mm). Cover and diameter stay in mm " & _
           "whatever this is set to, because 0.05 does not read.", _
           vbInformation, "AnonGee Bridge"
    Exit Sub

Failed:
    MsgBox "Could not convert: " & Err.Description, vbExclamation, _
           "AnonGee Bridge"
End Sub


Private Function ConvertSheetUnits(ByVal sheet As Worksheet, _
                                   ByVal wanted As String) As Long
    ' Every header on this sheet carrying a unit, scaled to the wanted one.
    ConvertSheetUnits = 0

    Dim lastRow As Long
    Dim lastColumn As Long
    lastRow = sheet.UsedRange.row + sheet.UsedRange.Rows.Count - 1
    lastColumn = sheet.UsedRange.column + sheet.UsedRange.Columns.Count - 1
    If lastRow < 2 Then Exit Function

    Dim row As Long
    Dim column As Long
    Dim head As String
    Dim found As String
    Dim target As String
    For row = 1 To Application.Min(HEADER_SEARCH_ROWS, lastRow)
        For column = 1 To lastColumn
            head = CStr(sheet.Cells(row, column).Value)
            found = UnitInHeader(head)
            If found <> "" Then
                target = UnitFor(head, wanted)
                If found <> target Then
                    ScaleColumn sheet, row, column, lastRow, _
                                UnitFactor(found, target), target
                    sheet.Cells(row, column).Value = _
                        Replace(head, "(" & found & ")", "(" & target & ")")
                    ConvertSheetUnits = ConvertSheetUnits + 1
                End If
            End If
        Next column
    Next row
End Function


Private Function ConvertKeyedRows(ByVal sheet As Worksheet, _
                                  ByVal wanted As String) As Long
    ' INFO: the key in column A names the unit of the value in column B.
    ConvertKeyedRows = 0

    Dim lastRow As Long
    lastRow = sheet.UsedRange.row + sheet.UsedRange.Rows.Count - 1

    Dim row As Long
    Dim key As String
    Dim found As String
    Dim target As String
    For row = 1 To lastRow
        key = CStr(sheet.Cells(row, 1).Value)
        found = UnitInHeader(key)
        If found <> "" Then
            target = UnitFor(key, wanted)
            If found <> target Then
                If IsNumeric(sheet.Cells(row, 2).Value) Then
                    sheet.Cells(row, 2).Value = _
                        sheet.Cells(row, 2).Value * UnitFactor(found, target)
                    sheet.Cells(row, 2).NumberFormat = FormatFor(target)
                End If
                sheet.Cells(row, 1).Value = _
                    Replace(key, "(" & found & ")", "(" & target & ")")
                ConvertKeyedRows = ConvertKeyedRows + 1
            End If
        End If
    Next row
End Function


Public Function UnitInHeader(ByVal head As String) As String
    ' "mm", "m", or "" -- the unit a header declares in brackets.
    Dim folded As String
    folded = Fold(head)
    If InStr(folded, "(mm)") > 0 Then
        UnitInHeader = "mm"
    ElseIf InStr(folded, "(m)") > 0 Then
        UnitInHeader = "m"
    Else
        UnitInHeader = ""
    End If
End Function


Public Function StripUnit(ByVal head As String) As String
    ' A header without its unit: "Elevation PBP (m)" -> "Elevation PBP".
    Dim at As Long
    at = InStr(head, "(")
    If at > 1 Then
        StripUnit = Trim$(Left$(head, at - 1))
    Else
        StripUnit = Trim$(head)
    End If
End Function


Public Function IsPinned(ByVal head As String) As String
    ' "mm" for a column that stays in millimetres, "" for one that converts.
    IsPinned = ""
    Dim name As String
    name = Fold(StripUnit(head))

    Dim prefixes() As String
    prefixes = Split(PINNED_TO_MM, ",")

    Dim index As Long
    For index = LBound(prefixes) To UBound(prefixes)
        If Left$(name, Len(prefixes(index))) = prefixes(index) Then
            IsPinned = "mm"
            Exit Function
        End If
    Next index
End Function


Public Function UnitFor(ByVal head As String, ByVal wanted As String) As String
    ' What unit this particular column should end up in.
    If IsPinned(head) <> "" Then
        UnitFor = "mm"
    Else
        UnitFor = wanted
    End If
End Function


Public Function FormatFor(ByVal units As String) As String
    ' Millimetres whole, metres to two decimals.
    If units = "mm" Then
        FormatFor = FORMAT_MM
    Else
        FormatFor = FORMAT_M
    End If
End Function


Public Function UnitFactor(ByVal from As String, ByVal wanted As String) As Double
    ' What to multiply a number in `from` by to get one in `wanted`.
    UnitFactor = 1
    If from = wanted Then Exit Function
    If from = "mm" And wanted = "m" Then UnitFactor = 0.001
    If from = "m" And wanted = "mm" Then UnitFactor = 1000
End Function


Private Sub ScaleColumn(ByVal sheet As Worksheet, ByVal header As Long, _
                        ByVal column As Long, ByVal lastRow As Long, _
                        ByVal factor As Double, ByVal units As String)
    ' Numbers only. A blank stays blank and a word stays a word -- a cell
    ' reading "as drawn" is an instruction, not a length, and multiplying it
    ' by a thousand would lose it.
    Dim row As Long
    For row = header + 1 To lastRow
        If IsNumeric(sheet.Cells(row, column).Value) Then
            If Trim$(CStr(sheet.Cells(row, column).Value)) <> "" Then
                If factor <> 1 Then
                    sheet.Cells(row, column).Value = _
                        sheet.Cells(row, column).Value * factor
                End If
                sheet.Cells(row, column).NumberFormat = FormatFor(units)
            End If
        End If
    Next row
End Sub


Public Sub AnonGeeBridge_ApplyFormat()
    ' The font, the row heights and the column widths, on every sheet.
    '
    ' The build writes Inter, and a machine without Inter shows whatever Excel
    ' substitutes. This picks the first font in the stack that is actually
    ' installed here, which is the nearest thing a spreadsheet has to the
    ' font fallback a stylesheet would give you.
    On Error GoTo Failed

    Dim face As String
    face = InstalledFont()

    Dim sheet As Worksheet
    For Each sheet In ThisWorkbook.Worksheets
        sheet.Cells.Font.Name = face
        sheet.Rows.RowHeight = ROW_HEIGHT
        sheet.UsedRange.Columns.AutoFit
    Next sheet

    MsgBox "Set in " & face & ", every row " & ROW_HEIGHT & " units, every " & _
           "column fitted to what is in it.", vbInformation, "AnonGee Bridge"
    Exit Sub

Failed:
    MsgBox "Could not format: " & Err.Description, vbExclamation, _
           "AnonGee Bridge"
End Sub


Public Function InstalledFont() As String
    ' The first font in FONT_STACK this machine actually has.
    '
    ' Excel stores one font name per cell and has no fallback list, so the
    ' fallback has to happen once, here, rather than at render time.
    Dim names() As String
    names = Split(FONT_STACK, ",")
    InstalledFont = Trim$(names(UBound(names)))

    Dim index As Long
    For index = LBound(names) To UBound(names)
        If FontExists(Trim$(names(index))) Then
            InstalledFont = Trim$(names(index))
            Exit Function
        End If
    Next index
End Function


Private Function FontExists(ByVal name As String) As Boolean
    ' Ask Excel for the font list. Wrapped, because the control this reads
    ' from is not present in every host and a missing font list should mean
    ' "use the last name in the stack", not a broken macro.
    FontExists = False
    On Error Resume Next
    Dim listed As Variant
    listed = Application.CommandBars("Formatting").Controls("Font").List
    On Error GoTo 0
    If IsEmpty(listed) Then Exit Function

    Dim index As Long
    For index = LBound(listed) To UBound(listed)
        If StrComp(CStr(listed(index)), name, vbTextCompare) = 0 Then
            FontExists = True
            Exit Function
        End If
    Next index
End Function
