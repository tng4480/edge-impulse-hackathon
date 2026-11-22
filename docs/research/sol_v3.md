# Hardware demos for Sunday

Build the chest strap's LED demo first. If the STM32 export runs on time, add a watch buzz that asks the wearer to recheck. The detected Movement module is enough for both. Use the held-out ICU replay for the sepsis alert and label the volunteer demo as live sensor data. The deployed trend model needs at least eight hours of readings, and the ICU results give no estimate of performance at home. [Board](../../board/README.md) · [Watch](../../wearos/README.md) · [Results](../results.md)

Scores are stage impact × chance of shipping within eight hours, each out of five. Times are build estimates including up to an hour of team recordings. Use a fresh Edge Impulse project for the chosen sensor dataset. Experiments within one project share its dataset. Hold out a volunteer or an entire recording session for rehearsal. [Edge Impulse experiments](https://docs.edgeimpulse.com/studio/projects/experiments)

## 1. A chest strap that shows what it senses · 5 × 4 = 20 · 3–4 h

Use the Movement accelerometer at the existing 25 Hz. Train an Edge Impulse spectral classifier on three-second clips of quiet breathing, walking, strap handling and acted shivering. Deploy a quantized Arduino/C++ build on the STM32. Drive the onboard 8×13 LED matrix directly from the sketch and keep the existing respiratory-rate estimator on Linux. Reach for the Vibro only if it passes a bench check. [Arduino UNO Q](https://docs.arduino.cc/tutorials/uno-q/user-manual) · [Edge Impulse spectral analysis](https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/spectral-analysis) · [Arduino export](https://docs.edgeimpulse.com/hardware/deployments/run-arduino-1-18)

**30 s.** Start with the strap on and a steady icon. Walk, mimic a shiver, then stop. Repeat the motion with the Linux consumer paused and the board still powered. Project a close-up of the matrix. Rehearse the pause with the exact demo setup.

Fast breathing matters in suspected sepsis, and NICE asks about recent rigors. The motion model can flag a shiver-like event for confirmation. Acted shivering cannot establish sensitivity to real rigors. Main risk is the UNO Q compile or inference disrupting 25 Hz sampling. Timebox MCU integration to 90 minutes, then use a Linux `.eim` and send the icon over Bridge. [NICE risk criteria](https://www.nice.org.uk/guidance/ng253/chapter/Evaluating-risk) · [NICE assessment](https://www.nice.org.uk/guidance/ng253/resources/suspected-sepsis-in-people-aged-16-or-over-recognition-assessment-and-early-management-pdf-66144015386053) · [Edge Impulse Linux SDK](https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/python)

## 2. A watch buzz that asks for another reading · 4 × 4 = 16 · 2–3 h after #1

Reuse the chest classifier and its dataset. Add walk-to-rest takes to check it during transitions. On sustained poor signal, return a prompt ID in the watch uplink response. The watch vibrates once per ID and shows “Sit still for a breathing check.” Publish a fresh rate once the estimator confirms it. [Android haptics](https://developer.android.com/develop/ui/views/haptics/haptics-apis)

**30 s.** Walk, show the buzz and prompt, sit, and show the fresh-sample countdown. Leave the number for later. The current estimator can need a 30-second motion-free window plus settling checks.

This can recover a missing respiratory observation. It needs the local watch link, and a cleaner signal alone cannot establish clinical accuracy. Duplicate or late prompts are the main risk. [Board](../../board/README.md) · [Watch](../../wearos/README.md)

## 3. Chair-rise check · 3 × 5 = 15 · 2–4 h

Use the chest IMU and a short-window Edge Impulse activity classifier for sitting, rising and standing. Record normal and deliberately slow rises plus reaches and repositioning. Time the transition from the raw trace and compare with video timestamps.

**30 s.** Rise normally, then slowly. Put both movement traces and the two durations on screen. Acute loss of function can matter in suspected sepsis. A chair rise is one repeatable observation, with no clinical threshold established here. Chair height, arm use and strap placement can dominate the timing. [NICE risk criteria](https://www.nice.org.uk/guidance/ng253/chapter/Evaluating-risk)

## 4. A cough that both sensors catch · 4 × 3 = 12 · 4–6 h

Record synchronized laptop mic and chest IMU clips of voluntary coughs, speech, claps and another person's coughs. Stream timestamped mic chunks over the local network to an Edge Impulse audio MFE classifier running as a Linux `.eim` on the UNO Q. Confirm an audio candidate only when a chest acceleration burst is close in time. [Edge Impulse audio MFE](https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/audio-mfe)

**30 s.** A teammate coughs nearby, then the wearer coughs. Show the mic firing twice and the strap corroborating the second event. A cough history may help a clinician consider a respiratory source. The prototype cannot distinguish infectious coughs. Stage noise and audio buffering are the main risks. [NICE respiratory infection guidance](https://www.nice.org.uk/guidance/ng237/chapter/Recommendations)

## 5. Camera backup for the breathing strap · 4 × 3 = 12 · 5–7 h

Use a fixed phone or laptop camera and a visible marker on the upper chest. Track its vertical motion and estimate rate from the waveform. Train a small Edge Impulse time-series classifier to accept or reject tracked windows. Record paired video and strap traces during still breathing, talking and camera bumps, with manual breath counts.

**30 s.** Start both live traces early, unplug Movement, then cover the marker. Show the camera take over and then withhold its reading. Respiratory rate stays available during a strap dropout if the wearer and camera are still. Both can fail during body motion, and agreement on stage does not validate accuracy. [Smartphone respiratory-rate validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC9053269/) · [NICE risk criteria](https://www.nice.org.uk/guidance/ng253/chapter/Evaluating-risk)

## 6. Film fingertip colour returning · 5 × 2 = 10 · 5–7 h

Use the phone rear camera under fixed illumination. Record press-and-release clips plus motion and lighting failures. Train a small Edge Impulse image classifier to reject bad framing. Use fingertip colour over time to show the refill curve.

**30 s.** Show the fingertip and its colour trace together, then move off target to show rejection. Clinicians use capillary refill to assess peripheral perfusion in septic shock. Healthy volunteer traces cannot establish screening performance. Exposure changes, skin tone and variable pressure are the main risks. [ANDROMEDA-SHOCK-2](https://jamanetwork.com/journals/jama/fullarticle/2840823)

## 7. Watch pulse signal quality · 4 × 2 = 8 · 5–7 h

First verify raw continuous PPG and wrist acceleration on this watch and SDK build. Record snug, loose and moving conditions. Train an Edge Impulse time-series classifier on synchronized PPG and motion windows and run it on UNO Q Linux.

**30 s.** Show a pulse waveform, loosen the watch, then reseat it and recover the trace. This would flag poor data before interpreting heart-rate trends. It cannot measure shock or validate SpO₂. SDK access and tracker timing are the main risks. [Samsung sensor specifications](https://developer.samsung.com/health/sensor/guide/data-specifications.html)

## Build order

Prove the LED and 25 Hz capture first. Collect up to an hour of clips, then train and export #1. Use any remaining time through hour six for #2 and reserve the last two hours for an unplugged-internet rehearsal and labelled ICU replay. If the watch prompt slips, ship the matrix demo alone.
