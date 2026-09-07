# AnonGee Authenticode Signing

Pipeline milestone: **0.7.0**  
Public-trust adoption: **Deferred**  
Self-signed local validation: **Implemented; awaiting workstation proof**

The 0.7.0 Authenticode path can now be exercised end-to-end at no certificate cost using a self-signed development certificate. This validates SignTool discovery, SHA-256 signing, RFC 3161 timestamping, Inno Setup signing of Setup + uninstaller, and final Windows Authenticode verification.

A self-signed build is **not** a public release. The pipeline marks it `release_ready: false`, renames the EXE with `-SELF-SIGNED-TEST`, and writes `test-signing-manifest.json`. A self-signed identity is rejected by the formal signed-release path unless `--allow-self-signed-test` is explicitly supplied.

Public/company signing remains deferred until a publicly trusted code-signing certificate or managed signing service is financially justified.

## Normal unsigned release

The ordinary release builder does not require any certificate:

```powershell
py -3.12 .\installer\build_release.py
```

## Free local Authenticode validation

Microsoft's `New-SelfSignedCertificate` supports a `CodeSigningCert` certificate type. AnonGee keeps the private key non-exportable in the current user's Windows certificate store and does not create a PFX.

From the repository root:

```powershell
$cert = & .\installer\create_test_signing_certificate.ps1 `
    -TrustForLocalVerification

$env:ANONGEE_SIGN_CERT_SHA1 = $cert.Thumbprint

py -3.12 .\installer\build_signed_release.py `
    --allow-self-signed-test
```

`-TrustForLocalVerification` imports only the public certificate into `Cert:\CurrentUser\Root`. That makes the self-signed test identity trusted **on this Windows user account**, which is required for `signtool verify /pa` to succeed. It does not make the publisher trusted on another PC and does not create SmartScreen reputation.

Expected test outputs:

```text
installer\output\AnonGee-Setup-<product-version>-SELF-SIGNED-TEST.exe
installer\output\test-signing-manifest.json
```

The manifest must contain:

```text
release_ready = false
authenticode.signing_profile = self-signed-test
authenticode.local_windows_policy_verified = true
authenticode.certificate.self_signed = true
```

Before a self-signed build starts, it protects both production-named release records. If either of these already exists, the test build refuses to continue:

```text
installer\output\AnonGee-Setup-<product-version>.exe
installer\output\release-manifest.json
```

Archive or move the existing EXE **and** its manifest first. This prevents a local test from silently replacing any earlier artifact or evidence record that uses the same product version.

## Remove the development certificate later

Use the thumbprint printed by the provisioning script:

```powershell
$thumb = "YOUR_40_CHARACTER_THUMBPRINT"
Remove-Item "Cert:\CurrentUser\Root\$thumb" -ErrorAction SilentlyContinue
Remove-Item "Cert:\CurrentUser\My\$thumb" -ErrorAction SilentlyContinue
```

Removing the Trusted Root copy removes local trust. Removing the `My` copy also removes access to its private key.

## Required tools

- Windows x64
- Inno Setup 7
- Microsoft `SignTool.exe` from a current Windows SDK
- a Code Signing certificate in `Cert:\CurrentUser\My` or `Cert:\LocalMachine\My`
- network access to an RFC 3161 timestamp server

The current work machine already has Windows SDK SignTool copies including the x64 build under the normal SDK layout. The pipeline automatically searches the SDK and prefers the newest available `x64\signtool.exe`:

```text
C:\Program Files (x86)\Windows Kits\10\bin\<SDK-version>\x64\signtool.exe
```

The installed executable itself is free; public publisher trust is the deferred paid dependency.

## Cryptographic contract

```text
file digest      SHA256
timestamp mode   RFC 3161
timestamp digest SHA256
```

Default timestamp endpoint:

```text
http://timestamp.digicert.com
```

Override it with `--timestamp-url` or `ANONGEE_TIMESTAMP_URL` if necessary.

The final Setup EXE is checked with:

```text
signtool verify /pa /all /v
```

A self-signed test certificate must therefore be in the local Trusted Root store for this verification to pass.

## Private-key policy

Do **not** commit a PFX/P12/PVK/private key to Git.

`.gitignore` blocks common private signing-key containers and `installer/signing/private/`. The self-signed helper uses `-KeyExportPolicy NonExportable` and does not call `Export-PfxCertificate`.

The formal workflow selects a certificate from the Windows certificate store by SHA-1 thumbprint. This also supports future hardware-backed/non-exportable production identities without changing installer signing commands.

## Formal signed release — future

When a real signing identity is provisioned:

```powershell
$env:ANONGEE_SIGN_CERT_SHA1 = "YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT"
py -3.12 .\installer\build_signed_release.py
```

The certificate must have a private key and the Code Signing EKU:

```text
1.3.6.1.5.5.7.3.3
```

The formal path rejects a self-signed certificate. It signs both Setup and Inno's embedded uninstaller, timestamps them, verifies the resulting Setup with Windows Authenticode policy, and only then promotes the manifest as release-ready.

## Manifest contract

Signing manifest schema is **1.3.0**. Authenticode evidence records:

- certificate subject, issuer, SHA-1 thumbprint, store and expiration;
- whether the certificate is self-signed;
- SignTool path;
- SHA-256 file digest;
- RFC 3161 timestamp URL and SHA-256 timestamp digest;
- final Setup signature verification;
- confirmation that Inno was asked to sign its uninstaller;
- signing profile (`self-signed-test` or `formal`).

Self-signed test mode can never set `release_ready: true`.

## Public trust remains deferred

The repository can create a **development self-signed identity**, but it does not create or distribute a **publicly trusted code-signing identity**. Self-signed certificates are suitable only for controlled local/internal validation where the receiving machine explicitly trusts that certificate.

For future external distribution, obtain an appropriate Code Signing certificate or supported managed signing service from a trusted provider, then configure its identity for the existing formal pipeline.
