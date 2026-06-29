param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("staging", "production")]
    [string]$Environment,

    [Parameter(Mandatory = $true)]
    [uri]$ApiOrigin,

    [Parameter(Mandatory = $true)]
    [string[]]$AllowedOrigins,

    [string[]]$Routes = @(),

    [string[]]$Domains = @(),

    [string]$SecretsFile = "",

    [switch]$Deploy
)

$ErrorActionPreference = "Stop"

function Assert-HttpUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $parsed = $null
    if (-not [uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$parsed)) {
        throw "$Name must be an absolute URL: $Value"
    }
    if ($parsed.Scheme -ne "https" -and $parsed.Scheme -ne "http") {
        throw "$Name must use http or https: $Value"
    }
}

function Get-NormalizedOrigin {
    param([Parameter(Mandatory = $true)][uri]$Uri)

    $builder = [System.UriBuilder]::new($Uri)
    $builder.Path = ""
    $builder.Query = ""
    $builder.Fragment = ""
    return $builder.Uri.AbsoluteUri.TrimEnd("/")
}

$workerPath = Join-Path (Split-Path -Parent $PSScriptRoot) "cloudflare\worker"
if (-not (Test-Path $workerPath)) {
    throw "Worker path not found: $workerPath"
}

$apiOriginValue = Get-NormalizedOrigin -Uri $ApiOrigin
if ($ApiOrigin.Scheme -ne "https") {
    throw "ApiOrigin must be HTTPS for $Environment deployments: $apiOriginValue"
}

$normalizedAllowedOrigins = @()
foreach ($origin in $AllowedOrigins) {
    Assert-HttpUrl -Value $origin -Name "AllowedOrigins"
    $normalizedAllowedOrigins += (Get-NormalizedOrigin -Uri ([uri]$origin))
}
$allowedOriginsValue = ($normalizedAllowedOrigins | Sort-Object -Unique) -join ","

Set-Location $workerPath

Write-Host "== Cloudflare Worker deployment =="
Write-Host "Environment: $Environment"
Write-Host "Worker path: $workerPath"
Write-Host "API_ORIGIN: $apiOriginValue"
Write-Host "ALLOWED_ORIGINS: $allowedOriginsValue"
if ($Routes.Count -gt 0) {
    Write-Host "Routes: $($Routes -join ', ')"
}
if ($Domains.Count -gt 0) {
    Write-Host "Domains: $($Domains -join ', ')"
}
if (-not $Deploy) {
    Write-Host "Mode: dry-run"
}

Write-Host "Running TypeScript validation..."
npm.cmd run typecheck

$temporarySecretsFile = ""
try {
    $effectiveSecretsFile = $SecretsFile
    if ($Deploy -and [string]::IsNullOrWhiteSpace($effectiveSecretsFile)) {
        $secretFromEnvironment = [Environment]::GetEnvironmentVariable("VAPI_WEBHOOK_SECRET")
        if ([string]::IsNullOrWhiteSpace($secretFromEnvironment)) {
            throw "Set VAPI_WEBHOOK_SECRET in the shell or pass -SecretsFile before using -Deploy."
        }

        $temporarySecretsFile = Join-Path ([System.IO.Path]::GetTempPath()) ("voice-worker-secrets-{0}.env" -f ([guid]::NewGuid().ToString("N")))
        Set-Content -LiteralPath $temporarySecretsFile -Value "VAPI_WEBHOOK_SECRET=$secretFromEnvironment" -NoNewline
        $effectiveSecretsFile = $temporarySecretsFile
    }

    $wranglerArgs = @(
        "wrangler",
        "deploy",
        "--env", $Environment,
        "--var", "API_ORIGIN:$apiOriginValue",
        "--var", "ALLOWED_ORIGINS:$allowedOriginsValue",
        "--var", "ENVIRONMENT:$Environment"
    )

    if (-not [string]::IsNullOrWhiteSpace($effectiveSecretsFile)) {
        if (-not (Test-Path $effectiveSecretsFile)) {
            throw "Secrets file not found: $effectiveSecretsFile"
        }
        $wranglerArgs += @("--secrets-file", $effectiveSecretsFile)
    }

    foreach ($route in $Routes) {
        if (-not [string]::IsNullOrWhiteSpace($route)) {
            $wranglerArgs += @("--route", $route)
        }
    }

    foreach ($domain in $Domains) {
        if (-not [string]::IsNullOrWhiteSpace($domain)) {
            $wranglerArgs += @("--domain", $domain)
        }
    }

    if (-not $Deploy) {
        $wranglerArgs += "--dry-run"
    }

    Write-Host "Running Wrangler..."
    npx.cmd @wranglerArgs

    if ($Deploy) {
        Write-Host "Worker deployment completed for $Environment."
    }
    else {
        Write-Host "Dry-run completed. Re-run with -Deploy to upload the Worker."
    }
}
finally {
    if (-not [string]::IsNullOrWhiteSpace($temporarySecretsFile) -and (Test-Path $temporarySecretsFile)) {
        Remove-Item -LiteralPath $temporarySecretsFile -Force
    }
}
