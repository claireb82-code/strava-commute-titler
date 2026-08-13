# strava-commute-titler

Automatically detects and tags commute rides between home and work on
Strava. This project only ever touches that specific case — it never
modifies any other Strava activity or account setting.

Strava gives new rides generic names like "Morning Ride", "Afternoon Ride",
"Lunch Ride", etc. This script polls your recent activities, and for any
`Ride` or `EBikeRide` that still has one of those generic names, checks
whether it started/finished near your home and work coordinates:

- Start near home, finish near work → renamed to **Morning Commute**
- Start near work, finish near home → renamed to **Afternoon Commute**
- Anything else (already renamed, or doesn't match either pattern) is left untouched

For a ride that matches one of the above, the script also:

- Sets Strava's **commute** flag to `true`
- Sets **sport_type to `EBikeRide`** if moving time is under 45 minutes
  (assumed to be the e-bike), leaving longer rides as-is. Moving time is used
  rather than elapsed time so a commute with a long stop (errand, traffic)
  doesn't get missed just because the clock kept running.

## Setup

1. Create a Strava API application at [strava.com/settings/api](https://www.strava.com/settings/api).
   Use `localhost` as the Authorization Callback Domain.
2. Copy `.env.example` to `.env` and fill in:
   - `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` — from your Strava API app
   - `HOME_LAT` / `HOME_LNG` — decimal coordinates of home
   - `WORK_LAT` / `WORK_LNG` — decimal coordinates of work
   - `RADIUS_METERS` — how close start/finish must be to count as a match (default 500)
3. Do a one-time OAuth authorization to get a refresh token:
   - Visit:
     ```
     https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all,activity:write
     ```
   - Authorize, then copy the `code` parameter from the `localhost` redirect URL (the page will fail to load — that's expected).
   - Exchange it for tokens:
     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -d client_id=YOUR_CLIENT_ID \
       -d client_secret=YOUR_CLIENT_SECRET \
       -d code=CODE_FROM_REDIRECT \
       -d grant_type=authorization_code
     ```
   - Copy the `refresh_token` from the response into `STRAVA_REFRESH_TOKEN` in `.env`.
4. Run it: `python3 titler.py` (stdlib only, no dependencies).

The script automatically saves any refreshed/rotated `refresh_token` back to `.env`.

## Running on a schedule

This script does one poll-and-rename pass and exits — it's meant to be run
periodically rather than as a long-running process. On macOS this can be done
with a `launchd` LaunchAgent using a `StartCalendarInterval` array to control
which days/times it runs (e.g. every 30 minutes, Monday–Friday, 7am–7pm), or
with `cron` on Linux.

## Notes

- Only activities with a still-default Strava title are ever touched — a ride
  you've already renamed yourself is never overwritten.
- Matching is idempotent: re-running against the same activities is always
  safe, since a renamed activity no longer matches the default-title pattern.
- When updating `sport_type`, only that field is sent — not the legacy `type`
  field. Sending both together in one request was found to make the value
  unreliable to change again afterward.
- `.env` is git-ignored and never committed — it contains your API secret,
  refresh token, and home/work coordinates.
