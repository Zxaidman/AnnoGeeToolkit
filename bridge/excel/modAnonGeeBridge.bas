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
    BridgeUrl = "http://" & BRIDGE_HOST & ":" & CStr(BRIDGE_PORT) & _
                "/" & BRIDGE_API & "/" & route
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
' It finds the first "key": value pair and returns the value as text. Good
' enough to put four fields in four cells for a spike, and no further. VBA has
' no JSON parser; the real bridge needs one, and writing half of it here would
' be the worst of both -- so this is deliberately named for what it is not.

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
        closing = InStr(2, rest, """")
        If closing = 0 Then
            JsonValue = ""
        Else
            JsonValue = Mid$(rest, 2, closing - 2)
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


Public Sub RunCommand(ByVal command As String, ByVal sheetName As String)
    ' The workbook on disk is what Revit reads, so it has to be the workbook
    ' you are looking at. Saving first is not a courtesy, it is the contract.
    On Error Resume Next
    ThisWorkbook.Save
    On Error GoTo 0

    Dim dryRun As Boolean
    dryRun = ReadDryRun(command)

    Dim reply As String
    reply = HttpPost(BridgeUrl("jobs"), JobJson(command, sheetName, dryRun))

    Dim jobId As String
    jobId = JsonValue(reply, "jobId")
    If jobId = "" Then
        ' No id means the post never reached a route. Say which of the two
        ' halves is missing rather than showing the raw error and leaving the
        ' user to guess -- they are different switches in different places.
        If InStr(reply, """ok"": false") > 0 Then
            MsgBox "Nothing is listening at " & BridgeUrl("jobs") & vbCrLf & _
                   vbCrLf & _
                   "In Revit: pyRevit Settings -> Routes -> Routes Server " & _
                   "(Beta), then restart Revit." & vbCrLf & vbCrLf & _
                   "Then AnonGee tab -> Dev -> Bridge Check, which says " & _
                   "whether the startup script ran." & vbCrLf & vbCrLf & _
                   Left$(reply, 300), vbExclamation, "AnonGee Bridge"
            LogRow "", command, "unreachable", "", Left$(reply, 200)
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
               "no result after " & GIVE_UP_AFTER_SECONDS & "s — the job may " & _
               "still be running. Is Bridge Listener switched on in Revit?"
        MsgBox "Queued as " & jobId & ", but no result yet." & vbCrLf & vbCrLf & _
               "Is Bridge Listener switched on in Revit?", _
               vbInformation, "AnonGee Bridge"
        Exit Sub
    End If

    WriteResult command, body
End Sub


Private Function JobJson(ByVal command As String, ByVal sheetName As String, _
                         ByVal dryRun As Boolean) As String
    ' Built by hand because it is four fields. Anything larger belongs in a
    ' sheet Revit reads for itself -- the envelope carries which sheet, never
    ' the data.
    JobJson = "{""envelope"": ""1.0""" & _
              ", ""command"": """ & command & """" & _
              ", ""workbook"": """ & JsonEscape(ThisWorkbook.FullName) & """" & _
              ", ""sheet"": """ & sheetName & """" & _
              ", ""options"": {""dryRun"": " & LCase$(CStr(dryRun)) & "}}"
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
    ShowFindings body

    MsgBox command & ": " & status & vbCrLf & vbCrLf & _
           Trim$(counts) & vbCrLf & note & vbCrLf & vbCrLf & _
           findings & " finding(s) — see the FINDINGS sheet.", _
           vbInformation, "AnonGee Bridge"
End Sub


Private Sub ShowFindings(ByVal body As String)
    Dim sheet As Worksheet
    Set sheet = EnsureSheet("FINDINGS")
    sheet.Cells.Clear

    Dim lines() As String
    lines = Split(Replace(body, vbCrLf, vbLf), vbLf)

    Dim writing As Boolean
    Dim row As Long
    row = 1

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

    sheet.Rows(1).Font.Bold = True
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
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets("CONTROL")
    On Error GoTo 0
    If sheet Is Nothing Then Exit Sub

    Dim row As Long
    For row = 1 To 60
        If sheet.Cells(row, 2).Value = command Then
            sheet.Cells(row, 6).Value = status
            sheet.Cells(row, 7).Value = Now
            sheet.Cells(row, 8).Value = note
            Exit For
        End If
    Next row
End Sub


Private Function ReadDryRun(ByVal command As String) As Boolean
    ReadDryRun = True                       ' nothing is written unless asked
    On Error Resume Next
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets("CONTROL")
    On Error GoTo 0
    If sheet Is Nothing Then Exit Function

    Dim row As Long
    For row = 1 To 60
        If sheet.Cells(row, 2).Value = command Then
            ReadDryRun = (UCase$(Trim$(CStr(sheet.Cells(row, 5).Value))) <> "NO")
            Exit Function
        End If
    Next row
End Function
