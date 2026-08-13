#!/usr/bin/env python3
"""Renames default-titled Strava rides to 'Morning Commute' / 'Afternoon Commute'
based on start/finish proximity to home and work, and flags them as commutes."""

import json
import math
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
LOG_PATH = ROOT / "titler.log"

DEFAULT_TITLE_RE = re.compile(r"^(morning|afternoon|evening|night|lunch)\s+ride$", re.IGNORECASE)
LOOKBACK_HOURS = 6
EBIKE_MOVING_SECONDS = 45 * 60


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def save_env(env):
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def api_request(url, method="GET", data=None, headers=None, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def refresh_access_token(env):
    resp = api_request(
        "https://www.strava.com/oauth/token",
        method="POST",
        data={
            "client_id": env["STRAVA_CLIENT_ID"],
            "client_secret": env["STRAVA_CLIENT_SECRET"],
            "refresh_token": env["STRAVA_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
    )
    if resp.get("refresh_token") and resp["refresh_token"] != env["STRAVA_REFRESH_TOKEN"]:
        env["STRAVA_REFRESH_TOKEN"] = resp["refresh_token"]
        save_env(env)
    return resp["access_token"]


def haversine_meters(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def within(point, center, radius_m):
    if not point or len(point) != 2:
        return False
    return haversine_meters(point[0], point[1], center[0], center[1]) <= radius_m


def classify(start, end, home, work, radius_m):
    if within(start, home, radius_m) and within(end, work, radius_m):
        return "Morning Commute"
    if within(start, work, radius_m) and within(end, home, radius_m):
        return "Afternoon Commute"
    return None


def main():
    env = load_env()
    access_token = refresh_access_token(env)
    headers = {"Authorization": f"Bearer {access_token}"}

    home = (float(env["HOME_LAT"]), float(env["HOME_LNG"]))
    work = (float(env["WORK_LAT"]), float(env["WORK_LNG"]))
    radius_m = float(env.get("RADIUS_METERS", 500))

    after = int(time.time()) - LOOKBACK_HOURS * 3600
    activities = api_request(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=headers,
        params={"after": after, "per_page": 30},
    )

    for act in activities:
        if act.get("type") not in ("Ride", "EBikeRide"):
            continue
        name = act.get("name", "")
        if not DEFAULT_TITLE_RE.match(name.strip()):
            continue

        start = act.get("start_latlng")
        end = act.get("end_latlng")
        new_title = classify(start, end, home, work, radius_m)
        if not new_title:
            continue

        act_id = act["id"]
        update_data = {"name": new_title, "commute": "true"}

        moving_time = act.get("moving_time")
        if moving_time is not None and moving_time < EBIKE_MOVING_SECONDS and act.get("type") != "EBikeRide":
            update_data["sport_type"] = "EBikeRide"

        updated = api_request(
            f"https://www.strava.com/api/v3/activities/{act_id}",
            method="PUT",
            data=update_data,
            headers=headers,
        )
        log(
            f"Renamed activity {act_id} '{name}' -> '{updated.get('name')}' "
            f"(commute={updated.get('commute')}, sport_type={updated.get('sport_type')})"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        raise
