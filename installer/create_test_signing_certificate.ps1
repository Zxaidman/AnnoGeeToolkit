#requires -Version 5.1
<#
.SYNOPSIS
Creates or reuses a local AnonGee self-signed Code Signing certificate.

.DESCRIPTION
This is a development/test helper only. It creates a non-exportable RSA code
signing key in Cert:\CurrentUser\My. With -TrustForLocalVerification it also
adds only the public certificate to Cert:\CurrentUser\Root so SignTool /pa can
validate test signatures on this Windows user account.

The certificate contract is explicit: DigitalSignature key usage plus the
Code Signing EKU 1.3.6.1.5.5.7.3.3. When this script is launched from
PowerShell Core (including the VS Code PowerShell extension when configured for
pwsh), certificate creation is delegated to the built-in Windows PowerShell
5.1 PKI cmdlet and the resulting certificate is returned to the calling shell.

It never exports a PFX/private key and never creates public publisher trust.
#>

[CmdletBinding()]
param(
    [string]$Subject = "CN=AnonGee Toolkit Development",
    [ValidateRange(1, 5)]
    [int]$ValidYears = 2,
    [switch]$TrustForLocalVerification,
    [switch]$ForceNew,
    [switch]$EmitThumbprintMarker
)

$ErrorActionPreference = "Stop"
$CodeSigningEku = "1.3.6.1.5.5.7.3.3"
$MyStore = "Cert:\CurrentUser\My"
$RootStore = "Cert:\CurrentUser\Root"
$WindowsPowerShell = Join-Path $env:SystemRoot `
    "System32\WindowsPowerShell\v1.0\powershell.exe"
$ThumbprintMarker = "ANONGEE_CERT_THUMBPRINT="

if ($env:OS -ne "Windows_NT") {
    throw "AnonGee test signing certificate provisioning requires Windows."
}

# The PKI cmdlet is a Windows PowerShell module. Calling it through a
# PowerShell Core compatibility proxy can change how certificate extension
# data is marshalled. Create the certificate in Windows PowerShell 5.1, then
# read the real certificate back from the same CurrentUser store here.
if ($PSVersionTable.PSEdition -ne "Desktop" -and -not $EmitThumbprintMarker) {
    if (-not (Test-Path -LiteralPath $WindowsPowerShell)) {
        throw "Windows PowerShell 5.1 was not found at $WindowsPowerShell"
    }

    Write-Host (
        "PowerShell Core detected; using Windows PowerShell 5.1 for the PKI " +
        "certificate creation step."
    )

    $ChildArguments = @(
        "-NoProfile",
        "-NonInteractive",
        "-File",
        $PSCommandPath,
        "-Subject",
        $Subject,
        "-ValidYears",
        [string]$ValidYears,
        "-EmitThumbprintMarker"
    )
    if ($TrustForLocalVerification) {
        $ChildArguments += "-TrustForLocalVerification"
    }
    if ($ForceNew) {
        $ChildArguments += "-ForceNew"
    }

    $ChildOutput = & $WindowsPowerShell @ChildArguments 2>&1
    $ChildExitCode = $LASTEXITCODE
    $Thumbprint = ""

    foreach ($Line in @($ChildOutput)) {
        $Text = [string]$Line
        if ($Text.StartsWith($ThumbprintMarker)) {
            $Thumbprint = $Text.Substring($ThumbprintMarker.Length).Trim()
        } elseif ($Text) {
            Write-Host $Text
        }
    }

    if ($ChildExitCode -ne 0) {
        throw "Windows PowerShell certificate provisioning failed with exit code $ChildExitCode."
    }
    if (-not $Thumbprint) {
        throw "Windows PowerShell certificate provisioning returned no thumbprint."
    }

    return Get-Item -LiteralPath (Join-Path $MyStore $Thumbprint)
}

function Get-EnhancedKeyUsageOids {
    param($Certificate)

    if (-not $Certificate) {
        return @()
    }

    $Values = @()

    # Prefer the convenience property when the current host populates it.
    try {
        foreach ($Usage in @($Certificate.EnhancedKeyUsageList)) {
            if ($Usage -and $Usage.ObjectId -and $Usage.ObjectId.Value) {
                $Values += [string]$Usage.ObjectId.Value
            }
        }
    } catch {
        # Fall through to the raw X.509 extension parser below.
    }

    # Some hosts/providers leave EnhancedKeyUsageList empty even though the
    # certificate contains the standard EKU extension. Parse OID 2.5.29.37
    # directly so validation is based on the certificate bytes, not a display
    # convenience property.
    if ($Values.Count -eq 0) {
        $RawExtension = @(
            $Certificate.Extensions |
                Where-Object { $_.Oid.Value -eq "2.5.29.37" }
        ) | Select-Object -First 1

        if ($null -ne $RawExtension) {
            try {
                $ParsedExtension = New-Object `
                    System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension
                $ParsedExtension.CopyFrom($RawExtension)
                foreach ($Oid in @($ParsedExtension.EnhancedKeyUsages)) {
                    if ($Oid -and $Oid.Value) {
                        $Values += [string]$Oid.Value
                    }
                }
            } catch {
                # The caller will report the raw extension OIDs if validation
                # still fails, which gives us a useful workstation diagnostic.
            }
        }
    }

    return @($Values | Select-Object -Unique)
}

