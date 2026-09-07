# AnonGee Authenticode Signing

Pipeline version: **0.7.0**  
Adoption status: **Implemented / Deferred**

The Authenticode release path is implemented and retained in the repository, but it is **not a release blocker** for the current sole-developer deployment. Public signing adoption is deferred until AnonGee has a publicly trusted code-signing identity or supported managed signing service that is financially justified.

The normal unsigned release path remains:

```powershell
py -3.12 .\installer\build_release.py
```

When public signing is adopted later, the existing signed path is:

```powershell
py -3.12 .\installer\build_signed_release.py
```

No production certificate is currently assumed or required by the repository. Do not produce or describe an artifact as a publicly trusted signed release unless the signed pipeline completes with a real Code Signing identity and final Authenticode verification.

## Why signing is separate

A developer must be able to build and test AnonGee without possessing the production private key. Private signing material therefore does not belong in the repository and is not required by `build_release.py`.

`build_signed_release.py` is reserved for formal signed distributable builds once the signing identity is provisioned. Keeping it implemented now avoids rebuilding the release engineering later, while deferring the recurring or certificate cost until it is useful.

## Required tools for the signed path

- Windows x64
- Inno Setup 7
- Microsoft `SignTool.exe` from a current Windows SDK
- A valid Code Signing certificate with its private key available in either:
  - `Cert:\CurrentUser\My` (default), or
  - `Cert:\LocalMachine\My` (`--machine-store`)
- Network access to an RFC 3161 timestamp server

`SignTool.exe` and the Windows SDK are build tools; having them installed does **not** by itself provide a publicly trusted publisher identity. The current work machine already has the Windows SDK x64 SignTool available, so the deferred dependency is the signing identity rather than the executable.

The pipeline automatically searches the Windows SDK and prefers the newest available `x64\signtool.exe`. A typical SDK installation looks like:

```text
C:\Program Files (x86)\Windows Kits\10\bin\<SDK-version>\x64\signtool.exe
```

To inspect installed copies:

```powershell
Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" `
  -Filter signtool.exe `
  -Recurse `
  -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty FullName
```

The pipeline uses:

```text
file digest      SHA256
timestamp mode   RFC 3161
timestamp digest SHA256
```

The default timestamp endpoint is:

```text
http://timestamp.digicert.com
```

Override it with `--timestamp-url` or `ANONGEE_TIMESTAMP_URL` when your certificate provider or company requires another RFC 3161 endpoint.

## Private-key policy

Do **not** commit a PFX/P12/PVK/private key to Git.

`.gitignore` blocks common private signing-key containers and `installer/signing/private/`.

The preferred release workflow uses the Windows certificate store by certificate thumbprint. This also supports certificates whose private keys are non-exportable or hardware-backed.

## Find your certificate

Current-user store:

```powershell
Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.HasPrivateKey } |
  Select-Object Subject, Thumbprint, NotAfter, EnhancedKeyUsageList
```

Machine store:

```powershell
Get-ChildItem Cert:\LocalMachine\My |
  Where-Object { $_.HasPrivateKey } |
  Select-Object Subject, Thumbprint, NotAfter, EnhancedKeyUsageList
```

The certificate must include the Code Signing EKU:

```text
1.3.6.1.5.5.7.3.3
```

## Configure the certificate

For the current PowerShell session:

```powershell
$env:ANONGEE_SIGN_CERT_SHA1 = "YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT"
```

Optional timestamp override:

```powershell
$env:ANONGEE_TIMESTAMP_URL = "https://your-rfc3161-timestamp-server"
```

If the certificate is in `LocalMachine\My`:

```powershell
$env:ANONGEE_SIGN_MACHINE_STORE = "1"
```

## Build a signed release

Only use this section after a real signing identity has been provisioned.

From the repository root, with a clean Git worktree:

```powershell
py -3.12 .\installer\build_signed_release.py
```

Or pass the thumbprint explicitly:

```powershell
py -3.12 .\installer\build_signed_release.py `
  --cert-sha1 "YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT"
```

If SignTool is not found automatically:

```powershell
py -3.12 .\installer\build_signed_release.py `
  --cert-sha1 "YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT" `
  --signtool "C:\Program Files (x86)\Windows Kits\10\bin\<SDK>\x64\signtool.exe"
```

## What the pipeline verifies

Before compilation it reuses the complete 0.6.0 contract:

- clean source state
- aligned extension / changelog / Setup product version
- minimum pyRevit metadata
- pinned pyRevit prerequisite filename and SHA-256
- Inno Setup 7
- verified payload/native-runtime integrity

0.7.0 additionally verifies:

- Microsoft SignTool is available
- the selected certificate exists in the requested Windows store
- the certificate has a private key
- the certificate has the Code Signing EKU
- Inno invokes Authenticode signing during compilation
- `SignedUninstaller=yes` is active through `signing-authenticode.iss`
- the final Setup EXE passes:

```text
signtool verify /pa /all /v
```

Only after that succeeds is `release-manifest.json` upgraded to schema 1.2.0 and marked with Authenticode evidence.

## Manifest additions

A successful signed build records an `authenticode` object containing:

- certificate subject
- certificate SHA-1 thumbprint
- certificate store location
- certificate expiration time
- SignTool path
- SHA-256 file digest
- RFC 3161 timestamp URL
- SHA-256 timestamp digest
- final Setup signature verification status
- confirmation that Inno was asked to sign its uninstaller

The Setup EXE's SHA-256 in the manifest is the hash of the **already-signed and timestamped** artifact.

## Certificate acquisition

The repository and build scripts do not create or distribute a publicly trusted code-signing identity. For public/company distribution, obtain an appropriate Code Signing certificate or supported managed signing service from a trusted provider, then configure its signing identity for this pipeline.

Self-signed certificates are useful only for controlled internal testing where the receiving machines explicitly trust your test certificate. They do not provide normal public Windows publisher trust or SmartScreen reputation.

Until that purchase/provisioning is justified, keep using the unsigned release pipeline and leave the 0.7.0 signed path dormant but maintained.
