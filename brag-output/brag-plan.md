# Launch video plan: Sepsis monitor

**Angle.** Sepsis is found late, and late is expensive. A watch people already wear, plus a small board at home, can raise the alarm earlier without adding a routine. Tone: polished (restrained, long holds, soft fades). Format: landscape 1920x1080, 30 fps, 26.25 s.

**Hook.** "36% of sepsis cases are detected late." The number counts up in the first second.

**Music.** 96 BPM (one beat = 0.625 s), 42 beats = 26.25 s. Every cut, reveal chime, thud and arpeggio note sits on that grid. A heartbeat pulse (lub-dub) runs under the problem scenes and turns into a soft kick when the product arrives. Key: A minor, progression Am F C G.

**Look.** Problem scenes on warm paper (#f6f3ec, ink #1b1e19, accent #c4472a). Product scenes on the Pine dark theme (#101815, text #E2ECE5, mint #9CD9B1). Instrument Serif numbers, Geist text, Geist Mono labels. These are the board pages' own tokens, from `ui.css`.

## Storyboard (beats from the start)

| # | Beats | Time | Theme | Content |
|---|---|---|---|---|
| 1 | 0-6 | 0.00-3.75 | paper | **36%** of sepsis cases are detected late. |
| 2 | 6-14 | 3.75-8.75 | paper | **£830m** NHS spend on hospital care for sepsis. Then **+4%** higher odds of death for each hour antibiotics wait (Seymour et al., NEJM 2017). |
| 3 | 14-22 | 8.75-13.75 | pine | **6x** more likely to get community-acquired sepsis with stage 5 kidney disease. "We watch them first." |
| 4 | 22-29 | 13.75-18.125 | pine | The product in use. Real watch app and real dashboard. A watch they already wear; chest sensor adds breathing; room sensor adds temperature and light; scored on the board, no cloud. |
| 5 | 29-37 | 18.125-23.125 | pine | **78%** flagged before onset, **20 h** median warning, **43%** fewer false alerts than NEWS2 at the same catch rate. Footer: held-out ICU patients, not yet validated at home. |
| 6 | 37-42 | 23.125-26.25 | pine | Sepsis monitor. Early warning at home. Decision support, not a diagnosis. Edge Impulse, Arduino UNO Q, Galaxy Watch. |

## Sources for each number

- 36% late, £830m NHS spend, 6x stage 5 CKD: supplied by the team. Not independently verified by search.
- +4% per hour of antibiotic delay: Seymour et al., NEJM 2017 (odds ratio 1.04 per hour).
- 78%, 20 h, 43%: `docs/results.md`, strict patient-level evaluation, model v1 at cutoff 0.55, 476 sepsis and 7,422 non-sepsis held-out PhysioNet 2019 patients.

## Honesty rules

The model figures are retrospective ICU data and the footer on screen says so. The device does not beat NEWS2 on catches per alarm hour, so the video claims only what the data shows: earlier, and fewer separate alarms at the same catch rate.
