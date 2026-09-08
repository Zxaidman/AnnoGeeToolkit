# AnonGee Authenticode Signing

Authenticode milestone: **0.7.0 — workstation-proven**  
Current integrated release pipeline: **0.8.0**  
Current signed manifest schema: **1.4.0**  
Public-trust adoption: **Deferred**  
Self-signed certificate provisioning: **Proven on the Windows workstation**  
Self-signed end-to-end signed build: **Passed for product 2.0.0 on the Windows workstation (2026-09-08)**

The Authenticode capability was introduced and proven in 0.7.0. Release pipeline 0.8.0 keeps the same signing, timestamping, and verification contract and adds lifecycle/version safety around it.

A self-signed build is **not** a public release. The pipeline marks it `release_ready: false`, renames the EXE with `-SELF-SIGNED-TEST`, and writes `test-signing-manifest.json`. A self-signed identity is rejected by the formal signed-release path unless `--allow-self-signed-test` is explicitly supplied.

Public/company signing remains deferred until a publicly trusted code-signing certificate or managed signing service is financially justified.

## Workstation proof

The free/self-signed 0.7.0 path was proven end to end on the Windows development workstation on 2026-09-07.

Observed gates:

```text
Signing contract tests                         PASS
Inno Setup 7 compile                           PASS
Windows SDK x64 SignTool discovery             PASS
Self-signed Code Signing certificate           PASS
SHA-256 Authenticode signing                   PASS
RFC 3161 timestamping                          PASS
Inno Setup + embedded uninstaller signing      PASS
signtool verify /pa /all /v                    PASS
Final self-signed test manifest                release_ready = false
```

Observed original 0.7 proof artifact:

```text
AnonGee-Setup-1.26.1-SELF-SIGNED-TEST.exe
Size:    110.74 MiB
SHA-256: f309f75d09ba2bc3a8ee1c613b733642cba4cf74e62da9e660c2afdd355a4395
```

That hash identifies only this self-signed validation artifact. It is **not** the historical official `1.26.1` release artifact and must not be published as one.

The integrated 0.8 pipeline was also exercised successfully before the 2.0.0 candidate bump:

```text
AnonGee-Setup-1.26.1-SELF-SIGNED-TEST.exe
Size:    110.74 MiB
SHA-256: 5f94ec9c9e4bdfcc7162500737fa33fd2c1691c60eebf987ca384bd246972315
Release ready: NO — self-signed local test only
```

The current product `2.0.0` candidate was then proven end to end on 2026-09-08 with the full 0.8 lifecycle integration enabled:

```text
AnonGee-Setup-2.0.0-SELF-SIGNED-TEST.exe
Size:    110.75 MiB
SHA-256: 1e6278cec11142fc4275eba90d063dfb1dd506f27191238c5d628c3c1266df1e
SignTool /pa verification: PASS
Release ready: NO — self-signed local test only
```

This 2.0.0 hash is local validation evidence only. The artifact is intentionally non-release-ready and must not be presented as publicly trusted.

Pipeline 0.8.0 deliberately holds the base manifest at `release_ready: false` before Authenticode verification. The misleading intermediate `Release ready: YES` seen in the earlier 0.7 implementation is no longer part of the current signed-build behavior.

## Normal unsigned release

The ordinary release builder does not require any certificate:

```powershell
py -3.12 .\installer\build_release.py
```

A formal product build must use a product version newer than the last published `1.26.1`. The current candidate is `2.0.0`.

## Free local Authenticode validation

AnonGee creates the development certificate with an explicit Windows certificate shape:

```text
Type             Custom
Key usage        DigitalSignature
Code Signing EKU 1.3.6.1.5.5.7.3.3
Key algorithm    RSA 3072
Hash             SHA256
Private key      Non-exportable
Store            Cert:\CurrentUser\My
```

The helper and signed builder both validate the Code Signing EKU. Some PowerShell/certificate-provider combinations can leave the convenience property `EnhancedKeyUsageList` empty even when the certificate contains the correct X.509 extension. For that reason the implementation also parses the persisted Enhanced Key Usage extension directly:

```text
X.509 extension OID  2.5.29.37
Code Signing EKU     1.3.6.1.5.5.7.3.3
```

From the repository root:

```powershell
$env:ANONGEE_SIGN_CERT_SHA1 = "YOUR_DEVELOPMENT_CERTIFICATE_THUMBPRINT"

py -3.12 .\installer\build_signed_release.py `
    --allow-self-signed-test
```

If a development certificate does not exist yet, provision one with:

```powershell
$cert = & .\installer\create_test_signing_certificate.ps1 `
    -TrustForLocalVerification

$env:ANONGEE_SIGN_CERT_SHA1 = $cert.Thumbprint
```

Expected test outputs for the current candidate:

```text
installer\output\AnonGee-Setup-2.0.0-SELF-SIGNED-TEST.exe
installer\output\test-signing-manifest.json
```

The manifest must contain:

