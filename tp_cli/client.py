"""TrainingPeaks HTTP client wrapping all tpapi.trainingpeaks.com endpoints."""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any, Optional

import httpx

from .auth import AuthError, _load_tokens, _save_tokens, get_bearer_token

TP_BASE = "https://tpapi.trainingpeaks.com"
PEAKSWARE_BASE = "https://api.peakswaresb.com"
MIN_REQUEST_INTERVAL = 0.15  # 150ms between requests

# Sport name → workoutTypeValueId mapping (confirmed for this TP account)
SPORT_IDS = {
    "swim": 1, "swimming": 1,
    "bike": 2, "cycling": 2, "ride": 2,
    "run": 3, "running": 3,
    "mtb": 4,
    "xcski": 5, "ski": 5,
    "walk": 6, "walking": 6,
    "strength": 7,
    "other": 9,
}


class TPClient:
    def __init__(self):
        self._last_request_at: float = 0.0
        self._athlete_id: Optional[int] = None

    # -----------------------------------------------------------------------
    # Core HTTP
    # -----------------------------------------------------------------------

    def _headers(self) -> dict:
        token = get_bearer_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "trainingpeaks-cli/0.1",
        }

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.time()

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        self._throttle()
        resp = httpx.request(
            method,
            f"{TP_BASE}{path}",
            headers=self._headers(),
            json=body,
            params=params,
            timeout=20,
        )
        if resp.status_code == 401 and retry_on_401:
            # Force-refresh token and retry once
            from .auth import invalidate_cache
            invalidate_cache()
            return self._request(method, path, body, params, retry_on_401=False)
        if resp.status_code == 401:
            raise AuthError("Session expired. Run `tp auth setup` to re-authenticate.")
        if resp.status_code == 403:
            raise PermissionError(f"Access denied (403): {path}")
        if resp.status_code == 404:
            raise ValueError(f"Not found (404): {path}")
        if resp.status_code == 429:
            raise RuntimeError("Rate limited (429). Wait a moment and retry.")
        resp.raise_for_status()
        raw = resp.text
        return json.loads(raw) if raw.strip() else {}

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict) -> Any:
        return self._request("POST", path, body=body)

    def put(self, path: str, body: dict) -> Any:
        return self._request("PUT", path, body=body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # -----------------------------------------------------------------------
    # Athlete ID (cached)
    # -----------------------------------------------------------------------

    def get_athlete_id(self) -> int:
        if self._athlete_id:
            return self._athlete_id

        # Check tokens file first (avoids extra API call)
        tokens = _load_tokens()
        if tokens.get("athlete_id"):
            self._athlete_id = int(tokens["athlete_id"])
            return self._athlete_id

        user_data = self.get_user()
        user = user_data.get("user", user_data) if isinstance(user_data, dict) else {}
        athletes = user.get("athletes", [])
        athlete = athletes[0] if athletes else user
        aid = (
            athlete.get("athleteId")
            or user.get("personId")
            or user.get("userId")
        )
        if not aid:
            raise RuntimeError("Could not determine athlete ID from profile.")

        self._athlete_id = int(aid)
        tokens["athlete_id"] = self._athlete_id
        _save_tokens(tokens)
        return self._athlete_id

    # -----------------------------------------------------------------------
    # User / profile
    # -----------------------------------------------------------------------

    def get_user(self) -> dict:
        return self.get("/users/v3/user")

    # -----------------------------------------------------------------------
    # Workouts
    # -----------------------------------------------------------------------

    def list_workouts(self, start: date, end: date) -> list[dict]:
        aid = self.get_athlete_id()
        path = f"/fitness/v6/athletes/{aid}/workouts/{start.isoformat()}/{end.isoformat()}"
        result = self.get(path)
        return result if isinstance(result, list) else result.get("workouts", [])

    def get_workout(self, workout_id: str) -> dict:
        aid = self.get_athlete_id()
        result = self.get(f"/fitness/v6/athletes/{aid}/workouts/{workout_id}")
        return result if isinstance(result, dict) else (result[0] if result else {})

    def get_workout_details(self, workout_id: str) -> dict:
        aid = self.get_athlete_id()
        result = self.get(f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/details")
        return result if isinstance(result, dict) else {}

    def sniff_workout_endpoints(self, workout_id: str) -> list[dict]:
        """Probe likely workout-detail endpoints and report which ones return data."""
        aid = self.get_athlete_id()
        paths = [
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}",
            f"/fitness/v7/athletes/{aid}/workouts/{workout_id}",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/details",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/metrics",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/laps",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/samples",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/files",
            f"/fitness/v6/athletes/{aid}/workouts/{workout_id}/devicefiles",
            f"/fitnessfile/v1/athletes/{aid}/workouts/{workout_id}",
            f"/fitnessfile/v2/athletes/{aid}/workouts/{workout_id}",
            f"/personalrecord/v2/athletes/{aid}/workouts/{workout_id}",
        ]
        findings = []
        for path in paths:
            try:
                data = self.get(path)
                keys = list(data.keys()) if isinstance(data, dict) else []
                findings.append(
                    {"path": path, "status": 200, "keys": keys[:20], "shape": type(data).__name__}
                )
            except Exception as e:
                findings.append({"path": path, "status": "error", "error": str(e)})
        return findings

    def create_workout(
        self,
        sport: str,
        workout_date: str,
        title: str,
        duration_s: Optional[int] = None,
        tss: Optional[float] = None,
        distance_km: Optional[float] = None,
        description: str = "",
        structure: Optional[dict] = None,
    ) -> dict:
        aid = self.get_athlete_id()
        sport_id = SPORT_IDS.get(sport.lower())
        if not sport_id:
            raise ValueError(f"Unknown sport '{sport}'. Valid: {', '.join(SPORT_IDS)}")

        body: dict = {
            "athleteId": aid,
            "workoutTypeValueId": sport_id,
            "title": title,
            "workoutDay": f"{workout_date}T00:00:00",
            "description": description or "",
            "coachComments": "",
        }
        if duration_s is not None:
            body["totalTimePlanned"] = duration_s / 3600  # TP stores in hours
        if tss is not None:
            body["tssPlanned"] = tss
        if distance_km is not None:
            body["totalDistancePlanned"] = distance_km * 1000  # km → meters
        if structure is not None:
            body["structure"] = structure

        result = self.post(f"/fitness/v6/athletes/{aid}/workouts", body)
        return result if isinstance(result, dict) else {}

    def update_workout(
        self,
        workout_id: str,
        title: Optional[str] = None,
        duration_s: Optional[int] = None,
        tss: Optional[float] = None,
        description: Optional[str] = None,
    ) -> dict:
        aid = self.get_athlete_id()
        # Fetch current state — PUT requires the complete object
        current = self.get_workout(workout_id)
        body = dict(current)

        if title is not None:
            body["title"] = title
        if duration_s is not None:
            body["totalTimePlanned"] = duration_s / 3600
        if tss is not None:
            body["tssPlanned"] = tss
        if description is not None:
            body["description"] = description

        self.put(f"/fitness/v6/athletes/{aid}/workouts/{workout_id}", body)
        return {"updated": True, "workout_id": workout_id}

    def delete_workout(self, workout_id: str) -> dict:
        aid = self.get_athlete_id()
        self.delete(f"/fitness/v6/athletes/{aid}/workouts/{workout_id}")
        return {"deleted": True, "workout_id": workout_id}

    # -----------------------------------------------------------------------
    # Fitness metrics (CTL / ATL / TSB)
    # -----------------------------------------------------------------------

    def get_fitness(
        self,
        start: date,
        end: date,
        ctl_constant: int = 42,
        atl_constant: int = 7,
    ) -> list[dict]:
        aid = self.get_athlete_id()
        path = (
            f"/fitness/v1/athletes/{aid}/reporting/performancedata"
            f"/{start.isoformat()}/{end.isoformat()}"
        )
        body = {
            "atlConstant": atl_constant,
            "atlStart": 0,
            "ctlConstant": ctl_constant,
            "ctlStart": 0,
            "workoutTypes": [],
        }
        result = self.post(path, body)
        return result if isinstance(result, list) else result.get("data", [])

    # -----------------------------------------------------------------------
    # Personal records / peaks
    # -----------------------------------------------------------------------

    def get_prs(
        self,
        sport: str,
        pr_type: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> list[dict]:
        aid = self.get_athlete_id()
        path = f"/personalrecord/v2/athletes/{aid}/{sport}"
        params: dict = {"prType": pr_type}
        if start:
            params["startDate"] = f"{start.isoformat()}T00:00:00"
        if end:
            params["endDate"] = f"{end.isoformat()}T00:00:00"
        result = self.get(path, params=params)
        return result if isinstance(result, list) else result.get("personalRecords", [])

    def get_workout_prs(self, workout_id: str) -> list[dict]:
        aid = self.get_athlete_id()
        path = f"/personalrecord/v2/athletes/{aid}/workouts/{workout_id}"
        result = self.get(path, params={"displayPeaksForBasic": "true"})
        if isinstance(result, dict):
            return result.get("personalRecords", [])
        return result if isinstance(result, list) else []

    # -----------------------------------------------------------------------
    # Strength workouts (Peaksware Rx API)
    # -----------------------------------------------------------------------

    def _pw_request(self, method, path, body=None, params=None, retry_on_401=True):
        """Request against the Peaksware Rx API (strength workouts)."""
        self._throttle()
        resp = httpx.request(
            method,
            f"{PEAKSWARE_BASE}{path}",
            headers=self._headers(),
            json=body,
            params=params,
            timeout=20,
        )
        if resp.status_code == 401 and retry_on_401:
            from .auth import invalidate_cache
            invalidate_cache()
            return self._pw_request(method, path, body, params, retry_on_401=False)
        if resp.status_code == 401:
            raise AuthError("Session expired. Run `tp auth setup` to re-authenticate.")
        if resp.status_code == 403:
            raise PermissionError(f"Access denied (403): {path}")
        if resp.status_code == 404:
            raise ValueError(f"Not found (404): {path}")
        resp.raise_for_status()
        raw = resp.text
        return json.loads(raw) if raw.strip() else {}

    def get_exercise(self, exercise_id: str) -> dict:
        """Fetch a single exercise definition by ID."""
        result = self._pw_request("GET", f"/rx/activity/v1/exercises/{exercise_id}")
        return result.get("data", result)

    def create_exercise(self, title: str, instructions: str = "", video_url: str = "", parameters: list[dict] | None = None) -> dict:
        """Create a custom exercise definition. Returns the created exercise."""
        aid = self.get_athlete_id()
        # POST creates a blank shell
        result = self._pw_request("POST", "/rx/activity/v1/exercises", body={})
        guid = result.get("data", {}).get("id")
        if not guid:
            raise RuntimeError("Failed to create exercise shell")
        # PUT sets the actual content
        body = {
            "id": guid,
            "ownerId": aid,
            "title": title,
            "instructions": instructions,
            "videoUrl": video_url,
            "parameters": parameters or [{"parameter": "Reps"}],
        }
        result = self._pw_request("PUT", "/rx/activity/v1/exercises", body=body)
        return result.get("data", result)

    def create_strength_workout(
        self,
        workout_date: str,
        title: str,
        blocks: list[dict],
        instructions: str = "",
        duration_s: Optional[int] = None,
    ) -> dict:
        """Create a structured strength workout via the Peaksware Rx API.

        blocks: list of dicts, each with:
            - title: str (block/exercise name)
            - blockType: "SingleExercise" or "Circuit"
            - prescriptions: list of dicts with:
                - exercise: full exercise object (from get_exercise or create_exercise)
                - parameters: list of {"parameter": "Reps"} or {"parameter": "Duration"} etc
                - sets: list of {"parameterValues": [{"parameter": "Reps", "prescribedValue": "10"}]}
                - coachNotes: optional str
        """
        aid = self.get_athlete_id()
        # Step 1: Create workout shell
        result = self._pw_request("POST", "/rx/activity/v1/workouts", body={
            "calendarId": aid,
            "workoutType": "Strength",
            "prescribedDate": workout_date,
        })
        wid = result.get("data", {}).get("id")
        if not wid:
            raise RuntimeError("Failed to create strength workout shell")

        # Step 2: Save with full structure
        body = {
            "id": wid,
            "calendarId": aid,
            "workoutType": "StructuredStrength",
            "prescribedDate": workout_date,
            "title": title,
            "instructions": instructions or None,
            "prescribedDurationInSeconds": duration_s,
            "blocks": blocks,
        }
        result = self._pw_request("POST", "/rx/activity/v1/workouts/save", body=body)
        data = result.get("data", {})
        errors = result.get("errors", {})
        if errors:
            raise RuntimeError(f"Strength workout save errors: {json.dumps(errors)}")
        return data

    def delete_strength_workout(self, workout_id: str) -> dict:
        """Delete a strength workout by its numeric Peaksware ID."""
        result = self._pw_request("DELETE", f"/rx/activity/v1/workouts/{workout_id}")
        return result.get("data", result)

    def get_strength_workout(self, workout_id: str) -> dict:
        """Fetch a strength workout by its numeric Peaksware ID."""
        result = self._pw_request("GET", f"/rx/activity/v1/workouts/{workout_id}")
        return result.get("data", result)

    # -----------------------------------------------------------------------
    # .zwo import
    # -----------------------------------------------------------------------

    def import_zwo(
        self,
        zwo_path: str,
        sport: str,
        workout_date: str,
        title: Optional[str] = None,
        tss: Optional[float] = None,
        description: Optional[str] = None,
    ) -> dict:
        import pathlib
        import xml.etree.ElementTree as ET

        path = pathlib.Path(zwo_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {zwo_path}")

        zwo_xml = path.read_text(encoding="utf-8", errors="replace")

        if not title:
            try:
                root = ET.fromstring(zwo_xml)
                title = root.findtext("name") or path.stem
            except Exception:
                title = path.stem

        if not description:
            try:
                root = ET.fromstring(zwo_xml)
                description = root.findtext("description") or ""
            except Exception:
                description = ""

        structure = _zwo_to_tp_structure(zwo_xml, sport=sport)
        duration_s = _total_duration_from_structure(structure)

        result = self.create_workout(
            sport=sport,
            workout_date=workout_date,
            title=title,
            duration_s=int(duration_s),
            tss=tss,
            description=description,
            structure=structure,
        )
        return {
            "created": True,
            "workout_id": result.get("workoutId"),
            "date": workout_date,
            "title": title,
            "sport": sport,
            "duration_min": round(duration_s / 60),
            "steps": len(structure.get("structure", [])),
        }


# ---------------------------------------------------------------------------
# Simple step list → TrainingPeaks structure builder
# ---------------------------------------------------------------------------

def build_structure(steps_def: list[dict], sport: str = "bike") -> dict:
    """
    Convert a simplified step list into a full TP workout structure.

    Each step dict supports:
      type:        warmup | cooldown | steady | rest | ramp | intervals
      duration:    seconds (for single steps)
      target:      % of FTP (bike) or % of LTHR (run/swim) — single value
      start / end: for ramp types (warmup/cooldown/ramp) — from start% to end%
      name:        optional label for this step
      repeat:      for intervals — number of repetitions
      on_duration / off_duration:  for intervals
      on_target / off_target:      for intervals

    Example:
      [
        {"type": "warmup",    "duration": 600, "start": 50, "end": 75},
        {"type": "steady",    "duration": 900, "target": 88, "name": "Sweet Spot"},
        {"type": "rest",      "duration": 300, "target": 50},
        {"type": "intervals", "repeat": 4, "on_duration": 300, "off_duration": 180,
                              "on_target": 105, "off_target": 55, "name": "VO2max"},
        {"type": "cooldown",  "duration": 300, "start": 60, "end": 40}
      ]
    """
    blocks = []
    cursor = 0

    for step in steps_def:
        stype = step.get("type", "steady")
        name = step.get("name", "")
        dur = int(step.get("duration", 300))

        if stype == "warmup":
            lo = int(step.get("start", 50))
            hi = int(step.get("end", 75))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": name or "Warm Up",
                    "intensityClass": "warmUp",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": min(lo, hi), "maxValue": max(lo, hi)}],
                }],
                "begin": cursor, "end": cursor + dur,
            }
            blocks.append(block)
            cursor += dur

        elif stype == "cooldown":
            lo = int(step.get("start", 60))
            hi = int(step.get("end", 40))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": name or "Cool Down",
                    "intensityClass": "coolDown",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": min(lo, hi), "maxValue": max(lo, hi)}],
                }],
                "begin": cursor, "end": cursor + dur,
            }
            blocks.append(block)
            cursor += dur

        elif stype in ("steady", "active"):
            target = int(step.get("target", 70))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": name or "Steady",
                    "intensityClass": "active",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": target}],
                }],
                "begin": cursor, "end": cursor + dur,
            }
            blocks.append(block)
            cursor += dur

        elif stype == "rest":
            target = int(step.get("target", 40))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": name or "Recovery",
                    "intensityClass": "rest",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": target}],
                }],
                "begin": cursor, "end": cursor + dur,
            }
            blocks.append(block)
            cursor += dur

        elif stype == "ramp":
            lo = int(step.get("start", 60))
            hi = int(step.get("end", 90))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": name or "Ramp",
                    "intensityClass": "active",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": min(lo, hi), "maxValue": max(lo, hi)}],
                }],
                "begin": cursor, "end": cursor + dur,
            }
            blocks.append(block)
            cursor += dur

        elif stype == "intervals":
            repeat = int(step.get("repeat", 1))
            on_dur = int(step.get("on_duration", 300))
            off_dur = int(step.get("off_duration", 120))
            on_target = int(step.get("on_target", 100))
            off_target = int(step.get("off_target", 50))
            total_dur = repeat * (on_dur + off_dur)
            block = {
                "type": "repetition",
                "length": {"unit": "repetition", "value": repeat},
                "steps": [
                    {
                        "type": "step",
                        "name": name or "On",
                        "intensityClass": "active",
                        "length": {"value": on_dur, "unit": "second"},
                        "targets": [{"minValue": on_target}],
                    },
                    {
                        "type": "step",
                        "name": "Recovery",
                        "intensityClass": "rest",
                        "length": {"value": off_dur, "unit": "second"},
                        "targets": [{"minValue": off_target}],
                    },
                ],
                "begin": cursor, "end": cursor + total_dur,
            }
            blocks.append(block)
            cursor += total_dur

    primary_metric = (
        "percentOfThresholdHr"
        if sport.lower() in ("run", "running", "swim", "swimming")
        else "percentOfFtp"
    )
    return {
        "primaryIntensityMetric": primary_metric,
        "primaryLengthMetric": "duration",
        "structure": blocks,
    }


