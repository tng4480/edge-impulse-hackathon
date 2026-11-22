"""Pathway rules that no model score can veto.

    profile = {"type": "chemo", "last_treatment_date": "2026-11-12"}
    manual  = {"oral_temp_c": 38.3, "feel_unwell": False, "something_wrong": False,
               "soft_signs": ["new_confusion"], "by": "carer"}
    for trig in evaluate(profile, vitals, manual):
        handoff.open_task(trig["task_source"], trig["rule"], sbar(trig, profile, manual), snap,
                          priority=trig["severity"])

Every trigger opens a task: these are human reports or hard rules, so the device escalates whatever
the model or NEWS2 says. Manual entries are what a person typed or tapped. Wrist skin temperature is
never used: it is not core temperature and can even fall at fever onset.

All messages are clinical-safety PLACEHOLDERS for a decision-support prototype; the wording must be
confirmed by a clinician before any real use. The hotline number is an Ofcom drama number (fake).
"""
import datetime as dt
import json
import pathlib
import time

PROFILE_TYPES = {
    "general": "General (no specific pathway)",
    "post_surgery": "Recently discharged after surgery",
    "chemo": "Receiving chemotherapy",
    "care_home": "Care home resident",
}
SOFT_SIGNS = {
    "eating_drinking_less": "Eating or drinking less",
    "new_confusion": "New confusion",
    "reduced_mobility": "Reduced mobility",
    "not_passing_urine": "Not passing urine",
    "mottled_skin": "Mottled or discoloured skin",
}
DEMO_HOTLINE = "07700 900000 (DEMO ONLY: Ofcom drama number, not a real service)"
CHEMO_WINDOW_DAYS = 42      # 6 weeks after the last treatment
FEVER_C = 38.0
ORAL_RANGE_C = (30.0, 44.0)  # plausible typed oral temperatures; outside this is a typo
CONFIRM = " Wording to be confirmed by a clinician."
DISCLAIMER = "Draft wording for a decision-support prototype; a clinician should confirm it before real use."
DEFAULT_PROFILE = {"type": "general"}
PROFILE_PATH = pathlib.Path(__file__).parent / "data" / "profile.json"


# ---- profile --------------------------------------------------------------------------------
def validate_profile(body):
    """(profile, errors). Fields: type, plus last_treatment_date + oncology_hotline (chemo),
    surgery_date (post_surgery), care_home_name (care_home). Dates are YYYY-MM-DD."""
    if not isinstance(body, dict):
        return None, ["body is not a JSON object"]
    kind = body.get("type", "general")
    if kind not in PROFILE_TYPES:
        return None, [f"type must be one of {sorted(PROFILE_TYPES)}"]
    out, errs = {"type": kind}, []
    for key in ("last_treatment_date", "surgery_date"):
        if body.get(key):
            try:
                dt.date.fromisoformat(str(body[key]))
                out[key] = str(body[key])
            except ValueError:
                errs.append(f"{key} must be YYYY-MM-DD")
    for key in ("oncology_hotline", "care_home_name"):
        if body.get(key):
            out[key] = str(body[key])[:80]
    if kind == "chemo":
        out.setdefault("oncology_hotline", DEMO_HOTLINE)
    return (None, errs) if errs else (out, [])


def load_profile(path=PROFILE_PATH):
    try:
        prof, errs = validate_profile(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
        return prof if not errs else dict(DEFAULT_PROFILE)
    except (OSError, ValueError):
        return dict(DEFAULT_PROFILE)


def save_profile(profile, path=PROFILE_PATH):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1), encoding="utf-8")


# ---- check-in -------------------------------------------------------------------------------
def validate_checkin(body):
    """(manual, errors) from POST /api/checkin {oral_temp_c, feel_unwell, something_wrong, soft_signs, by}."""
    if not isinstance(body, dict):
        return None, ["body is not a JSON object"]
    errs = []
    temp = body.get("oral_temp_c")
    if temp is not None:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            errs.append("oral_temp_c must be a number or null")
        elif not ORAL_RANGE_C[0] <= temp <= ORAL_RANGE_C[1]:
            errs.append(f"oral_temp_c {temp} is outside {ORAL_RANGE_C[0]}-{ORAL_RANGE_C[1]} °C: check the reading")
    signs = body.get("soft_signs") or []
    if not isinstance(signs, list) or any(not isinstance(s, str) or s not in SOFT_SIGNS for s in signs):
        errs.append(f"soft_signs must be a list drawn from {sorted(SOFT_SIGNS)}")
    by = body.get("by", "wearer")
    if by not in ("wearer", "carer"):
        errs.append('by must be "wearer" or "carer"')
    if errs:
        return None, errs
    return {"oral_temp_c": None if temp is None else round(float(temp), 1),
            "feel_unwell": bool(body.get("feel_unwell")),
            "something_wrong": bool(body.get("something_wrong")),
            "soft_signs": sorted(set(signs)), "by": by}, []