```text
release_ready = false
release_readiness_reason = self-signed local test only
authenticode.signing_profile = self-signed-test
authenticode.local_windows_policy_verified = true
authenticode.certificate.self_signed = true
```

Before a self-signed build starts, it protects both production-named release records. If either already exists, the test build refuses to continue:

```text
installer\output\AnonGee-Setup-<product-version>.exe
installer\output\release-manifest.json
```

Archive or move the existing EXE **and** its manifest first.

## Lifecycle integration in 0.8

Both unsigned and signed 0.8 builds include `installer/lifecycle-version.iss`. The signed compile therefore carries both overlays:

```text
lifecycle-version.iss
signing-authenticode.iss
```

The lifecycle fragment is deferred into the root installer's existing Pascal `[Code]` stream so lifecycle logic compiles after the main installer code while the signing overlay remains in `[Setup]`.

The lifecycle logic classifies fresh install, same-version reinstall, upgrade, and blocked downgrade before the normal Revit/pyRevit prerequisite flow continues. Signing does not bypass or weaken those installer lifecycle rules.

## Security warning during local trust

`-TrustForLocalVerification` intentionally imports the **public certificate only** into:

```text
Cert:\CurrentUser\Root
```

Windows therefore shows a security warning asking whether to trust a certification authority. For the AnonGee self-signed test, this warning is expected.

Before choosing **Yes**, verify that:

1. you just ran `create_test_signing_certificate.ps1`;
2. the dialog says `AnonGee Toolkit Development`; and
3. the thumbprint shown by Windows exactly matches the thumbprint printed by the helper.

If the subject or thumbprint does not match, choose **No** and investigate. Never approve an unexpected root-certificate prompt.

This trust is scoped to the current Windows user. It does not make AnonGee publicly trusted on other computers and does not create Microsoft SmartScreen reputation.

## Where the self-signed key lives

The self-signed signing identity is **not saved in this Git repository**.

| Item | Location | Secret? | Stored in Git? |
| --- | --- | --- | --- |
| Private signing key | Windows certificate/key store behind `Cert:\CurrentUser\My` | **Yes** | **No** |
| Signing certificate (public part) | `Cert:\CurrentUser\My` | No | No |
| Trusted public copy for local verification | `Cert:\CurrentUser\Root` | No | No |
| Thumbprint used by the builder | `$env:ANONGEE_SIGN_CERT_SHA1` for the current shell | No | No |
| Temporary `.cer` used by the helper | Windows temporary directory, deleted after import | No | No |
| Signing scripts and policy | `installer/` in this repository | No private key | Yes |
| `test-signing-manifest.json` | `installer\output\` | Metadata only | Output is not a private key |

The helper creates the private key with `KeyExportPolicy NonExportable` and never calls `Export-PfxCertificate`. The repository also ignores common private-key containers such as `.pfx`, `.p12`, `.pvk`, and `.key`.

The environment variable contains only a certificate **thumbprint**. A thumbprint is an identifier, not a password and not a private key.

Do not copy the Windows private-key material out of the user profile, do not try to commit it, and do not convert this development identity into a PFX for convenience.

A public `.cer` certificate is not secret, but installing it into a Trusted Root store grants trust. Share/import it only when that trust is deliberate.

## Inspect the development certificate

```powershell
$cert |
    Select-Object `
        Subject,
        Issuer,
        Thumbprint,
        NotAfter,
        HasPrivateKey,
        EnhancedKeyUsageList
```

Expected characteristics:

```text
Subject             CN=AnonGee Toolkit Development
Issuer              CN=AnonGee Toolkit Development
HasPrivateKey       True
EnhancedKeyUsage    Code Signing (1.3.6.1.5.5.7.3.3)
```

## Remove the development certificate later

Use the exact thumbprint printed by the provisioning script:

```powershell
$thumb = "YOUR_40_CHARACTER_THUMBPRINT"

Remove-Item "Cert:\CurrentUser\Root\$thumb" -ErrorAction SilentlyContinue
Remove-Item "Cert:\CurrentUser\My\$thumb" -ErrorAction SilentlyContinue
```

Removing the Trusted Root copy removes local trust. Removing the `My` copy also removes access to the development private key.

## Required tools

- Windows x64
- Inno Setup 7
- Microsoft `SignTool.exe` from a current Windows SDK
- a Code Signing certificate in `Cert:\CurrentUser\My` or `Cert:\LocalMachine\My`
- network access to an RFC 3161 timestamp server

The pipeline automatically searches the Windows SDK and prefers the newest available `x64\signtool.exe`:

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

The final Setup EXE is checked with:

```text
signtool verify /pa /all /v
```

## Private-key policy

Do **not** commit a PFX/P12/PVK/private key to Git.

`.gitignore` blocks common private signing-key containers and `installer/signing/private/`. The self-signed helper uses `-KeyExportPolicy NonExportable` and does not call `Export-PfxCertificate`.