# ---------------------------------------------------------------------------
# .zwo → TrainingPeaks structure converter
# ---------------------------------------------------------------------------

def _zwo_to_tp_structure(zwo_xml: str, sport: str = "bike") -> dict:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(zwo_xml)
    workout_el = root.find("workout")
    if workout_el is None:
        raise ValueError("No <workout> element found in .zwo file")

    def pct(val, default=50):
        if val is None:
            return default
        return round(float(val) * 100)

    def text_notes(el) -> str:
        events = el.findall("textevent")
        if not events:
            return ""
        parts = [
            f"{ev.get('timeoffset', '0')}:{(ev.get('message') or '').replace(';', ',')}"
            for ev in events
        ]
        return "!TextEvents:{{\r\n{}\r\n}}".format(";\r\n".join(parts))

    steps = []
    cursor_s = 0

    for el in workout_el:
        tag = el.tag
        notes = text_notes(el)

        if tag == "Warmup":
            lo, hi = pct(el.get("PowerLow")), pct(el.get("PowerHigh"))
            dur = int(el.get("Duration", 600))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": "Warm Up", "intensityClass": "warmUp",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": min(lo, hi), "maxValue": max(lo, hi)}],
                    "notes": notes,
                }],
                "begin": cursor_s, "end": cursor_s + dur,
            }
            steps.append(block)
            cursor_s += dur

        elif tag == "Cooldown":
            lo, hi = pct(el.get("PowerLow")), pct(el.get("PowerHigh"))
            dur = int(el.get("Duration", 600))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": "Cool Down", "intensityClass": "coolDown",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": min(lo, hi), "maxValue": max(lo, hi)}],
                    "notes": notes,
                }],
                "begin": cursor_s, "end": cursor_s + dur,
            }
            steps.append(block)
            cursor_s += dur

        elif tag == "SteadyState":
            power = pct(el.get("Power"))
            dur = int(el.get("Duration", 300))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": "Steady State", "intensityClass": "active",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": power}],
                    "notes": notes,
                }],
                "begin": cursor_s, "end": cursor_s + dur,
            }
            steps.append(block)
            cursor_s += dur

        elif tag in ("Ramp", "FreeRide"):
            lo_raw = pct(el.get("PowerLow", el.get("Power", "0.5")))
            hi_raw = pct(el.get("PowerHigh", el.get("Power", "0.75")))
            lo, hi = min(lo_raw, hi_raw), max(lo_raw, hi_raw)
            dur = int(el.get("Duration", 300))
            block = {
                "type": "step",
                "length": {"unit": "repetition", "value": 1},
                "steps": [{
                    "name": tag, "intensityClass": "active",
                    "length": {"value": dur, "unit": "second"},
                    "targets": [{"minValue": lo, "maxValue": hi}],
                    "notes": notes,
                }],
                "begin": cursor_s, "end": cursor_s + dur,
            }
            steps.append(block)
            cursor_s += dur

        elif tag == "IntervalsT":
            repeat = int(el.get("Repeat", 1))
            on_dur = int(el.get("OnDuration", 300))
            off_dur = int(el.get("OffDuration", 120))
            on_pwr = pct(el.get("OnPower"))
            off_pwr = pct(el.get("OffPower", "0.5"))
            dur = repeat * (on_dur + off_dur)
            block = {
                "type": "repetition",
                "length": {"unit": "repetition", "value": repeat},
                "steps": [
                    {
                        "type": "step", "name": "On", "intensityClass": "active",
                        "length": {"value": on_dur, "unit": "second"},
                        "targets": [{"minValue": on_pwr}],
                        "notes": "",
                    },
                    {
                        "type": "step", "name": "Off", "intensityClass": "rest",
                        "length": {"value": off_dur, "unit": "second"},
                        "targets": [{"minValue": off_pwr}],
                        "notes": "",
                    },
                ],
                "begin": cursor_s, "end": cursor_s + dur,
            }
            steps.append(block)
            cursor_s += dur

    primary_metric = (
        "percentOfThresholdHr"
        if sport.lower() in ("run", "running", "swim", "swimming")
        else "percentOfFtp"
    )
    return {
        "primaryIntensityMetric": primary_metric,
        "primaryLengthMetric": "duration",
        "structure": steps,
    }


