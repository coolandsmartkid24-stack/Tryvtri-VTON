$body = @{
    image_base64 = "https://v3b.fal.media/files/b/koala/YlOtn9SjXGGH274eN1G5R.png"
    garment_url = "https://v3b.fal.media/files/b/penguin/sji5EHUvmFYOCVZsvvId-.png"
    prompt = "A person wearing a stylish jacket, virtual try-on"
    image_size = @{ width = 512; height = 768 }
}
$json = $body | ConvertTo-Json
try {
    $resp = Invoke-WebRequest -Uri "https://tryvtri-vton.vercel.app/api/try-on" -Method POST -ContentType "application/json" -Body $json -UseBasicParsing -TimeoutSec 300 -ErrorAction Stop
    Write-Output "Status: $($resp.StatusCode)"
    Write-Output $resp.Content
} catch {
    Write-Output "Error: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Output $reader.ReadToEnd()
        $reader.Close()
    }
}
