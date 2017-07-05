@Echo OFF

set OGRECLIENT_VERSION=0.0.2

if not exist "WinPython.exe" (
  powershell -Command "(New-Object System.Net.WebClient).DownloadFile('https://github.com/winpython/winpython/releases/download/1.6.20160828/WinPython-64bit-2.7.12.3Zero.exe', 'WinPython.exe')" <NUL
)

if not exist "WinPython-64bit-2.7.12.3Zero" (
  Echo Accept WinPython licence and extract into the current directory..
  WinPython.exe
)

@echo call env.bat> WinPython-64bit-2.7.12.3Zero\scripts\install_ogre.bat
@echo pip install ..\..\ogreclient-%OGRECLIENT_VERSION%.zip>> WinPython-64bit-2.7.12.3Zero\scripts\install_ogre.bat
@echo ogre init>> WinPython-64bit-2.7.12.3Zero\scripts\install_ogre.bat

rmdir /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\Doc
rmdir /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\Logs
rmdir /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\Tools
rmdir /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\tcl
rmdir /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\Lib\test
del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\NEWS.txt
del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\DLLs\_bsddb.pyd
REM del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\DLLs\sqlite3.dll
del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\DLLs\tcl85.dll
del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\DLLs\tclpip85.dll
del /F /S /Q WinPython-64bit-2.7.12.3Zero\python-2.7.12.amd64\DLLs\tk85.dll

call WinPython-64bit-2.7.12.3Zero\scripts\env.bat

pip uninstall -y docopt idlex jedi prompt-toolkit ptpython Pygments pythonnet six sqlite-bro wcwidth winpython

if not exist "calibre.exe" (
  powershell -Command "(New-Object System.Net.WebClient).DownloadFile('https://calibre-ebook.com/dist/portable', 'calibre.exe')" <NUL
)

if not exist "Calibre Portable" (
  calibre.exe .
)

pushd ..
C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe /t:Build /p:Configuration=Release /p:TargetFramework=v4.0 /m
popd

"C:\Program Files (x86)\Inno Setup 5\ISCC.exe" /Qp install.iss

REM robocopy Z:\-vagrant\OGRE C:\Users\vagrant\Desktop\OGRE /E /FP /PURGE