The formal workflow currently selects a certificate from the Windows certificate store by SHA-1 thumbprint. This supports hardware-backed/non-exportable certificates exposed through the Windows certificate provider. A future managed signing service can be integrated behind a provider-specific signing adapter without weakening the rest of the release-verification contract.

## Formal signed release — future

Do **not** reuse the self-signed development key for public production signing.

A publicly trusted code-signing identity is not something AnonGee should generate locally and then make public. The secure process is:

1. choose a publicly trusted code-signing CA or managed signing service;
2. complete the provider's individual/organization identity validation;
3. generate and keep the production private key inside approved hardware/HSM-backed protection, or let the managed service generate and retain it;
4. receive/use the public Code Signing certificate or certificate profile issued for that protected key;
5. grant signing access only to the release identity/operator;
6. sign a clean, versioned release;
7. RFC 3161 timestamp the signature;
8. verify the final artifact and record the evidence in the release manifest.

Current CA/Browser Forum Code Signing Baseline Requirements require publicly trusted subscriber private keys issued since June 1, 2023 to be generated, stored, and used in a qualifying Hardware Crypto Module, compliant cloud HSM solution, or compliant Signing Service. For Code Signing certificates issued on or after March 1, 2026, the certificate validity period must not exceed 460 days.

Official requirements:
- CA/Browser Forum Code Signing Baseline Requirements: https://cabforum.org/working-groups/code-signing/requirements/
- Microsoft SignTool: https://learn.microsoft.com/windows/win32/seccrypto/signtool

### Preferred future option: managed signing service

For a sole developer, a managed signing service is usually the simpler security model because the production private key never needs to live on the development PC.

Microsoft Artifact Signing is one such managed service. Microsoft states that it provides certificate lifecycle management with keys protected in FIPS 140-3 Level 3 HSMs, identity validation, certificate profiles, access control through Azure, and public/private/test signing scenarios.

Official Microsoft references:
- Overview: https://learn.microsoft.com/azure/artifact-signing/overview
- Setup quickstart: https://learn.microsoft.com/azure/artifact-signing/quickstart

Public Trust availability and identity eligibility vary by region/entity and can change, so re-check current Microsoft eligibility before choosing this provider.

A secure managed-service setup should use:

- MFA on the account that administers signing;
- least-privilege signing roles;
- a dedicated release identity rather than day-to-day broad administrator access;
- audit logging for signing and configuration changes;
- no long-lived signing secrets in the repository;
- release signing only from clean/tagged source;
- final signature verification and manifest evidence.

### Alternative future option: public CA + hardware token/HSM

A traditional public code-signing CA may issue the certificate for a private key protected by a compliant USB hardware token, smart card, local HSM, or provider-backed cloud HSM/signing service.

For this route:

- use the CA/provider-supported key-generation flow;
- ensure the private key is generated inside the approved device/service;
- do not export the production private key to a `.pfx`;
- protect token PINs/recovery credentials separately;
- keep a physical token disconnected except during an intentional signing session where practical;
- enable MFA/audit controls when the provider supports them;
- document revocation contacts/procedure before the first public release.

The exact provider, price, identity requirements, and hardware model should be selected when public distribution is actually needed because those details change over time.

## Future AnonGee production-signing integration

When the public identity is provisioned, do a **test-only integration first**.

For a production certificate exposed through the Windows certificate store:

```powershell
$env:ANONGEE_SIGN_CERT_SHA1 = "YOUR_40_CHARACTER_CERTIFICATE_THUMBPRINT"

py -3.12 .\installer\build_signed_release.py
```

The certificate must have a private key and the Code Signing EKU:

```text
1.3.6.1.5.5.7.3.3
```

If the chosen managed signing service does not expose a local Windows-store certificate, add a dedicated signing backend/adapter rather than exporting or weakening the provider's protected key model.

The formal path signs both Setup and Inno's embedded uninstaller, timestamps them, verifies the resulting Setup with Windows Authenticode policy, and only then promotes the manifest as release-ready.

## Manifest contract

Current signed manifest schema is **1.4.0** under release pipeline **0.8.0**. Authenticode evidence records:

- certificate subject, issuer, SHA-1 thumbprint, store and expiration;
- whether the certificate is self-signed;
- SignTool path;
- SHA-256 file digest;
- RFC 3161 timestamp URL and SHA-256 timestamp digest;
- final Setup signature verification;
- confirmation that Inno was asked to sign its uninstaller;
- signing profile (`self-signed-test` or `formal`);
- final `release_readiness_reason`.

Self-signed test mode can never set `release_ready: true`.

## Public trust remains deferred

The repository can create a **development self-signed identity**, but it does not create or distribute a **publicly trusted code-signing identity**. Self-signed certificates are suitable only for controlled local/internal validation where the receiving machine explicitly trusts that certificate.

For future external distribution, obtain an appropriate publicly trusted Code Signing certificate or supported managed signing service from a trusted provider, then configure its protected identity for the existing formal pipeline.
