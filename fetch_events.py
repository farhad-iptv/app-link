#!/usr/bin/env python3
"""
Fetch events from ivan-flux API and transform to events.json format.
"""

import requests
import json
import os
import re
from datetime import datetime, timezone


API_URL = "https://events.ivan-flux.online/api/v1/user?username=footfy"
OUTPUT_DIR = "app-files"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "events.json")

# Fallback video URL for non-DRM m3u8/mp4 streams
FALLBACK_VIDEO_URL = "https://github.com/farhad-iptv/app-link/raw/refs/heads/main/FREEFLIX-extended.mp4"

# User agent string for DRM streams
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"


def fetch_api_data():
    """Fetch data from the API."""
    print(f"Fetching data from: {API_URL}")
    try:
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"Successfully fetched data. Found {len(data.get('events', []))} events.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching API: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        raise


def is_drm_stream(link, api_key):
    """Check if a stream is a DRM (clearkey) protected MPD stream."""
    if not api_key or api_key.strip() == "":
        return False
    if ".mpd" in link.lower():
        return True
    return False


def is_fallback_stream(link):
    """
    Check if a stream is a non-DRM simple m3u8/mp4 that should be replaced
    with the fallback video. This targets streams like ivan-flux fallback
    or similar placeholder streams.
    """
    fallback_patterns = [
        "fallback-video",
        "ivan-fluxo.workers.dev",
        "ivan-flux.workers.dev",
    ]
    for pattern in fallback_patterns:
        if pattern in link.lower():
            return True
    return False


def build_stream_url(channel):
    """
    Build the properly formatted stream URL based on channel data.

    Rules:
    1. If the stream has a DRM key (api field) and is MPD -> format with clearkey
    2. If the stream is a fallback/placeholder -> replace with FREEFLIX fallback
    3. Otherwise, keep the original URL as-is (regular m3u8/mp4 streams)
    """
    link = channel.get("link", "").strip()
    api_key = channel.get("api", "").strip()
    title = channel.get("title", "").strip()

    # Rule 1: DRM protected MPD stream with clearkey
    if is_drm_stream(link, api_key):
        # Clean the link - remove any existing query params after .mpd if needed
        # Split the api key into kid:key format
        # The api field is already in "kid:key" format
        # Format: url?|drmScheme=clearkey&drmLicense=kid:key
        # Also remove any existing pipe-separated headers from the link
        base_link = link.split("|")[0].strip()

        # Ensure proper separator
        if "?" in base_link:
            formatted_url = f"{base_link}|drmScheme=clearkey&drmLicense={api_key}"
        else:
            formatted_url = f"{base_link}?|drmScheme=clearkey&drmLicense={api_key}"

        return formatted_url

    # Rule 2: Fallback/placeholder streams -> replace with FREEFLIX
    if is_fallback_stream(link):
        return FALLBACK_VIDEO_URL

    # Rule 3: Regular streams (m3u8, etc.) - keep as-is
    return link


def parse_start_time(start_time_str):
    """
    Parse the API start time format and convert to output format.

    Input format:  "2026/06/17 10:00:00 +0000"
    Output format: "03:30 PM 17/06/2026" (in UTC+5:30 IST, based on examples)

    Looking at the examples more carefully:
    - API: "2026/06/17 08:00:00 +0000" -> Output: "11:00 AM 14/06/2026"
      Wait, that doesn't match date-wise. Let me re-examine.

    Actually the dates in the example output don't correspond 1:1 to the input
    because they're from different fetches. Let me just convert UTC to IST (+5:30).

    API "2026/06/17 08:00:00 +0000" in IST = 01:30 PM 17/06/2026
    But example shows "11:00 AM 14/06/2026" for BAN vs AUS which has different dates.

    Let me just use UTC+5:30 (IST) conversion as that seems to be the pattern.
    """
    try:
        # Parse the input format: "2026/06/17 10:00:00 +0000"
        dt = datetime.strptime(start_time_str.strip(), "%Y/%m/%d %H:%M:%S %z")

        # Convert to IST (UTC+5:30)
        from datetime import timedelta
        ist_offset = timedelta(hours=5, minutes=30)
        dt_ist = dt + ist_offset

        # Format to output: "03:30 PM 17/06/2026"
        formatted = dt_ist.strftime("%I:%M %p %d/%m/%Y")

        # Remove leading zero from hour if present
        if formatted.startswith("0"):
            formatted = formatted[1:]

        return formatted
    except (ValueError, Exception) as e:
        print(f"Warning: Could not parse start time '{start_time_str}': {e}")
        return start_time_str


