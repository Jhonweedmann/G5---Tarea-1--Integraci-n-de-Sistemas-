# Pruebas manuales desde PowerShell. Cargar con:  . .\scripts\llamar.ps1
# Uso:  Llamar POST /v1/estudiantes @{ nombre = "Ana"; email = "ana@example.com" }
#       Llamar GET /v1/cursos/ARQ-101 -Token solo-lectura
#       Llamar POST /v1/matriculas @{ estudiante_id = $e.id; curso_id = "ARQ-101" } -Clave intento-1
# Muestra el código HTTP y la latencia, y devuelve el cuerpo como objeto (también en errores).
function Llamar {
    param($Metodo, $Ruta, $Cuerpo, $Token = "desarrollo-seguro", $Clave)
    $headers = @{}
    if ($Token) { $headers.Authorization = "Bearer $Token" }
    if ($Clave) { $headers["Idempotency-Key"] = $Clave }
    $params = @{ Uri = "http://localhost:8000$Ruta"; Method = $Metodo; Headers = $headers; UseBasicParsing = $true }
    if ($Cuerpo) {
        $params.Body = [Text.Encoding]::UTF8.GetBytes(($Cuerpo | ConvertTo-Json))
        $params.ContentType = "application/json"
    }
    $inicio = Get-Date
    try {
        $r = Invoke-WebRequest @params
        $codigo = [int]$r.StatusCode
        $texto = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
    } catch {
        $resp = $_.Exception.Response
        if (-not $resp) { Write-Host "Sin respuesta: $($_.Exception.Message)" -ForegroundColor Red; return }
        $codigo = [int]$resp.StatusCode
        $stream = $resp.GetResponseStream()
        $stream.Position = 0
        $texto = (New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)).ReadToEnd()
    }
    $ms = [int]((Get-Date) - $inicio).TotalMilliseconds
    Write-Host "HTTP $codigo  ($ms ms)" -ForegroundColor Cyan
    if ($texto) { $texto | ConvertFrom-Json }
}
