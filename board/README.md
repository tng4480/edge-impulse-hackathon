# Board app (Arduino UNO Q)

`sepsis-monitor/` is an Arduino App Lab app. The STM32 sketch reads the Qwiic sensors; the Python app on the Linux side does the maths, serves the dashboard and receives the watch's vitals.

## Deploy

```
adb -s <board serial> push board/sepsis-monitor /home/arduino/ArduinoApps/
adb -s <board serial> shell "cd ~/ArduinoApps/sepsis-monitor && arduino-app-cli app start ."
```

(`adb devices -l` lists serials; the Wear OS emulator also shows up there.) Dashboard: `http://<board ip>:8000/`.

## STM32 sketch (Bridge functions)

| Function | Returns |
|---|---|
| `drain()` | `t0,t1\|ax,ay,az;...` accelerometer samples in milli-g at 25 Hz since the last call |
| `env()` | `temp_c,hum_pct,lux,ir` from Modulino Thermo and Light |
| `vibe(ms, power)` | 1 if the Vibro fired (power 25 to 50) |
| `status()` | which modules answered on Qwiic |

## HTTP

| Request | Purpose |
|---|---|
| `POST /vitals` | watch contract: `{t, hr, spo2, skin_temp_c, source:"watch"}` plus optional `spo2_t` (epoch ms the SpO2 was measured). Nulls allowed. |
| `GET /api/state` | everything the dashboard shows |
| `POST /override` | `{hr, spo2, temp, rr}` demo overrides for 10 minutes (null clears) |
| `POST /vibe`, `POST /ack` | test the Vibro; acknowledge an alert (mutes 5 minutes) |
| `POST /replay/start` | `{"case": "p112060", "seconds_per_hour": 1.5}` replays a recorded held-out ICU patient through the model and NEWS2; drives the alert while active |
| `POST /replay/stop`, `GET /api/replay` | stop it; replay state (vitals, risk, NEWS2, timeline, hours to onset, case list) |
| `GET /api/imu/raw?seconds=N` | last N seconds (max 60) of raw accelerometer samples `[[x, y, z] in g]` at 25 Hz |

The model (`python/model_runner.py`, `model/sepsis.eim`) works on hourly trends: live mode needs 8 hours of history before it answers, replay shows it working on a recorded patient. `model/sepsis.eim` is gitignored, so push it with adb along with the rest of the app.

## Respiratory rate

`python/resp.py`: magnitude of the chest accelerometer, band-passed to 0.1 to 0.6 Hz, peak counting on the best axis. It returns nothing while the wearer is moving, when no breathing signal is present, or when breaths are too irregular. It needs about 20 s of data and the board strapped to the chest.

## Risk

The dashboard scores a partial NEWS2 (RR, SpO2, temperature, HR). `risk_from_model()` in `python/main.py` is where the Edge Impulse model plugs in. An alert fires after two consecutive seconds at NEWS2 5 or more, or any single red (3) score.
