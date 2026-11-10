$body = @{
    image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    garment_url = "https://v3b.fal.media/files/b/penguin/sji5EHUvmFYOCVZsvvId-.png"
    prompt = "test"
}
$json = $body | ConvertTo-Json
try {
    $resp = Invoke-WebRequest -Uri "https://tryvtri-vton.vercel.app/api/try-on" -Method POST -ContentType "application/json" -Body $json -UseBasicParsing -TimeoutSec 300 -ErrorAction Stop
    Write-Output "Status: $($resp.StatusCode)"
    Write-Output $resp.Content
} catch {
    Write-Output "Error: $($_.Exception.Message)"
    if ($_.ErrorDetails) { Write-Output $_.ErrorDetails }
    if ($_.Exception.Response) {
        $errContent = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($errContent)
        Write-Output $reader.ReadToEnd()
        $reader.Close()
    }
}
