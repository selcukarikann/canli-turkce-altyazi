; Canlı Türkçe Altyazı - kurulum betiği (Inno Setup 6)
; Derleme:  ISCC.exe kurulum.iss   ->  dist\CanliTurkceAltyazi-Kurulum-1.0.0.exe
; Önce uygulama paketlenmiş olmalı (dist\CanliTurkceAltyazi klasörü).

#define UygulamaAdi "Canlı Türkçe Altyazı"
#define Surum "1.0.0"
#define ExeAdi "CanliTurkceAltyazi.exe"

[Setup]
AppId={{7C2B5E4A-93D1-4F6E-B8A7-2D5C1E9F4A63}
AppName={#UygulamaAdi}
AppVersion={#Surum}
AppVerName={#UygulamaAdi} {#Surum}
DefaultDirName={autopf}\CanliTurkceAltyazi
DefaultGroupName={#UygulamaAdi}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=CanliTurkceAltyazi-Kurulum-{#Surum}
SetupIconFile=simge.ico
UninstallDisplayIcon={app}\{#ExeAdi}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
; Yönetici izni istemeden, yalnızca bu kullanıcı için kurulabilir
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Ek kısayollar:"

[Files]
Source: "dist\CanliTurkceAltyazi\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "BENIOKU.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Parameters: "--tam-ekran"
Name: "{group}\{#UygulamaAdi} (pencere)"; Filename: "{app}\{#ExeAdi}"
Name: "{group}\Kullanım bilgisi"; Filename: "{app}\BENIOKU.txt"
Name: "{autodesktop}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Parameters: "--tam-ekran"; Tasks: desktopicon

[Run]
Filename: "{app}\BENIOKU.txt"; Description: "Kullanım bilgisini aç"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\{#ExeAdi}"; Description: "{#UygulamaAdi} programını başlat"; Flags: postinstall nowait skipifsilent
