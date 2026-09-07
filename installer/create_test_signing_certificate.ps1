#requires -Version 5.1
<#
.SYNOPSIS
Creates or reuses a local AnonGee self-signed Code Signing certificate.

.DESCRIPTION
This is a development/test helper only. It creates a non-exportable RSA code
signing key in Cert:\CurrentUser\My. With -TrustForLocalVerification it also
adds only the public certificate to Cert:\CurrentUser\Root so SignTool /pa can
validate test signatures on this Windows user account.

The certificate contract is explicit rather than relying on a shorthand type:
DigitalSignature key usage plus the Code Signing EKU 1.3.6.1.5.5.7.3.3.
It never exports a PFX/private key and never creates public publisher trust.
#>

[CmdletBinding()]
param(
    [string]$Subject = "CN=AnonGee Toolkit Development",
    [ValidateRange(1, 5)]
    [int]$ValidYears = 2,
    [switch]$TrustForLocalVerification,
    [switch]$ForceNew
)

$ErrorActionPreference = "Stop"
$CodeSigningEku = "1.3.6.1.5.5.7.3.3"
$MyStore = "Cert:\CurrentUser\My"
$RootStore = "Cert:\CurrentUser\Root"

if ($env:OS -ne "Windows_NT") {
    throw "AnonGee test signing certificate provisioning requires Windows."
}

function Get-EnhancedKeyUsageOids {
    param($Certificate)

    if (-not $Certificate) {
        return @()
    }

    return @($Certificate.EnhancedKeyUsageList | ForEach-Object {
        $_.ObjectId.Value
    })
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

    # Use the explicit certificate shape recommended by Microsoft's package
    # signing guidance. This avoids depending on how a particular PKI module
    # version expands the CodeSigningCert shorthand.
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
        -KeyUsageProperty Sign `
        -TextExtension @(
            "2.5.29.37={text}$CodeSigningEku",
            "2.5.29.19={text}"
        ) `
        -NotAfter (Get-Date).AddYears($ValidYears)

    $CreatedNew = $true

    # Re-read from the certificate provider before validation. This makes the
    # object shape identical to certificates discovered on later runs and
    # ensures provider-added properties such as EnhancedKeyUsageList are loaded.
    $Certificate = Get-Item -LiteralPath (
        Join-Path $MyStore $Created.Thumbprint
    )
} else {
    Write-Host "Reusing existing AnonGee development Code Signing certificate."
}

if (-not (Test-CodeSigningCertificate $Certificate)) {
    $Ekus = @(Get-EnhancedKeyUsageOids $Certificate)
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
        "contract. Thumbprint={0}; HasPrivateKey={1}; NotAfter={2}; EKUs={3}" -f
        $Thumbprint,
        $HasPrivateKey,
        $NotAfter,
        (($Ekus -join ", ") -replace "^$", "<none>")
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

# Return only the certificate object on the success pipeline so callers can do:
# $cert = & .\installer\create_test_signing_certificate.ps1 -TrustForLocalVerification
$Certificate
