; Trading Terminal Windows Installer
; Usage: makensis.exe /DVERSION=1.0.0 installer.nsi

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APPNAME "Trading-Terminal"
!define COMPANY "Trading-Terminal"

Name "${APPNAME}"
OutFile "..\dist\Trading-Terminal-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "..\dist\Trading-Terminal\*.*"

    ; Data directories in LOCALAPPDATA
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\actions"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\stocks"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\daily_dump"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\hot_rank"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\dragon_tiger"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\dragon_tiger_seats"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\billboard"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\northbound"
    CreateDirectory "$LOCALAPPDATA\${APPNAME}\data\sector_flow"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\Trading-Terminal.lnk" "$INSTDIR\Trading-Terminal.exe"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\卸载.lnk" "$INSTDIR\uninstall.exe"

    ; Desktop shortcut
    CreateShortCut "$DESKTOP\Trading-Terminal.lnk" "$INSTDIR\Trading-Terminal.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Registry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "Publisher" "${COMPANY}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" \
        "NoRepair" 1

    ; DPI awareness
    WriteRegStr HKCU "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" \
        "$INSTDIR\Trading-Terminal.exe" "~ DPIUNAWARE"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    Delete "$SMPROGRAMS\${APPNAME}\Trading-Terminal.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\卸载.lnk"
    RMDir "$SMPROGRAMS\${APPNAME}"
    Delete "$DESKTOP\Trading-Terminal.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
