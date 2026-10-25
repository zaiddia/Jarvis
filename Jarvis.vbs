' Inicia Jarvis sin ninguna ventana de consola.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
exe = dir & "\dist\jarvis\jarvis.exe"
pyw = dir & "\.venv\Scripts\pythonw.exe"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
' Si hay un .exe compilado pero el codigo es mas nuevo (actualizaste sin recompilar),
' se usa el codigo para no abrir sin querer una version vieja.
useExe = fso.FileExists(exe)
If useExe And fso.FileExists(pyw) And fso.FileExists(dir & "\jarvis.py") Then
  If fso.GetFile(dir & "\jarvis.py").DateLastModified > fso.GetFile(exe).DateLastModified Then useExe = False
End If
If useExe Then
  sh.Run """" & exe & """", 0, False
ElseIf fso.FileExists(pyw) Then
  sh.Run """" & pyw & """ """ & dir & "\jarvis.py""", 0, False
Else
  MsgBox "No se encontró la instalación de Jarvis. Ejecuta primero instalar.bat.", 48, "Jarvis"
End If