def _days_since(date_str, now):
    if not date_str:
        return None
    today = dt.datetime.fromtimestamp(now).date()
    return (today - dt.date.fromisoformat(date_str)).days


def _trigger(rule, severity, message, guideline, task_source):
    return {"rule": rule, "severity": severity, "message": message + CONFIRM,
            "source_guideline": guideline, "task_source": task_source}


def evaluate(profile, vitals=None, manual=None, now=None):
    """Triggers from the profile and what a person entered. Urgent first.

    `vitals` is accepted for context, but no rule reads it: the chemotherapy rule uses only a typed
    oral temperature, never wrist skin temperature, and the other rules are human reports.
    """
    profile = profile or DEFAULT_PROFILE
    manual = manual or {}
    now = time.time() if now is None else now
    kind = profile.get("type", "general")
    signs = set(manual.get("soft_signs") or [])
    temp = manual.get("oral_temp_c")
    unwell = bool(manual.get("feel_unwell"))
    concern = unwell or bool(manual.get("something_wrong"))
    who = "the wearer" if manual.get("by", "wearer") == "wearer" else "the carer"
    out = []

    if kind == "chemo":
        days = _days_since(profile.get("last_treatment_date"), now)
        # No date on file: apply the rule anyway. Over-escalating is the safer failure here.
        in_window = days is None or 0 <= days <= CHEMO_WINDOW_DAYS
        fever = temp is not None and temp >= FEVER_C
        if in_window and (fever or unwell):
            when = "date of last treatment not recorded" if days is None else f"{days} days after treatment"
            why = f"oral temperature {temp:.1f} °C" if fever else "feels unwell"
            out.append(_trigger(
                "chemo_neutropenic_sepsis", "urgent",
                f"Call your oncology 24 h line now: {profile.get('oncology_hotline', DEMO_HOTLINE)}. "
                f"Possible neutropenic sepsis ({why}, {when}). Do not wait for the device score.",
                "NICE CG151 (neutropenic sepsis)", "rule"))

    if "new_confusion" in signs:
        out.append(_trigger(
            "new_confusion", "urgent",
            f"New confusion reported by {who}. This is a red flag: get a clinical review now, "
            "and call 999 if the person is very drowsy, struggling to breathe or getting worse.",
            "NEWS2 (RCP 2017): new confusion scores 3 on the consciousness (C) parameter", "rule"))

    if concern:
        out.append(_trigger(
            "concern", "review",
            f"{who.capitalize()} said something is wrong. A nurse has been asked to review, "
            "whatever the readings or the model say.",
            "Martha's Rule (NHS England, 2024): patient and family concern triggers a review", "wearer"))

    if kind == "care_home" and len(signs) >= 2:
        names = ", ".join(SOFT_SIGNS[s].lower() for s in sorted(signs))
        out.append(_trigger(
            "soft_signs", "review",
            f"Two or more soft signs of deterioration ({names}). Take a full set of observations "
            "and ask for a clinical review.",
            "RESTORE2 soft signs (care-home deterioration tool)", "rule"))

    out.sort(key=lambda t: t["severity"] != "urgent")
    return out


def sbar(trigger, profile, manual=None, vitals_line=None, now=None):
    """SBAR for a pathway task, in the same shape as main.build_escalation()'s sbar."""
    profile = profile or DEFAULT_PROFILE
    manual = manual or {}
    now = time.time() if now is None else now
    bg = [PROFILE_TYPES.get(profile.get("type"), "General") + "."]
    days = _days_since(profile.get("last_treatment_date"), now) if profile.get("type") == "chemo" else None
    if profile.get("type") == "chemo":
        bg.append(f"Last chemotherapy {profile.get('last_treatment_date') or 'date not recorded'}"
                  + (f" ({days} days ago)." if days is not None else "."))
    if profile.get("surgery_date"):
        bg.append(f"Surgery on {profile['surgery_date']}.")
    bg.append("The device has no record of medicines, other history or infection source.")
    entered = []
    if manual.get("oral_temp_c") is not None:
        entered.append(f"oral temperature {manual['oral_temp_c']:.1f} °C (typed in)")
    if manual.get("feel_unwell"):
        entered.append("'I feel unwell' tapped")
    if manual.get("something_wrong"):
        entered.append("'something is wrong' reported")
    if manual.get("soft_signs"):
        entered.append("soft signs: " + ", ".join(SOFT_SIGNS[s].lower() for s in manual["soft_signs"]))
    assessment = [f"Check-in by the {manual.get('by', 'wearer')}: " + ("; ".join(entered) or "nothing entered") + "."]
    if vitals_line:
        assessment.append(vitals_line)
    return {
        "situation": f"{trigger['severity'].upper()}: pathway rule '{trigger['rule']}' "
                     f"({trigger['source_guideline']}). Raised by a person's report or a hard rule, not by the model.",
        "background": " ".join(bg),
        "assessment": assessment,
        "recommendation": trigger["message"],
        "disclaimer": DISCLAIMER,
    }
