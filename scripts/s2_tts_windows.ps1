param(
    [Parameter(Mandatory=$true)][string]$TextPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$VoiceName = ""
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$reader = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $voices = @($reader.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.Name -eq "vi-VN"
    })
    if ($voices.Count -eq 0) {
        throw "No installed vi-VN SAPI voice. Install a suitable local Vietnamese voice or use Piper."
    }
    $chosen = $voices[0].VoiceInfo.Name
    if ($VoiceName -ne "") {
        $match = @($voices | Where-Object { $_.VoiceInfo.Name -eq $VoiceName })
        if ($match.Count -ne 1) {
            throw "The requested Vietnamese SAPI voice is not installed."
        }
        $chosen = $match[0].VoiceInfo.Name
    }
    $reader.SelectVoice($chosen)
    $text = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Narration text is empty."
    }
    $reader.SetOutputToWaveFile($OutputPath)
    $reader.Speak($text)
    $reader.SetOutputToNull()
}
finally {
    $reader.Dispose()
}
