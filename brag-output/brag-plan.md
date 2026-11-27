# Sepsis Watch launch video

**Angle.** Sepsis is found late, and late is expensive. A watch people already wear, plus a small board at home, can raise an alert. Format is landscape 1920 × 1080 at 30 fps, about 29 seconds.

**Hook.** "36% of sepsis cases are detected late." The number counts up in the first second.

**Music.** The original 96 BPM score repeats one bar under the extended product scene. A heartbeat pulse runs under the problem scenes and turns into a soft kick when the product arrives.

**Look.** The first two scenes use the original bright red (#FF4D2E). The video then transitions to the app's Pine dark theme (#101815 background, #E2ECE5 text and #9CD9B1 mint). Type is Archivo, Inter Tight and JetBrains Mono.

## Storyboard (beats from the start)

| # | Beats | Time | Theme | Content |
|---|---|---|---|---|
| 1 | 0-6 | 0.00-3.75 | Red | **36%** of sepsis cases are detected late. |
| 2 | 6-14 | 3.75-8.75 | Red | **£830m** NHS spend on hospital care for sepsis. Then **+4%** higher odds of death for each hour antibiotics wait (Seymour et al., NEJM 2017). |
| 3 | 14-22 | 8.75-13.75 | pine | **6x** more likely to get community-acquired sepsis with stage 5 kidney disease. "We watch them first." |
| 4 | 22-33 | 13.75-20.625 | pine | The connected watch and its sensors feed the board. The dashboard shows a deterioration alert during a recorded ICU replay. Then a separate simulated “I feel unwell” check-in appears in the nurse queue and a nurse accepts it. |
| 5 | 33-41 | 20.625-25.625 | pine | **78%** flagged before onset, **20 h** median warning, **43%** fewer false alerts than NEWS2 at the same catch rate. Footer: held-out ICU patients, not yet validated at home. |
| 6 | 41-46 | 25.625-28.75 | pine | Sepsis Watch. Early warning at home. Decision support, not a diagnosis. Edge Impulse, Arduino UNO Q, Galaxy Watch. |

## Sources for each number

- 36% late, £830m NHS spend, 6x stage 5 CKD: supplied by the team. Not independently verified by search.
- +4% per hour of antibiotic delay: Seymour et al., NEJM 2017 (odds ratio 1.04 per hour).
- 78%, 20 h, 43%: `docs/results.md`, strict patient-level evaluation, model v1 at cutoff 0.55, 476 sepsis and 7,422 non-sepsis held-out PhysioNet 2019 patients.

## Honesty rules

The model figures are retrospective ICU data and the footer on screen says so. The device does not beat NEWS2 on catches per alarm hour, so the video claims only what the data shows: earlier, and fewer separate alarms at the same catch rate.