def _total_duration_from_structure(structure: dict) -> float:
    """Return total workout duration in seconds from a TP structure dict."""
    total_s = 0
    for block in structure.get("structure", []):
        reps = block.get("length", {}).get("value", 1)
        block_s = sum(
            s.get("length", {}).get("value", 0)
            for s in block.get("steps", [])
        )
        total_s += block_s * reps
    return total_s


# ---------------------------------------------------------------------------
# Exercise catalog search
# ---------------------------------------------------------------------------

def search_exercises(query: str, limit: int = 20) -> list[dict]:
    """Search the local exercise catalog by title (fuzzy substring match)."""
    import pathlib
    catalog_path = pathlib.Path(__file__).parent / "exercise_catalog.json"
    if not catalog_path.exists():
        return []
    catalog = json.loads(catalog_path.read_text())
    query_lower = query.lower()
    # Exact prefix match first, then substring
    prefix = [e for e in catalog if e["title"].lower().startswith(query_lower)]
    substring = [e for e in catalog if query_lower in e["title"].lower() and e not in prefix]
    return (prefix + substring)[:limit]


def build_strength_blocks(exercises_def: list[dict], client: "TPClient") -> list[dict]:
    """Convert a simplified exercise list into Peaksware Rx API blocks.

    Each exercise_def dict:
        exercise_id: str (ID from catalog or custom) OR title: str (for custom)
        sets: int (number of sets, default 1)
        parameter: str ("Reps", "Duration", etc)
        value: str (prescribed value per set, e.g. "10" or "30")
        values: list[str] (if different per set, overrides value)
        coach_notes: optional str
        block_type: optional, default "SingleExercise"
    """
    blocks = []
    for edef in exercises_def:
        # Get or create exercise
        if "exercise_id" in edef:
            exercise = client.get_exercise(edef["exercise_id"])
        elif "exercise" in edef:
            exercise = edef["exercise"]  # Already a full exercise object
        else:
            raise ValueError(f"Exercise definition must have 'exercise_id' or 'exercise': {edef}")

        param_name = edef.get("parameter", "Reps")
        num_sets = edef.get("sets", 1)
        default_value = str(edef.get("value", "10"))
        values = edef.get("values", [default_value] * num_sets)

        sets = [
            {"parameterValues": [{"parameter": param_name, "prescribedValue": str(v)}]}
            for v in values
        ]

        block = {
            "title": exercise.get("title", "Exercise"),
            "blockType": edef.get("block_type", "SingleExercise"),
            "prescriptions": [{
                "exercise": exercise,
                "parameters": [{"parameter": param_name}],
                "sets": sets,
                "coachNotes": edef.get("coach_notes"),
            }],
        }
        blocks.append(block)

    return blocks
