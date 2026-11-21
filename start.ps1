$docker = Get-Command docker -CommandType Application -TotalCount 1 -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Error 'Docker wurde im PATH nicht gefunden.'
    exit 1
}

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Write-Error 'Kopiert .env.template nach .env und tragt DREAM_API_KEY ein.'
    exit 2
}

$image = 'dreamorchestra-api-test:local'
& $docker.Source build --tag $image $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $docker.Source run --rm --env-file $envFile $image
exit $LASTEXITCODE
