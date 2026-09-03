; AnonGee Authenticode signing overlay
;
; Included only by installer/build_signed_release.py. Keeping signing out of the
; base AnonGee.iss means ordinary installer development does not require access
; to the private code-signing key, while a signed release can still use Inno's
; native signing path for BOTH Setup and the embedded uninstaller.
;
; The named tool is supplied to ISCC on the command line with
; --signtool=AnonGeeAuthenticode=<command>.

[Setup]
SignTool=AnonGeeAuthenticode
SignedUninstaller=yes
