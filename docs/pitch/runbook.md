# Live Demo Runbook

Use this runbook from **T−30 min** through the end of judging. Keep every fallback one click or one command away.

---

## 1. Hardware & Network Setup

### Hardware in scope
- **Arduino UNO Q** powered via USB-C battery pack or laptop USB, strapped securely to the presenter's chest with the **Modulino Movement** (LSM6DSOX at `0x6A`) attached via Qwiic.
  - *Expected sensor status:* `imu=1 thermo=0 light=0 vibro=0`. Modulino Thermo, Light, and Vibro are **not currently detected** — do not attempt to debug them on stage and do not promise them.
- **Samsung Galaxy Watch 8** (charged > 60%), running the `real` build (`com.sepsis.watch`).
  - Confirm **Health Platform developer mode** is active: *Settings → Apps → Health Platform → tap title ~10 times until `[Dev mode]` shows*.
  - Confirm background sensor permission is set to **"Allow all the time"**.
- **Phone hotspot (`S26ULTRA`) or dedicated travel router** with **client isolation OFF** (mandatory so watch, UNO Q, laptop, and second screen can reach each other on LAN).
  - Default board IP on `S26ULTRA` hotspot: **`10.136.49.240`**, port **`8000`** (from `wearos/README.md`).
  - **Crucial Wear OS rule:** The watch must connect over **Wi-Fi**, not Bluetooth tethering through the phone, to reach a LAN IP (`wearos/README.md`). The app requests a Wi-Fi network automatically, so keep Watch Wi-Fi ON and joined to the hotspot.
- **Presenter laptop** (projected to judges) + **Second screen** (phone or tablet on the same hotspot, playing the nurse station).

---

## 2. Exact Commands

### A. Find devices and deploy/start the UNO Q board app
Always pass `-s <serial>` because both the UNO Q and the Wear OS watch/emulator appear in `adb devices`.

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"

# 1. List connected devices (note UNO Q serial vs Watch IP:port)
& $adb devices -l

# 2. Push the latest board app (including gitignored model/sepsis.eim!)
& $adb -s <BOARD_SERIAL> push board/sepsis-monitor /home/arduino/ArduinoApps/

# 3. Start the UNO Q app
& $adb -s <BOARD_SERIAL> shell "cd ~/ArduinoApps/sepsis-monitor && arduino-app-cli app start ."

# 4. Check the UNO Q's LAN IP address
& $adb -s <BOARD_SERIAL> shell "hostname -I"
```

### B. Verify the board API before going on stage
Replace `<BOARD_IP>` (default `10.136.49.240`).

```powershell
# Confirm dashboard state, IMU sample rate (~25 Hz), and Edge Impulse engine ("eim")
curl.exe -s http://<BOARD_IP>:8000/api/state | python -m json.tool | Select-String -Pattern '"engine"|"imu_hz"|"devices"|"state"'

# Confirm replay cases are loaded (p112060 sepsis, p000147 healthy)
curl.exe -s http://<BOARD_IP>:8000/api/replay | python -m json.tool | Select-String -Pattern '"id"|"active"'

# Confirm stress-lab whole-cohort summary is loaded
curl.exe -s http://<BOARD_IP>:8000/api/stress/summary | python -m json.tool | Select-String -Pattern '"n_sepsis"|"threshold"'
```

### C. Point the Galaxy Watch 8 at the board (if IP changed)
Either edit the IP directly on the watch UI (scroll down → numeric keypad → `✓`), or push via ADB over Wi-Fi debugging:

```powershell
& $adb -s <WATCH_IP>:<PORT> shell am start -n com.sepsis.watch/.MainActivity --es host <BOARD_IP> --ei port 8000
```
Then tap **Start** on the watch and confirm the watch screen reads **Connected**. Tap **Measure SpO2** once during pre-flight (hold wrist still ~30 s; value stays fresh for 10 min).

### D. Optional watch-only contract test (without board)
```powershell
python wearos\tools\test_server.py
```

### E. Laptop Simulator Fallback (if the UNO Q board fails)
Another agent is building a standalone laptop simulator at `board/sepsis-monitor/sim/` that runs the same Python scoring, replay, stress lab, and handoff UI locally without Arduino hardware.

> **Before Sunday 11:00 UK:** Fill in the exact command and flags below once `board/sepsis-monitor/sim/` is committed, and smoke-test it once.

```powershell
# If the UNO Q board fails, start the laptop simulator:
cd "C:\Users\tejas\Projects\edge impulse hackathon"
# [PLACEHOLDER — confirm exact entry point in board/sepsis-monitor/sim/]
.venv\Scripts\python.exe board\sepsis-monitor\sim\<SIM_ENTRYPOINT>.py --port 8000 <SIM_FLAGS>
```
- **Simulator URLs (swap `<BOARD_IP>` → `127.0.0.1`):**
  - Monitor dashboard: `http://127.0.0.1:8000/`
  - Stress lab: `http://127.0.0.1:8000/stress`
  - Nurse handoff queue: `http://127.0.0.1:8000/handoff` *(confirm exact route name in Sunday build)*
- **If pointing the real watch at the laptop simulator:** use the laptop's hotspot IP (`ipconfig`) and ensure Python is allowed through Windows Firewall on port `8000`.

---

## 3. Screen-by-Screen URL Plan