def determine_sport_type(cat):
    """Determine the sportType based on category."""
    cat_lower = cat.lower() if cat else ""
    if "cricket" in cat_lower:
        return "Cricket"
    elif "football" in cat_lower or "soccer" in cat_lower:
        return "Football"
    elif "f1" in cat_lower or "formula" in cat_lower:
        return "All Sports"
    else:
        return "All Sports"


def determine_league(event):
    """Determine the league from event data."""
    cat = event.get("cat", "")
    title = event.get("title", "")
    event_name = event.get("eventInfo", {}).get("eventName", "")

    cat_lower = cat.lower() if cat else ""

    if "cricket" in cat_lower:
        return "Cricket"
    elif "football" in cat_lower or "soccer" in cat_lower:
        return event_name if event_name else title
    elif "f1" in cat_lower or "formula" in cat_lower:
        return "F1"
    else:
        return event_name if event_name else title


def build_match_name(event_info):
    """Build the match name from event info."""
    team_a = event_info.get("teamA", "")
    team_b = event_info.get("teamB", "")
    event_name = event_info.get("eventName", "")

    if team_a and team_b:
        # If both teams are the same (like F1), use event name
        if team_a.strip() == team_b.strip():
            return event_name if event_name else f"{team_a} vs {team_b}"
        return f"{team_a} vs {team_b}"
    elif event_name:
        return event_name
    else:
        return "Unknown Match"


def determine_is_live(status):
    """Determine if event is live based on status."""
    if not status:
        return False
    status_lower = status.lower().strip()
    return status_lower == "live" or status_lower == "inprogress"


def determine_is_hot(is_hot_str):
    """Determine if event is hot."""
    if not is_hot_str:
        return False
    return str(is_hot_str).strip() == "1"


def transform_event(event, index, timestamp):
    """Transform a single event from API format to output format."""
    event_info = event.get("eventInfo", {})
    channels = event.get("channels_data", [])

    # Build match name
    match_name = build_match_name(event_info)

    # Determine sport type and league
    cat = event.get("cat", "")
    sport_type = determine_sport_type(cat)
    league = determine_league(event)

    # Team info
    home_team = event_info.get("teamA", "")
    away_team = event_info.get("teamB", "")
    home_logo = event_info.get("teamAFlag", "")
    away_logo = event_info.get("teamBFlag", "")

    # Status
    status = event_info.get("Status", "")
    is_live = determine_is_live(status)
    is_hot = determine_is_hot(event_info.get("isHot", "0"))

    # Start time
    start_time_raw = event_info.get("startTime", "")
    start_time = parse_start_time(start_time_raw) if start_time_raw else ""

    # Generate unique ID
    event_id = f"imported-{timestamp}-{index}"

    # Build streams
    streams = []
    for ch_index, channel in enumerate(channels):
        stream_url = build_stream_url(channel)
        stream_name = channel.get("title", f"Stream {ch_index + 1}")

        stream_entry = {
            "name": stream_name,
            "url": stream_url,
            "isPrimary": ch_index == 0  # First stream is primary
        }
        streams.append(stream_entry)

    # If no streams, add a fallback
    if not streams:
        streams.append({
            "name": "FREEFLIX",
            "url": FALLBACK_VIDEO_URL,
            "isPrimary": True
        })

    transformed = {
        "id": event_id,
        "matchName": match_name,
        "sportType": sport_type,
        "league": league,
        "homeTeamName": home_team,
        "homeTeamLogo": home_logo,
        "awayTeamName": away_team,
        "awayTeamLogo": away_logo,
        "isLive": is_live,
        "isHot": is_hot,
        "startTime": start_time,
        "link": "",
        "streams": streams
    }

    return transformed


def transform_all_events(api_data):
    """Transform all events from API data to output format."""
    events = api_data.get("events", [])
    timestamp = int(datetime.now().timestamp() * 1000)

    transformed_events = []
    for index, event in enumerate(events):
        try:
            transformed = transform_event(event, index, timestamp)
            transformed_events.append(transformed)
            print(f"  Transformed event: {transformed['matchName']}")
        except Exception as e:
            print(f"  Warning: Failed to transform event {index}: {e}")
            continue

    return transformed_events


def save_json(data, filepath):
    """Save data to JSON file."""
    # Create directory if it doesn't exist
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(data)} events to {filepath}")


def main():
    """Main function to fetch, transform, and save events."""
    print("=" * 60)
    print("Event Fetcher & Transformer")
    print("=" * 60)

    # Step 1: Fetch API data
    api_data = fetch_api_data()

    # Step 2: Transform events
    print("\nTransforming events...")
    transformed_events = transform_all_events(api_data)

    # Step 3: Save to JSON file
    print(f"\nSaving to {OUTPUT_FILE}...")
    save_json(transformed_events, OUTPUT_FILE)

    print("\n" + "=" * 60)
    print(f"Done! {len(transformed_events)} events saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
