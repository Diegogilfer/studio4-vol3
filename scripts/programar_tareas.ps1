# Registra (o actualiza) las tareas programadas de Studio 4 en el Programador de tareas de Windows.
#   Ideas del día: cada día a las 08:00 · Resumen semanal: los lunes a las 09:00.
# Si el PC está apagado a esa hora, se lanzan al encenderlo. Se quitan con:
#   Unregister-ScheduledTask -TaskName "STUDIO4 *" -Confirm:$false
$raiz = Split-Path -Parent $PSScriptRoot
$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\pythonw.exe" }
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$cada5 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$tareas = @(
    @{ Nombre = "STUDIO4 Ideas del dia"; Orden = "ideas"; Disparador = New-ScheduledTaskTrigger -Daily -At 08:00 },
    @{ Nombre = "STUDIO4 Resumen semanal"; Orden = "semana"; Disparador = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 09:00 },
    @{ Nombre = "STUDIO4 Radar tendencias"; Orden = "radar"; Disparador = New-ScheduledTaskTrigger -Daily -At 07:30 },
    @{ Nombre = "STUDIO4 Vigilante"; Orden = "vigilar"; Disparador = $cada5 }
)
foreach ($t in $tareas) {
    $accion = New-ScheduledTaskAction -Execute $python -Argument "`"$raiz\scripts\tareas.py`" $($t.Orden)" -WorkingDirectory $raiz
    Register-ScheduledTask -TaskName $t.Nombre -Action $accion -Trigger $t.Disparador -Settings $ajustes `
        -Description "Studio 4: python scripts\tareas.py $($t.Orden)" -Force | Out-Null
    Write-Output "Programada: $($t.Nombre)"
}
