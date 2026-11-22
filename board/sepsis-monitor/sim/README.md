# Windows board simulator

From the repo root in PowerShell, run the first two commands in separate terminals. The third starts its own simulator.
```powershell
& .venv/Scripts/python.exe board/sepsis-monitor/sim/run_sim.py
& .venv/Scripts/python.exe board/sepsis-monitor/sim/fake_watch.py --scenario normal
& .venv/Scripts/python.exe board/sepsis-monitor/sim/rehearse.py
```
Open the dashboard at http://127.0.0.1:8000/, the nurse queue at `/handoff`, or the stress lab at `/stress`.
To try "I feel unwell", run `Invoke-RestMethod http://127.0.0.1:8000/api/checkin -Method Post -ContentType application/json -Body '{"feel_unwell":true}'`.
To change the port, set `$env:SIM_PORT = '8123'` in both terminals before starting.
Watch scenarios are `normal`, `sepsis_drift`, `walking` and `disconnect`.
The watch's scenario also drives the simulated chest sensor. Drift raises breathing rate over four minutes.
For a longer outage, pass `--scenario disconnect --disconnect-seconds 65`. Heart rate turns stale after 12 seconds.
The simulator uses the board's bundled tree model and keeps each run's data in a temporary directory.