function Test-CodeSigningCertificate {
    param($Certificate)

    if (-not $Certificate -or -not $Certificate.HasPrivateKey) {
        return $false
    }
    if ($Certificate.NotAfter -le (Get-Date).AddDays(30)) {
        return $false
    }
    $Ekus = @(Get-EnhancedKeyUsageOids $Certificate)
    return $Ekus -contains $CodeSigningEku
}

$Certificate = $null
$CreatedNew = $false

if (-not $ForceNew) {
    $Certificate = Get-ChildItem $MyStore |
        Where-Object {
            $_.Subject -eq $Subject -and (Test-CodeSigningCertificate $_)
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
}

if ($null -eq $Certificate) {
    Write-Host "Creating AnonGee self-signed development Code Signing certificate..."

    # Match Microsoft's documented self-signed package-signing shape exactly
    # for the EKU and basic-constraints extensions.
    $Created = New-SelfSignedCertificate `
        -Type Custom `
        -Subject $Subject `
        -FriendlyName "AnonGee Toolkit Development Code Signing" `
        -CertStoreLocation $MyStore `
        -HashAlgorithm SHA256 `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -KeyExportPolicy NonExportable `
        -KeyUsage DigitalSignature `
        -TextExtension @(
            "2.5.29.37={text}1.3.6.1.5.5.7.3.3",
            "2.5.29.19={text}"
        ) `
        -NotAfter (Get-Date).AddYears($ValidYears)

    $CreatedNew = $true

    # Re-read from the certificate provider so validation uses the persisted
    # certificate rather than the creation cmdlet's transient return object.
    $Certificate = Get-Item -LiteralPath (
        Join-Path $MyStore $Created.Thumbprint
    )
} else {
    Write-Host "Reusing existing AnonGee development Code Signing certificate."
}

if (-not (Test-CodeSigningCertificate $Certificate)) {
    $Ekus = @(Get-EnhancedKeyUsageOids $Certificate)
    $RawExtensionOids = @()
    if ($Certificate) {
        $RawExtensionOids = @($Certificate.Extensions | ForEach-Object {
            $_.Oid.Value
        })
    }

    $Thumbprint = if ($Certificate) { $Certificate.Thumbprint } else { "<none>" }
    $HasPrivateKey = if ($Certificate) { $Certificate.HasPrivateKey } else { $false }
    $NotAfter = if ($Certificate) { $Certificate.NotAfter.ToString("u") } else { "<none>" }

    # Remove only the exact unusable certificate created by this invocation.
    # Existing certificates are never deleted automatically.
    if ($CreatedNew -and $Certificate -and $Certificate.Thumbprint) {
        Remove-Item -LiteralPath (
            Join-Path $MyStore $Certificate.Thumbprint
        ) -Force -ErrorAction SilentlyContinue
    }

    throw (
        "The selected certificate does not satisfy the AnonGee test-signing " +
        "contract. Thumbprint={0}; HasPrivateKey={1}; NotAfter={2}; EKUs={3}; " +
        "RawExtensions={4}" -f
        $Thumbprint,
        $HasPrivateKey,
        $NotAfter,
        (($Ekus -join ", ") -replace "^$", "<none>"),
        (($RawExtensionOids -join ", ") -replace "^$", "<none>")
    )
}

if ($TrustForLocalVerification) {
    $Trusted = Get-ChildItem $RootStore |
        Where-Object { $_.Thumbprint -eq $Certificate.Thumbprint } |
        Select-Object -First 1

    if ($null -eq $Trusted) {
        $TempCer = Join-Path ([System.IO.Path]::GetTempPath()) `
            ("anongee-test-signing-{0}.cer" -f $Certificate.Thumbprint)
        try {
            Export-Certificate -Cert $Certificate -FilePath $TempCer -Force | Out-Null
            Import-Certificate -FilePath $TempCer -CertStoreLocation $RootStore | Out-Null
        } finally {
            Remove-Item $TempCer -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Trusted the public test certificate for this Windows user only."
    } else {
        Write-Host "Public test certificate is already trusted for this Windows user."
    }
} else {
    Write-Host "Certificate was not added to Trusted Root."
    Write-Host "Use -TrustForLocalVerification before running SignTool /pa validation."
}

Write-Host "Subject:    $($Certificate.Subject)"
Write-Host "Thumbprint: $($Certificate.Thumbprint)"
Write-Host "Expires:    $($Certificate.NotAfter.ToString('u'))"
Write-Host "EKU:        $((Get-EnhancedKeyUsageOids $Certificate) -join ', ')"
Write-Host ""
Write-Host "For this PowerShell session:"
Write-Host ('$env:ANONGEE_SIGN_CERT_SHA1 = "{0}"' -f $Certificate.Thumbprint)
Write-Host ""
Write-Host "This certificate is SELF-SIGNED and is not publicly trusted."

if ($EmitThumbprintMarker) {
    Write-Output ("{0}{1}" -f $ThumbprintMarker, $Certificate.Thumbprint)
} else {
    $Certificate
}