| Device / Window | URL | Tab State Before Pitch Starts |
|---|---|---|
| **Presenter Laptop — Tab 1** | Slide deck (Slides 1–7) | On **Slide 1** (full screen). |
| **Presenter Laptop — Tab 2** | `http://<BOARD_IP>:8000/` | Live monitor loaded; replay **stopped**; no overrides or faults active; `p112060` selected at `1.5 s per hour`. |
| **Presenter Laptop — Tab 3** | `http://<BOARD_IP>:8000/stress` | Pre-loaded on `p112060` with **SpO2 over-read +4** selected (summary table visible below). |
| **Second Screen (Phone / Tablet)** | `http://<BOARD_IP>:8000/handoff` *(verify route before pitch; serves `handoff.html`)* | Nurse name pre-filled as `Sam`; open queue clean (no stale demo tasks). |
| **Presenter Laptop — Backup Window** | Local 3-min backup video + Simulator terminal ready | Minimized; one Alt-Tab away. |

---

## 4. Pre-Flight 10-Point Checklist (Run at T−15 min)

- [ ] **1. Power & battery:** UNO Q power bank > 50%, Galaxy Watch 8 > 60%, laptop plugged in, hotspot phone > 50%.
- [ ] **2. Hotspot & LAN:** Laptop, UNO Q, Watch 8, and second screen are all on the same hotspot with **client isolation OFF**.
- [ ] **3. Board liveness:** `http://<BOARD_IP>:8000/` shows green **Model: Edge Impulse model on the board, running** (`engine: eim`) and `imu=1` at ~25 samples/s.
- [ ] **4. Live chest breathing:** Stand still 25 s with strap snug → confirm **Respiratory rate** populates; move 5 s → confirm it clears to `moving`.
- [ ] **5. Watch stream:** Watch shows **Connected**, packet counter increments every 5 s, HR and skin temp appear on dashboard, and `spo2` spot check taken within last 5 min.
- [ ] **6. Offline test verified:** Toggle **Cut the internet (simulated)** (or test mobile-data off once *before* stage) and verify LAN stays up and the amber **Offline: no internet** banner appears while scoring continues. Clear fault afterwards.
- [ ] **7. Replay dry run:** Start `p112060` at `1.5 s/h` → confirm purple **REPLAY** banner appears, model alerts around hour 89 (~9 s in), and stop replay cleanly before stage.
- [ ] **8. Second screen & handoff:** Confirm `http://<BOARD_IP>:8000/handoff` loads on the second screen, nurse name `Sam` is saved, and old test tasks are cleared/resolved.
- [ ] **9. Stress lab warm:** Open `http://<BOARD_IP>:8000/stress`, verify both charts and the 7,898-patient summary table render cleanly.
- [ ] **10. Fail-safes armed:** Laptop simulator terminal is open to the repo directory (command ready to run) and the pre-recorded backup video is open in a media player behind the browser.

---

## 5. Stage Recovery Table

| Symptom on Stage | Probable Cause | Immediate Fix (< 15 s) | Spoken Fallback |
|---|---|---|---|
| **Dashboard says `board unreachable`** | Hotspot dropped UNO Q, IP changed, or app crashed. | Check second tab; if still dead after 5 s, launch **Laptop Simulator** (`board/sepsis-monitor/sim/`) and switch browser to `http://127.0.0.1:8000/`. | "Venue RF dropped the board link — I'm switching to the identical Python and model stack running locally on this laptop." |
| **Chest RR stays `–` (`warming up` / `settling` / `no rhythm`)** | Strap loose, talking while testing, or < 20 s since last movement. | Pause 3 s still; do **not** stall waiting for it. Move straight to the offline beat. | "It requires 20 seconds of still rhythm and three agreeing windows before reporting — refusing to guess under motion is intentional." |
| **Watch link chip turns amber/red (`slow` / `down`)** | Watch fell back to Bluetooth, or Wi-Fi hiccupped. | Leave it on screen — it demonstrates real staleness handling! Don't fumble with Watch settings mid-pitch. | "You can see the liveness badge flag the dropped watch link and grey out stale readings — meanwhile the watch queues up to an hour locally." |
| **Cutting mobile data also kills the phone hotspot LAN** | Some phones tear down hotspot routing when cellular data switches off. | **Never** toggle Airplane Mode on the hotspot phone; use **Mobile Data off only** (tested at pre-flight) OR click **Cut the internet (simulated)** in *Demo controls*. | "We're using the board's deterministic internet-cut fixture so the hotspot LAN stays up for the projector — zero inference calls leave the board." |
| **Model chip says `tree fallback` instead of `.eim`** | `sepsis.eim` binary missing (`gitignored`) or runner socket timed out. | Keep going! Do not restart mid-pitch. (Fix pre-flight by pushing `model/sepsis.eim`.) | "Our deterministic Python tree fallback kicked in automatically — it matches the Edge Impulse `.eim` to four decimal places, so scoring never halts." |
| **Replay `p112060` won't start or hangs** | Replay lock or old replay still active. | Click **Stop**, wait 1 s, click **Start replay**. If still stuck, switch to **Stress Lab (`/stress`)** where the full `p112060` timeline is already plotted. | "Here is the exact same held-out case `p112060` plotted hour by hour in our stress lab." |
| **Nurse handoff page (`/handoff`) 404s or won't sync** | Route not merged or second screen lost Wi-Fi. | Show the local SBAR escalation card on the main dashboard (`POST /escalation` or wait for timer). | "The board still generates the full SBAR handoff and FHIR bundle locally even without a second screen connected." |
| **Stress lab `/stress` slow or summary missing** | `model/stress_eval.json` not pushed or CPU busy during replay. | Stop replay first, or flip immediately to **Slide 4** (pre-rendered stress table from `docs/stress_results.md`). | "I'll show the full 7,898-patient stress-test table on the slide so we stay on time." |
| **Complete Wi-Fi / hardware blackout** | Venue interference or power loss. | Alt-Tab to **backup video** (for live clips) + **Slide deck** (Slides 1–7). | "Hardware lost power/Wi-Fi on stage — here is the unedited recording of the board running offline from this morning." |
