# Speech check on the watch: findings (Saturday evening)

## Is there a ready model?

No. Neither Hugging Face nor Edge Impulse has a slurred-speech or dysarthria *detector* ready to use. The closest, `jmaczan/wav2vec2-large-xls-r-300m-dysarthria`, is a speech-to-text model fine-tuned on dysarthric speech, not a classifier.

## Baseline we trained (`training/speech_baseline.py`)

- **Data:** TORGO, via HF `abnerh/TORGO-database`: 16,544 clips from 15 speakers. 8 have dysarthria (cerebral palsy or ALS) and 7 are controls. The licence is research use.
- **Method:** MFCC summary features into LightGBM, scored **leave-one-speaker-out**. No speaker's clips were seen during training.

| Measure | AUC |
|---|---|
| Per clip | 0.635 |
| Per speaker (mean of clip scores, 15 points) | 0.77 |
| Per clip, head-worn mic only | 0.669 |
| Per clip, array mic only | 0.592 |

- Healthy speaker MC04 scores 0.64, higher than three of the eight dysarthric speakers. Dysarthric F03 is called healthy on 93 % of clips.
- Performance falls when the microphone is held fixed, so part of the signal is the recording setup. arXiv 2509.19946 warns about the same bias.

## Decision

Don't ship a "slurred speech" classifier. It doesn't generalise to new speakers, the data is chronic dysarthria rather than acute change, and slurring is also a stroke sign.

Build a **speech and confusion check** on the watch instead:

1. **Confusion is the sepsis sign.** New confusion is the C in NEWS2's ACVPU and is part of qSOFA. The prompt is "say the months backwards from December", as in the 4AT bedside test.
2. **Edge Impulse keyword spotting recognises the month words.** Errors or long pauses count as a failed check, which feeds the consciousness item of NEWS2 (3 points).
3. **Change against the wearer's own baseline.** One recording at setup, then speaking rate and pause pattern compared at each check. A large change prompts a review; it does not diagnose.

It needs its own Edge Impulse project, because impulses in one project share a dataset.
