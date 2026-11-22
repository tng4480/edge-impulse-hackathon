# Sepsis Watch (Wear OS)

Galaxy Watch app that streams vitals to the Arduino UNO Q board every 5 seconds:

```
POST http://<BOARD_IP>:8000/vitals
{"t": <epoch ms>, "hr": <bpm|null>, "spo2": <percent|null>, "spo2_t": <epoch ms|null>,
 "skin_temp_c": <float|null>, "ambient_c": <float|null>, "ibi_ms": [<ms>, ...] | null, "source": "watch"}
```

- `hr`, `skin_temp_c` and `ambient_c` are current at `t`. `ambient_c` (air temperature around the
  watch) is context only for the board.
- `ibi_ms`: inter-beat intervals from Samsung's HR tracker received since the previous sample, only
  those with IBI status 0 (normal). Null if none. With the screen off they arrive batched, so one
  sample may carry more or fewer than 5 s worth.
- `spo2_t`, `ambient_c` and `ibi_ms` are optional for the board (older builds omit them).
- `spo2` is a spot measurement taken at `spo2_t`, which can be minutes before `t`. `spo2_t` is null
  exactly when `spo2` is null.
- A value that wasn't measured recently is sent as `null`. Nothing is estimated or repeated forever.

## Builds

| APK | Flavor | Use |
|---|---|---|
| `app/build/outputs/apk/real/release/app-real-release.apk` | `real` | The watch. Real sensors only. App id `com.sepsis.watch`. |
| `app/build/outputs/apk/fake/debug/app-fake-debug.apk` | `fake` | Emulator / link testing. Constant HR 72, SpO2 98 (with `spo2_t` 2 min before `t`), skin 34.0. App id `com.sepsis.watch.fake`, red "FAKE DATA BUILD" banner. |

```powershell
cd wearos
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat assembleRealRelease assembleFakeDebug
```

The release APK is signed with the debug key so `adb install` works without a keystore.

## Where each vital comes from

| Vital | Source | Notes |
|---|---|---|
| Heart rate | Samsung `HEART_RATE_CONTINUOUS`, else Android `TYPE_HEART_RATE` | Null if no valid reading in 15 s (off wrist, moving, weak signal). |
| Skin temp | Samsung `SKIN_TEMPERATURE_CONTINUOUS`, else `SKIN_TEMPERATURE_ON_DEMAND` once a minute | Samsung SDK only. Null without it. Sent for 5 min after a reading. Skin temperature is not core body temperature. |
| SpO2 | Samsung `SPO2_ON_DEMAND` | Samsung SDK only. On-demand only: tap **Measure SpO2**, keep still ~30 s with the app open. Sent for 10 min after, with `spo2_t` = when it was taken, then null. |

### Samsung Health Sensor SDK

Skin temp and SpO2 need it. Download it (Samsung account needed) from
<https://developer.samsung.com/health/sensor/overview.html> and put `samsung-health-sensor-api*.aar` in
`app/libs/`. The build picks it up automatically (the Gradle log says which). The `.aar` is git-ignored
because Samsung's licence doesn't allow redistributing it.

On the watch, turn on **Health Platform developer mode**: Settings → Apps → Health Platform → tap the
title ~10 times until "[Dev mode]" shows. Without it Samsung's service rejects unregistered apps
(`SDK_POLICY_ERROR`, shown on screen). Partner registration is only needed to distribute the app.

Samsung states the data is for wellness, not diagnosis.

## Install on the Galaxy Watch (Wi-Fi debugging)

1. Watch: Settings → About watch → Software → tap *Software version* until developer mode is on.
2. Settings → Developer options: turn on **ADB debugging** and **Wireless debugging**
   (watch must be on the same Wi-Fi as the laptop). Tap **Pair new device**.
3. Laptop:
   ```powershell
   $adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
   & $adb pair <ip>:<pair-port>     # enter the 6-digit code
   & $adb connect <ip>:<port>       # the port shown on the Wireless debugging screen
   & $adb -s <ip>:<port> install -r app\build\outputs\apk\real\release\app-real-release.apk
   ```
4. Open **Sepsis Watch**, allow the permissions (including "all the time" for background sensor
   access), set the board IP, tap **Start**.

Always pass `-s`: the UNO Q also shows up in `adb devices`.

## Board address

The `real` build defaults to `10.136.49.240:8000` (the board on the S26ULTRA phone hotspot,
dashboard at `http://10.136.49.240:8000/`). Watch and board must be on the same Wi-Fi, with client
isolation off.
Edit it on the watch (scroll down, numeric keypad, ✓ saves), or set it from the laptop:

```powershell
& $adb -s <watch> shell am start -n com.sepsis.watch/.MainActivity --es host 192.168.1.50 --ei port 8000
```

The watch must reach the board over **Wi-Fi**. Wear OS normally routes through the phone over
Bluetooth, which can't reach a LAN address, so the app explicitly requests a Wi-Fi network.

## Testing without the board

```powershell
python wearos\tools\test_server.py          # validates the JSON contract, prints each sample
```

Emulator: the app's `fake` build defaults to `10.0.2.2:8000`, which is the laptop. Real watch: use the
laptop's Wi-Fi IP and allow Python through Windows Firewall.

## Behaviour

- Foreground service (type `health`) with a partial wake lock: keeps sampling and sending with the
  screen off. Stop it from the app.
- If the board is unreachable, samples queue (up to 1 hour) and are replayed oldest first, 30 per
  tick, when it comes back. A non-2xx reply drops that sample (resending the same body won't help).
- Screen shows **Connected** if a POST succeeded in the last 12 s, plus the queue length and last error.
