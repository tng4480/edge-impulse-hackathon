Put `samsung-health-sensor-api*.aar` from the Samsung Health Sensor SDK download here
(https://developer.samsung.com/health/sensor/overview.html, needs a Samsung account).

The build detects it automatically. Without it, the `real` build reads heart rate only and sends
`spo2` and `skin_temp_c` as null. The .aar is git-ignored because Samsung's licence does not allow
redistributing it.
