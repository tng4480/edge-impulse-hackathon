# Research Report: Home Sepsis Early-Warning Wearable

*Synthesis from five parallel research tracks plus direct inspection of `board/`, `training/`, `wearos/`, and `samsung-health-sensor-api-1.4.1.aar`. Ideas already in `docs/ideas/` are omitted unless corrected or sharpened.*

---

## 1. Key Findings by Research Question

### 1.1 Clinical: Pre-Hospital Deterioration & UK Guidance
- **NICE NG51 was replaced:** On 19 Nov 2025 (updated Sep 2026), NICE replaced NG51 with **[NICE NG253](https://www.nice.org.uk/guidance/ng253)** (adults ≥16; plus NG254 <16, NG255 pregnancy). Acute/ambulance care uses **[RCP NEWS2](https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2)** (High = ≥7 or 5–6 with a single 3; Medium = 5–6 or 3–4 with a single 3). Community tables flag **no urine ≥18 h** (High) / **12–18 h** (Medium), new altered mental state, and mottling (darker-skin caveats). Under **[NICE CG151](https://www.nice.org.uk/guidance/cg151)**, chemo fever >38°C or sepsis signs require immediate 24 h oncology triage and IV antibiotics <60 min—never delayed by a wearable score.
- **Evidence hierarchy:**
  - **RR trend** is the earliest reliable vital sign ([Cretikos et al., 2008](https://doi.org/10.5694/j.1326-5377.2008.tb01825.x)); in ~270k ward admissions, vital **trends** lifted AUC 0.74→0.78 (*p*<0.001), with RR and SpO₂ trends each adding +0.04 ([Churpek et al., 2016](https://doi.org/10.1016/j.resuscitation.2016.02.005)).
  - **Rigors / shaking chills** rule in bacteraemia (**Spec 90.3%, PLR 4.65**, [Tokuda et al., 2005](https://doi.org/10.1016/j.amjmed.2005.06.043); **PLR 4.7**, [Coburn et al., 2012](https://doi.org/10.1001/jama.2012.8262); **OR 13.7**, [Lee et al., 2012](https://doi.org/10.1016/j.diagmicrobio.2012.01.007)), but pooled **sensitivity is ~37%**—absence never reassures.
  - **HRV drop** preceded sepsis ~35 h on inpatient ECG ([Ahmad et al., 2009](https://doi.org/10.1371/journal.pone.0006642), *n*=17); ED HRV+vitals hit AUC 0.78–0.80 ([Samsudin et al., 2018](https://doi.org/10.1097/MD.0000000000010536); [Barnaby et al., 2019](https://doi.org/10.1097/SHK.0000000000001164)). Watch PPG HRV flags viral infection up to 7 d early ([Hirten et al., 2021](https://doi.org/10.2196/26107))—unvalidated for home bacterial sepsis.
  - **Delirium & step collapse:** Delirium hits 20–50% of sepsis cases (often 36–48 h pre-fever in older adults). In oncology wearables, +1,000 steps/day cut hospitalisation odds (**OR 0.21**, [Gresham et al., 2018](https://doi.org/10.1038/s41746-018-0051-3)).
  - **Mottling, CRT & toe-to-room gradient** ([Ait-Oufella et al., 2011](https://doi.org/10.1007/s00134-011-2163-y); [ANDROMEDA-SHOCK, 2019](https://doi.org/10.1001/jama.2019.0071); [Bourcier et al., 2016](https://doi.org/10.1186/s13613-016-0164-2)) track **ICU shock** at knee/toe—not early wrist onset.
- **Home/virtual-ward numbers:** TempTraq axillary patches caught neutropenic fever **median 4.9 h earlier** than 4–8 h spot checks (Sens ~85%, Spec ~86%, >90% adherence; [Flora et al., 2021](https://doi.org/10.1016/j.ccell.2021.03.005); [Nessle et al., 2023](https://doi.org/10.1002/pbc.30059)). Post-op patches (WARD: [Haahr-Raunkjær et al., 2022](https://doi.org/10.1016/j.bja.2022.01.030); Mølgaard et al., *Anesth Analg* 2025—*exact 2025 SAE/alarm rates unverified*) catch micro-events but suffer alarm fatigue and ≥25% home data loss. South Yorkshire's NHS virtual-ward evaluation (*n*=236,741) saw no consistent readmission drop. Viral watch trials (**NightSignal** 78% Sens / ~13% FPR, [Alavi et al., 2022](https://doi.org/10.1038/s41591-021-01593-2); **TemPredict** AUC 0.819, [Mason et al., 2022](https://doi.org/10.1038/s41598-022-07314-0)) are viral precedent only.

### 1.2 Data: Closing the ICU-to-Home Gap
No open dataset pairs multi-day home wearables with clinical sepsis outcomes. Pair open wearable/IMU datasets tonight with credentialed ED/wearable cohorts post-hackathon:

| Dataset | Link | Access | Signals & Size | Use |
|---|---|---|---|---|
| **Stanford MyPHD** | [Phase 2 ZIP](https://storage.googleapis.com/gbsc-gcp-project-ipop_public/COVID-19-Phase2/COVID-19-Phase2-Wearables.zip) · [Code](https://github.com/StanfordBioinformatics/wearable-infection) | Open (academic) | >3,000 subjects; HR, steps, sleep + infection dates | **Tonight:** personal-baseline RHR/step drift on free-living infections. |
| **ESL-EPFL Cough** | [Zenodo 7562332](https://doi.org/10.5281/zenodo.7562332) | Open (CC BY 4.0) | 15 subjects, ~4,300 coughs; **chest 9-axis IMU** + audio | **Roadmap:** replaces audio-only COUGHVID. |
| **Capture-24** / **MMASH** | [Capture-24](https://ora.ox.ac.uk/objects/uuid:99d7c092-d865-4a19-b096-cc16440cd001) · [MMASH](https://physionet.org/content/mmash/1.0.0/) | Open (CC BY / ODbL) | 151 adults ACC/sleep; 22 adults 24 h IBI+ACC | **Tonight:** circadian HR/HRV & posture baselines. |
| **BIG IDEAs Wearable** | [PhysioNet](https://physionet.org/content/big-ideas-glycemic-wearable/) | Open (ODC-By 1.0) | Free-living Empatica E4 HR, ACC, skin temp | **Tonight:** diurnal wrist-temp drift. |
| **PADS** (Tremor) | [PhysioNet](https://physionet.org/content/pads/1.0.0/) | Open (CC BY-NC-SA) | 469 subjects; watch tremor IMU (4–8 Hz) | **Proxy only:** 4–8 Hz ≠ 8–12 Hz rigors. |
| **MIMIC-IV Waveforms** | [PhysioNet](https://physionet.org/content/mimic4wdb/) | Open waves; cred. labels | 198 pts; ECG, PPG, Resp waveforms | **Tonight:** PPG→IBI; **Roadmap:** sepsis HRV. |
| **MC-MED** (Stanford ED) | [PhysioNet](https://physionet.org/content/mc-med) | Credentialed (1.5.0) | **118,385 ED visits**; ECG/PPG/Resp + EHR | **Roadmap #1:** ICU→ED bridge + sepsis labels. |
| **CovIdentify** / **MIMIC-IV-ED** / **eICU** / **TherLiD** | [CovID](https://physionet.org/content/covidentify/1.0.0/) · [M4-ED](https://physionet.org/content/mimic-iv-ed/2.2/) · [eICU](https://physionet.org/content/eicu-crd/) · [TherLiD](https://physionet.org/content/therlid/1.0.0/) | Credentialed (1.5.0 + CITI) | 2,887 wearables; 425k ED; >200k ICU; 13k IR-vs-core | **Roadmap:** external validation & IR temp calibration. |

*Audit of `docs/ideas/` datasets:* **WESAD** & **PPG-DaLiA** carry a **licence trap** (Siegen non-commercial despite UCI CC BY 4.0); **BIDMC** lacks IMU; **SisFall** is waist-only; **COUGHVID** is audio-only; **MIMIC-IV Demo** is v2.2; **TemPredict**/**DETECT** are non-public.

### 1.3 Modelling & Edge Impulse Capabilities
Code inspection (`training/`, `board/sepsis-monitor/python/`) exposed **five concrete flaws**:
1. **Post-onset contamination:** `train_gbm.py:46` samples positives across *all* `SepsisLabel==1` hours (`t_sepsis-6` to discharge), overweighting overt shock. Restrict positives to `[fp-6, fp+6]` ([Reyna et al., 2020](https://doi.org/10.1097/CCM.0000000000004145)).
2. **Test-set threshold leakage:** `meta.json` uses `0.58` swept on test patients (`threshold_sweep.py`) instead of validation (`0.614`). Lock strictly on validation.
3. **Miscalibrated `% sepsis risk`:** `class_weight="balanced"` shifts scores toward 50/50 ([Van Calster et al., 2019](https://doi.org/10.1186/s12916-019-1466-7)); at 1–2% prevalence, 85% sens / 15% FA yields **PPV ≈ 5–10%**. Bake a validation-fitted **Platt sigmoid** (`torch.sigmoid(a*logit + b)`) inside `to_onnx.py` and label UI **Deterioration Index (0–100)**.
4. **Domain shift, cold start & Hummingbird NaNs:** Within-patient baseline deltas (`last-base`, `max-base`, z-score; cf. [Morrill et al., 2020](https://doi.org/10.1097/CCM.0000000000004318)) cancel fixed temp offsets and COPD SpO₂ baselines. Lower `MIN_HOURS` 8→2 + `hours_observed`. Train with **80–95% SpO₂ dropout**, **±2°C Temp jitter**, and finite `age_since_last_valid_h` + `obs_frac_24h`—never pass raw `NaN`s into Hummingbird `gemm` ONNX ([Hummingbird #199/#436](https://github.com/microsoft/hummingbird)). Fix `HourlyVitals.add` (`model_runner.py:141`), which compresses multi-hour gaps into 1 hour, and add **2 h hysteresis** + staleness abstention.
5. **Edge Impulse Developer (free) plan:** Per [pricing](https://edgeimpulse.com/pricing) & [BYOM docs](https://docs.edgeimpulse.com/docs/edge-impulse-studio/bring-your-own-model), **dual learning blocks in one impulse** work natively—attach **[K-means](https://docs.edgeimpulse.com/docs/edge-impulse-studio/learning-blocks/anomaly-detection/anomaly-detection-k-means)** or **[GMM](https://docs.edgeimpulse.com/docs/edge-impulse-studio/learning-blocks/anomaly-detection/anomaly-detection-gmm)** alongside Keras Classification on `motion.py`'s `Spectral Analysis` block to flag loose straps / OOD motion *(K-means confirmed free; verify GMM UI unlock live)*. Classical ML and single-binary multi-impulse are Enterprise-only, so parallel `.eim` IPC runners ([example](https://github.com/edgeimpulse/example-multi-impulse-python)) fit UNO Q Linux. **[EON Tuner](https://docs.edgeimpulse.com/docs/edge-impulse-studio/eon-tuner)** (default space) and cloud Python SDK (`ei.model.profile`/`deploy`) work on free tier.

### 1.4 Novel On-Device Signals: Physics & SDK Audit
Inspecting `sketch.ino`, datasheets, and `samsung-health-sensor-api-1.4.1.aar` revealed:
- **Watch HRV (`IBI_LIST`) is ALREADY in our bundled SDK:** `javap` confirms `ValueKey.HeartRateSet` exposes `IBI_LIST` (ms) + `IBI_STATUS_LIST` (`status==0 && ibi!=0`) on the running `HEART_RATE_CONTINUOUS` tracker, and `SkinTemperatureSet` exposes `AMBIENT_TEMPERATURE` ([Samsung SDK](https://developer.samsung.com/health/sensor)). `PPG_CONTINUOUS` (25 Hz) suffers BioActive AGC step jumps—defer raw PPG-PI/RR to roadmap. *(Watch 8 awake continuous skin-temp cadence unverified.)*
- **LSM6DSOX aliasing & Nyquist:** `sketch.ino:101` sets `CTRL1_XL=0x30` (52 Hz ODR, LPF1 ~26 Hz BW, LPF2 off) yet polls at **25 Hz** (`f_N=12.5 Hz`), aliasing 12.5–26 Hz energy downward ([datasheet](https://www.st.com/resource/en/datasheet/lsm6dsox.pdf)). Shivering fires at **4–12 Hz** (peak 8–10 Hz). Streaming **52 Hz** fixes aliasing *and* captures rigors; else enable LPF2 (`CTRL1_XL |= 0x02`). **SCG/GCG** needs ≥208 Hz + gyro + rigid sternum adhesive (40 ms jitter destroys <20 ms septic RMSSD)—roadmap alongside ST's 15 µA **MLC** ([AN5259](https://www.st.com/resource/en/application_note/an5259.pdf)) and ≥100 Hz cough. **Posture (DC tilt) + ENMO** work at 25 Hz now.
- **Why `+3.5°C` wrist temp & chest Thermo fail:** Fever-onset vasoconstriction drops **wrist skin temp** as core rises; track **nocturnal baseline shift** ([Smarr et al., 2020](https://doi.org/10.1038/s41598-020-78355-6)) and **rapid cooling + tachycardia/rigors**. **[Modulino Thermo](https://docs.arduino.cc/hardware/modulino-thermo/)** ([HS3003](https://www.renesas.com/en/products/sensor-products/humidity-sensors/hs3003-high-performance-relative-humidity-and-temperature-sensor)/GXHT30C; *check IC rev*) near UNO Q (0.6–3 W) or torso absorbs board/body heat.
- **Modulino Light cannot do CRT—use it for sleep context:** **[Modulino Light](https://docs.arduino.cc/hardware/modulino-light/)** (`LTR-381RGB-01`) is a passive photodiode with **no LED emitter** or blanching mechanism. Pair `lux` with chest tilt + ENMO to separate *dark nighttime sleep* from *daytime lit-room collapse*.

### 1.5 Product, Workflow & 2026 Competitors
- **Alert fatigue & 4-tier funnel:** Under [NHS Virtual Wards guidance](https://www.england.nhs.uk/long-read/virtual-wards-operational-framework/) (30–40 beds, ~10–12 pts/nurse), 0.82 FA/pt-day = **~25 raw alerts/day per 30-bed ward** (vs 48/day NEWS2)—still unworkable for direct nurse paging. Funnel: *Tier 0* IMU motion gate → *Tier 1* haptic + 30 s IMU-verified still re-check + spot SpO₂ + symptom/urine check → *Tier 2* auto-escalate to **Carer on 5–10 min timeout** (delirium net) → *Tier 3* **SBAR card** to Virtual Ward/111 (hard **CG151** bypass). *(70–85% Tier-1 suppression to ~4–7 pages/day is illustrative, unverified prospectively.)*
- **Economics & 2025–2026 market autopsy:** UK sepsis costs **£1.5–2.0B/yr** (~245k cases, ~48k deaths; [UK Sepsis Trust](https://sepsistrust.org/about-sepsis/)). West Herts hit **£118/bed-day** vs £569 inpatient, while [WWL (2024)](https://www.pslhub.org/news/patient-safety-news/virtual-ward-costs-twice-that-of-inpatient-care-study-finds-r4354/) hit **£1,077 vs £536**—the overhead trap reshaping rivals:
  - **Isansys** (`K172329`, [MIB271](https://www.nice.org.uk/advice/mib271)): **liquidation (Jun 2025)** ([PKF](https://www.pkf-francisclark.co.uk/news/liquidators-seek-buyers-for-assets-of-isansys-lifecare-ltd/)).
  - **Current Health** (`K191272`): **Best Buy divested (Jun 2025)** after $475M impairment ([Healthcare Dive](https://www.healthcaredive.com/news/best-buy-divests-home-care-firm-current-health/754228/)).
  - **Biobeat** (`K241066`, no sepsis clearance): **$50M Series B (Jan 2026)** on US ABPM ([MedTech Dive](https://www.medtechdive.com/news/biobeat-raises-50m-cuffless-blood-pressure-monitor/736340/)).
  - **Masimo** (W1 + [SafetyNet Aug 2024](https://www.masimo.com/news-and-events/press-releases/press-release-view/ir-00898a-pr-510k-masimo-w1-connectivity-aug-2024-v6/)) & **iRhythm/VitalConnect** ([Oct 2026, ~$287.5M](https://www.globenewswire.com/news-release/2026/10/05/3163351/0/en/iRhythm-Completes-Acquisition-of-VitalConnect-Expanding-Its-Cardiac-Monitoring-Platform-Across-Ambulatory-Inpatient-and-Hospital-to-Home-Care.html)): enterprise cloud RPM.
  - **FDA sepsis AI:** [Prenosis `DEN230036`](https://www.accessdata.fda.gov/cdrh_docs/pdf23/DEN230036.pdf) & [Bayesian TREWS `K250680`](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K250680.pdf) (Apr 2026) are inpatient EHR/lab tools; **zero home wearable clearances**.
- **BOM, offline & regulation:** Prototype retail is ~£390+ ([UNO Q 2GB](https://store.arduino.cc/products/arduino-uno-q-2gb) £50–60, [Modulino Movement](https://store.arduino.cc/products/modulino-movement) £11–12, [Watch 8](https://www.techadvisor.com/article/2681534/samsung-galaxy-watch-8-release-date-price-specs.html) £319+)—state bluntly that Watch 8 proxies a ~£30–60 BLE BOM *(estimate, unverified)*. Local `.eim` enforces UK GDPR minimisation ([NHS DTAC](https://transform.england.nhs.uk/key-tools-and-info/digital-technology-assessment-criteria-dtac/)/DCB0129) and survives Wi-Fi drops; UK's **21 Oct 2026** [indefinite CE recognition](https://www.gov.uk/government/news/government-confirms-indefinite-recognition-of-ce-marked-medical-devices) streamlines Class IIa EU MDR entry.

---

## 2. New Routes (Beyond `docs/ideas/plan.md`)

| Route | Impact | Effort | Risk | What We'd Show |
|---|---|---|---|---|
| **A. Integrity & Calibration Rescue:** Fix `news2.py` float-band gaps (`20.5`/`24.5` score 0), `HourlyVitals` gaps & `sketch.ino` aliasing; retrain pre-onset `[fp-6, fp+6]` + within-patient deltas + `MIN_HOURS=2` + SpO₂ dropout + val threshold + Platt-ONNX + 2 h hysteresis | **Very High** | 2.0 h | Low (offline) | Calibrated validation metrics + lower FA/day; hour-2 scoring; `Deterioration Index`. |
| **B. Watch HRV (`IBI_LIST`) + Dynamic Skin Temp:** Extract `IBI_LIST`/`IBI_STATUS_LIST` + `AMBIENT_TEMPERATURE` in `SamsungSensors.kt`; resting RMSSD; drop `+3.5°C` | **High** | 1.5–2 h | Low–Med (APK) | Live resting RMSSD (ms) + personal skin-temp delta & cooling badge. |
| **C. Dual-Block 52 Hz IMU Impulse + EON Tuner:** 52 Hz stream; K-means/GMM anomaly alongside `still`/`moving`/`shiver-like`; resting-only hourly vitals | **High** | 2.5 h | Med (board) | Live motion class + strap-off anomaly gating RR/HR + EON Tuner footprint. |
| **D. 4-Tier Escalation, SBAR & "Unplug Wi-Fi":** Missed 10 s prompt → Carer/SBAR; top-3 tree drivers; NG253/CG151 fields; live Wi-Fi pull | **High** | 1.5–2 h | Low (UI) | Ignore alert prompt → auto-escalate to SBAR with top-3 drivers while Wi-Fi is off. |
| **E. Sickness-Behaviour + MyPHD Slide:** Chest tilt + ENMO + `lux` (night sleep vs daytime collapse); 30-min MyPHD drift check | **Med–High** | 1.5 h | Low | Live `Upright / Night sleep / Daytime recumbent` state + MyPHD slide. |

---

## 3. Things We Should Stop Claiming or Doing

1. **STOP quoting test-tuned `0.58` as unbiased held-out results** (`meta.json`) and **STOP showing uncalibrated `class_weight="balanced"` scores as `"% sepsis risk"`** (`dashboard.html:229`).
2. **STOP calling 4 vitals "NEWS2"**—fix `news2.py:16–19` (`20.5`/`24.5`/`8.5` currently return `0`), label **Incomplete NEWS2**, keep Scale 2 clinician-locked.
3. **STOP claiming `skin_temp_c + 3.5°C` (`main.py:33`) detects fever or CG151 >38°C**—vasoconstriction drops wrist temp at onset.
4. **STOP pitching chest-mounted Thermo `T_skin−T_ambient` as a shock proxy** (board+body heat) and **STOP pitching Modulino Light for CRT/perfusion** (no emitter LED).
5. **STOP claiming a tap-test measures ACVPU "new confusion"**—delirious patients ignore prompts; use timeouts as **carer triggers**.
6. **STOP citing NICE NG51** (use **NG253**), **25 Hz SCG/HRV** (needs ≥208 Hz + rigid mount), or **COUGHVID/SisFall/WESAD/PPG-DaLiA** without audio/waist/non-commercial caveats.

---

## 4. Ranked Shortlist

### Top 5 Doable by Sunday 12:00
1. **Route A (~2 h):** Fixes silent bugs (`news2.py`, `HourlyVitals`, aliasing), test leakage, cold start, and miscalibration offline.
2. **Route C (~2.5 h):** Makes Edge Impulse the centerpiece (52 Hz rigors + OOD strap anomaly + resting gating + EON Tuner).
3. **Route D (~1.5–2 h):** Delirium-safe timeout escalation, top-3 tree drivers, NG253/CG151 fidelity, offline theater, and 2025–2026 market autopsy.
4. **Route B (~1.5–2 h):** Unlocks `IBI_LIST` resting RMSSD already in our bundled Samsung SDK and drops `+3.5°C`.
5. **Route E (~1.5 h):** Rescues Modulino Light for sleep/collapse gating and empirically answers the ICU-to-home critique on MyPHD.

### Top 3 Roadmap (Post-Hackathon)
1. **Pre-ICU Domain Bridge (`MC-MED` + `CovIdentify` + `TherLiD`):** Discrete-time survival + rough-path signatures on 118k ED waveforms and 2.8k free-living infections.
2. **Full-Rate Multimodal Edge Sensing:** Offload posture/shivering to LSM6DSOX's 15 µA MLC; add AGC-robust `PPG_CONTINUOUS` PI, 208 Hz rigid-mount SCG/GCG, and ESL-EPFL chest-IMU cough ([Zenodo 7562332](https://doi.org/10.5281/zenodo.7562332)).
3. **Scaled £30–60 BLE BOM + Prospective NHS Virtual Ward Pilot:** Replace the £319 Watch 8 dev proxy with commodity BLE sensors + edge hub under NHS DTAC/DCB0129 and UK indefinite EU MDR CE recognition.
