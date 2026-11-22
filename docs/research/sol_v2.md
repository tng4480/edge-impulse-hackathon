# From a wearable alert to a nurse taking ownership

**Sunday recommendation.** Build the first ten minutes after an alert for an adult surgical patient recovering on a virtual ward. Let the wearer see which reading the device trusts, let a nurse accept the review on a second screen, and show what happens when the watch link drops. Keep the ICU replay, live volunteer measurements and simulated workflow visibly labelled. [NHS England virtual ward guidance](https://digital.nhs.uk/data-and-information/information-governance/guidance/virtual-wards)

## The current ceiling

- **Patient.** A score and an SBAR card still leave someone at home wondering whether to recheck, call, or wait. Show one clear action, its reason, and who will respond. Make it possible to report feeling worse regardless of sensor availability.
- **Clinical pathway.** Acknowledging a prompt and accepting clinical responsibility are different actions. Show the review owner and whether they received and acted on the request. A second screen makes this tangible.
- **Demo.** A success-only replay makes the hardware feel incidental. Move until the UNO Q withholds a noisy breath estimate, then show a real check-in and a labelled replay that creates one review task. Inject a failure the judges can see and recover from.
- **Evidence.** At validation-matched catch rates, the held-out ICU results are 78% vs 76% caught, 0.91 vs 1.61 false alert episodes per patient-day, 22% vs 16% of non-sepsis hours in alert, and median leads of 20 vs 17 hours. At matched alarm time, catches are 70% vs 76%. The comparator uses four NEWS2 vitals. The promising product hypothesis is fewer nurse interruptions, and actual review workload and home performance remain unmeasured. [Team results](../results.md)
- **Edge Impulse.** Show the running Linux aarch64 BYOM `.eim` and its output during internet loss. The STM32 acquires the chest IMU, and the UNO Q Linux app runs inference and the local workflow. The two current Studio datasets are ICU and speech. Experiments share their project's dataset. Plan the demo around those two projects and use the working respiratory signal processing for live motion rejection. [UNO Q](https://docs.arduino.cc/hardware/uno-q/) · [BYOM](https://docs.edgeimpulse.com/studio/projects/dashboard/byom) · [Linux SDK](https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/python) · [Experiments](https://docs.edgeimpulse.com/studio/projects/experiments)

## 20 expansion routes

| Route | What changes |
| --- | --- |
| 1. Review-budget benchmark | Score the alert policy under two workload limits. |
| 2. Owned handoff | A nurse claims, reviews and closes a task with an action. |
| 3. Outage and sensor fault lab | Replay link failures and stale readings through the actual board app. |
| 4. Recovery trajectory | Compare today's resting signals with the patient's own time-of-day and recovery baseline. |
| 5. Oximetry equity test | Measure how plausible sensor bias and missingness change downstream alerts. |
| 6. Camera backup for breaths | Use prompted torso video when the chest strap is off. |
| 7. Care-home shift check | Let staff record concrete changes from a resident's normal routine. |
| 8. Oncology contact card | Bring up the patient's existing urgent contact pathway when they feel unwell. |
| 9. One measurement at a time | Ask for the missing observation most likely to change a review decision. |
| 10. Accessible check-in | Offer voice, large buttons and carer entry as alternative input methods. |
| 11. Local language assistant | Benchmark a small quantized model on the UNO Q for rephrasing human-approved instructions, with a template fallback. Runtime and fidelity are unverified. [Candidate model](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) |
| 12. Low-connectivity outreach | Give a visiting worker a local inbox and an explicit sync receipt on return to coverage. |
| 13. Maternal follow-up | Co-design a postpartum contact workflow around the maternity team's plan and maternal reference measurements. |
| 14. Paediatric follow-up | Design a parent-assisted observation workflow for age-specific assessment and sensor fit. |
| 15. Charging and wear planner | Find risky observation gaps around charging, handovers and sleep. |
| 16. Assisted observations | Pair a nurse-entered cuff or thermometer reading with its acquisition time and device provenance. |
| 17. Cross-site replay | Lock the pipeline, then test how much survives an ICU-to-ED shift. |
| 18. Per-site review staffing | Replay arrival bursts and compare queue delays across staffing schedules. |
| 19. At-home measurement coaching | Learn which brief prompts help wearers obtain a usable reading on the first retry. |
| 20. Shared-device checkout | Match the watch and chest strap to the correct episode and reset data at discharge. |

## Shortlist in build order

The eight route numbers above also give the ranking. Hours are hands-on engineering estimates. Roadmap estimates cover a first implementation or analysis and exclude recruitment, approvals and integration lead times.

### 1. Review-budget benchmark

**Who and why.** A virtual ward lead can judge how many patients get a timely review for a given workload. An honest win needs to survive a stronger comparator.

**By Sunday, 3–4 h.** Cache hourly outputs from the frozen BYOM model and use `training/strict_eval.py` on the laptop. Compare the current four-vital rule, the rule with the same debounce and clear logic, the current model, and a candidate policy that requests one bounded recheck after a model-only alert. Keep the severe four-vital trigger immediate in both policy arms. Choose one candidate on validation constrained by both false episodes per patient-day and non-sepsis hours in alert versus the debounced rule. Report if no point satisfies both. On the already reported test cohort, show the 24 h catch rate, fresh starts 2–12 h before onset, missed cases, and paired patient-bootstrap intervals alongside both burdens. Distinguish standing alerts from new reviews. Use the UNO Q `.eim` to verify scores on one fixture. Rechecks mapped to the next recorded hour are simulations, and the reanalysis is exploratory. [Evaluation script](../../training/strict_eval.py) · [PhysioNet 2019, CC BY 4.0](https://physionet.org/content/challenge-2019/1.0.0/#access)

**Demo.** Two policies compete on the same replay, and the review counter shows the cost of a standing alert.

**Risk and roadmap, 16–30 h.** Matching both limits may cost catches. Pre-register an independent evaluation that includes unobservable time, symptom bypass and time to accepted review. Stanford MC-MED can test transport to a monitored ED under a separately defined outcome and shorter observation windows. It needs credentialing and a signed DUA. [MC-MED v1.0.1, PhysioNet Credentialed Health Data License 1.5.0](https://physionet.org/content/mc-med/1.0.1/)

### 2. Owned handoff on the local network

**Who and why.** The wearer sees whether someone accepted their review. The virtual ward gets an actionable item with the trigger, current evidence and its age.

**By Sunday, 3–4 h.** On UNO Q Linux, attach an SQLite task to each episode from the deployed BYOM `.eim` or independent rules. Separate live and replay IDs and timers. Store one record through `pending → accepted → resolved`, with wearer acknowledgement as its own timestamp. Snapshot the existing SBAR with source, time, missing fields and score engine. Use a phone or laptop browser on the hotspot to accept and log a simulated action. Verify refresh and repeated requests leave one task. Seed the roster with a public-domain SyntheticMass identity and use labelled ICU or synthetic alert inputs. [SyntheticMass downloads](https://synthetichealth.github.io/downloads.html) · [Data terms](https://github.com/synthetichealth/synthea/wiki/DPG#does-it-use-an-appropriate-open-license) · [PhysioNet 2019, CC BY 4.0](https://physionet.org/content/challenge-2019/1.0.0/#access)

**Demo.** A nurse accepts the case from a second screen and the wearer sees the named owner and time.

**Risk and roadmap, 12–24 h for sandbox integration.** An accepted task can still sit idle. Add a staffed fallback and a review deadline. Map synthetic local exports to FHIR R4 `Task`, `Observation` and `Provenance`, validate against the receiving provider's profiles, and add identity, authorization and secure transport. NHS booking and referral is a provider-to-provider service. The Sunday route is local. [FHIR Task](https://hl7.org/fhir/R4/task.html) · [Observation](https://hl7.org/fhir/R4/observation.html) · [Provenance](https://hl7.org/fhir/R4/provenance.html) · [NHS England BaRS](https://digital.nhs.uk/developer/api-catalogue/booking-and-referral-fhir)

### 3. Outage and sensor fault lab

**Who and why.** Home users and judges can tell which parts still work when the connection or a reading stops. Tests can reproduce the failure.

**By Sunday, 2–3 h.** Feed the UNO Q board app an attributed PhysioNet trace with deterministic gaps and synthetic watch fixtures with duplicates, future timestamp skew and a repeated old `spo2_t`. Test the watch's documented one-hour queue. On reconnect, keep historical samples out of current-alert evaluation and give each observation its true age where available. Show separate states for watch link, reading availability and inference engine. Cut upstream internet with the LAN intact, then test watch-to-board loss separately. Log fresh-data recovery and whether the Linux BYOM runner remained active. [PhysioNet 2019, CC BY 4.0](https://physionet.org/content/challenge-2019/1.0.0/#access) · [Watch uplink contract](../../wearos/README.md)

**Demo.** The dashboard keeps scoring a labelled replay offline, and a real watch disconnect visibly ages its separate live reading.

**Risk and roadmap, 12–20 h.** Hotspot client isolation, clock skew and process restarts can spoil a live run. Measure coverage with faults both singly and together. Add persistent sync receipts, encrypted transport and power-loss recovery for real deployments.

### 4. A baseline that follows recovery

**Who and why.** A post-discharge nurse can see whether a patient is drifting away from their usual resting pattern or recovering as expected.

**By Sunday, 2–3 h.** Import one subject's five-minute Galaxy Watch Active 2 HR and motion CSV windows. Fit resting median and dispersion by time of day on earlier days, freeze them, and plot later days and a labelled injected drift. Add a contextual panel to the UNO Q dashboard. Fresh Watch 8 HR and chest stillness can populate a live observation with a pending baseline. Keep HRV and skin temperature as context. [Galaxy Watch dataset and CC BY 4.0 metadata](https://api.figshare.com/v2/articles/28509740) · [Collection study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12375003/)

**Demo.** Two readings with the same pulse get different context because one has moved away from the wearer's usual resting range.

**Risk and roadmap, 12–24 h.** Healthy participants and older watch hardware limit transport. Postoperative recovery itself shifts the baseline. Fit a clinician-approved recovery trajectory, freeze updates when data are sparse or a review is open, and compare the median rule with EI Raw Data → K-means Anomaly Detection on fixed standardized resting summaries in a future project. Quantify alert rate and coverage before using it for prompts. [Raw Data](https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/raw-data) · [K-means](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/anomaly-detection-k-means)

### 5. Oximetry equity and uncertainty

**Who and why.** Wearers and clinicians can see how much the decision depends on a peripheral oxygen estimate, including under conditions where devices can overestimate saturation.

**By Sunday, 2–3 h.** Replay the same ICU patient through the frozen BYOM impulse with SpO₂ unchanged, absent, and shifted upward by illustrative 1, 2 and 4 percentage points, capped at 100%. Rebuild its causal feature windows each time. Compare alert flips, lead-time loss and score availability across patients. Show the score's dependence on the spot value and its age. Label the shifts as synthetic stress scenarios. [PhysioNet 2019, CC BY 4.0](https://physionet.org/content/challenge-2019/1.0.0/#access) · [FDA oximeter evidence and guidance status](https://www.fda.gov/medical-devices/products-and-medical-procedures/pulse-oximeters)

**Demo.** The replay shows how an over-read changes the same case's alert timing.

**Risk and roadmap, 16–30 h.** Audit error and failed reads by device, measured pigmentation and saturation range against paired arterial SaO₂. OpenOximetry requires registration and a signed DUA. Relevant Watch 8 pairs are unverified. Compare parallel policies with and without a usable SpO₂ input and obtain Watch 8 reference data before making a device-specific claim. Never infer skin tone from the device or use race as a numeric correction. [OpenOximetry v1.1.1, PhysioNet Restricted Health Data License 1.5.0](https://www.physionet.org/content/openox-repo/1.1.1/)

### 6. Camera fallback for respiratory rate

**Who and why.** A wearer can attempt a short respiratory observation when the chest strap is unavailable. A contactless trace makes sensor redundancy visible.

**By Sunday, 3–5 h if a working camera is at hand.** Use a laptop webcam or a phone's native clip locally. In OpenCV track vertical optical flow in a fixed torso box and subtract motion in a background box. Resample by frame timestamp, then estimate respiratory periodicity over 30–45 s. Reject poor tracking, moving camera and weak periodicity. Pass rate, time and quality to the separate UNO Q context panel. Keep frames local with no raw video retention. Compare a consenting volunteer with a simultaneous timed manual count. Camera access from the board's plain HTTP page needs a secure-context solution, so start with native capture or laptop localhost. [Capture specification](https://www.w3.org/TR/mediacapture-streams/) · [MPSC-RR belt-labelled RGB, CC BY 4.0](https://huggingface.co/datasets/justchugh/MPSC-RR)

**Demo.** The camera returns a breath rate at rest, withholds it during movement, and recovers when the signal clears.

**Risk and roadmap, 16–28 h.** Clothing, talking and camera shake can produce plausible false rates. Test on held-out people against the belt and publish error versus coverage. Try a separate EI Raw Data → Regression impulse on torso-motion series and compare it with the simple estimator. Deploy a Linux `.eim` only if it improves coverage at a matched error level. [EI Regression](https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/regression)

### 7. Care-home shift check

**Who and why.** A night-shift carer can report a change from a resident's normal mobility, intake or alertness, even if the resident cannot use the watch.

**By Sunday, 2–3 h.** On the phone's local page, capture who saw the change, when, what the resident's usual pattern is, and the next agreed check. Use a deterministic check-in beside the existing EI score, which stays contextual. Use TIHM to inform event types and gaps in a synthetic shift handoff. The study took place in private homes of people with dementia. Credit the Surrey and Borders Partnership NHS Foundation Trust as requested by the authors. [TIHM dataset, CC BY 4.0](https://zenodo.org/records/7622128) · [Licence metadata](https://zenodo.org/api/records/7622128)

**Demo.** A carer records a functional change and the next shift sees the observation with its author and time.

**Risk and roadmap, 12–20 h.** Capacity, consent and differences between private homes and care homes affect use. Pilot with staff and test accessible completion and handoff time. If speech helps, keep the Audio MFCC → Classification digit impulse as an optional input, with a tap or carer route. Route a missed or misheard response to a human check and leave NEWS2 consciousness assessment to a clinician. [EI Audio MFCC](https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/audio-mfcc)

### 8. Oncology contact card

**Who and why.** A patient who becomes unwell on anticancer treatment can find their oncology team's contact plan immediately, including when the trend score is low or unavailable.

**By Sunday, 1–2 h.** Configure one synthetic treatment episode, last treatment date and a demo contact card. Pressing “I feel unwell” opens the card immediately. The existing EI BYOM score can populate the handoff as context but is outside the decision path. Test low score, empty history and disconnected watch using public-domain Synthea patient data plus authored symptom fixtures. [SyntheticMass](https://synthetichealth.github.io/downloads.html) · [Data terms](https://github.com/synthetichealth/synthea/wiki/DPG#does-it-use-an-appropriate-open-license) · [NICE CG151, rec. 1.3](https://www.nice.org.uk/guidance/cg151/resources/neutropenic-sepsis-prevention-and-management-in-people-with-cancer-pdf-35109626262469)

**Demo.** The patient reports feeling unwell and the oncology contact appears despite an unavailable model score.

**Risk and roadmap, 12–20 h.** Trust instructions and phone numbers vary. Co-design the screen with an acute oncology service and simulate time to contact across outages and shifts. Maintain the service's own approved instructions. [Leeds NHS oncology card](https://www.leedsth.nhs.uk/patients/resources/chemotherapy-smartcard/)

## Three moonshots

1. **A virtual ward that buys review time.** Sell a post-surgical monitoring service with an accountable reviewer and measure time to adjudicated appropriate review per staffed nurse-hour. Start with shadow use, then compare with existing ward practice and track missed deterioration and unintended workload. A 905-person surgical remote-monitoring trial found no significant increase in days alive at home, so clinical value needs its own trial. [PVC-RAM-1 trial](https://pubmed.ncbi.nlm.nih.gov/34593374/) · [DECIDE-AI](https://pmc.ncbi.nlm.nih.gov/articles/PMC9116198/)
2. **A home-to-ED measurement cohort.** Collect paired wearable and clinical reference vitals from discharge through community or ED review. Record observation gaps, medications, symptoms, alternate causes and adjudicated outcomes. Hold out sites and device versions to quantify separately how much performance changes with device error, sparse capture and patient population.
3. **A wearable that asks for the next observation.** Compare a policy that spends one short prompt on the most informative fresh measurement with a fixed check-in schedule. First build an open replay simulator that models battery, motion, oximetry error and prompt response independently. Then measure time to review at matched measurement burden and missed-case rate in a prospective study, including coverage by pigmentation and accessibility needs.

## The next 13 hours

| UK time | Owners and order |
| --- | --- |
| Sat 21:00–22:00 | Human A checks real watch POSTs, chest RR, hotspot and `.eim` parity. The board POST allowlist and the watch README currently disagree on optional fields, so test the actual payload first. Human B freezes the adult virtual ward script and one handoff payload with source, age, episode ID, owner and action. |
| 22:00–01:00 | Agent 1 builds the episode ledger and local claim screen. Agent 2 creates deterministic fault fixtures and freshness display. Agent 3 runs the locked replay comparison. Use separate files or agreed interfaces. Human A handles board, watch and hardware. Human B tests the two roles and builds the evidence slide from completed results. |
| 01:00–02:00 | Integrate once and run healthy, sepsis, and link-loss cases. Check that replay cannot create a live task, a repeat acceptance cannot duplicate it, and stale spots never look new. Correct the existing SBAR's percentage-risk wording. Save a known-good build. |
| 02:00–08:00 | Let deterministic replays finish unattended and reserve the time for rest. |
| 08:00–10:00 | Rehearse twice and record a local backup with genuine on-board inference visible. If the new benchmark misses either burden limit, show the existing held-out results and both trade-offs. If the watch link is intermittent, keep the working live chest demo and use labelled link-failure fixtures. |
| 10:00–12:00 | Leave two hours for submission and hardware recovery. Add a speech clip only if the second `.eim` already works with a held-out speaker on the real recording path. Camera, new training projects and Qwiic fixes can wait. |

**Three-minute pitch.** 0:00–0:25, show who is waiting for help between post-operative checks. 0:25–0:55, move and sit to show the chest estimate disappear and return. 0:55–1:40, run the trace labelled “Recorded ICU case · accelerated” with the internet cut and let a review task appear. 1:40–2:20, have the nurse accept on the second screen and show the wearer the receipt. 2:20–3:00, put catch rate, false episodes and alarm hours on one slide, explain the longer time in alert, and ask for a shadow virtual ward pilot that measures actual response and workload.
