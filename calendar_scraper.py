import re
import time
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

BASE_URL = "https://www.salesian.com/fs/elements/15028"

# Academic year months: August 2026 through June 2027
MONTHS_TO_FETCH = [
    (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12),
    (2027, 1), (2027, 2), (2027, 3), (2027, 4), (2027, 5), (2027, 6)
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

DATE_REGEX = re.compile(
    r'(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)[,\s]+([A-Za-z]+)\s+(\d{1,2})',
    re.IGNORECASE
)

TIME_RANGE_REGEX = re.compile(
    r'(\d{1,2}\s*:\s*\d{2}\s*(?:AM|PM))\s*-\s*(\d{1,2}\s*:\s*\d{2}\s*(?:AM|PM))',
    re.IGNORECASE
)

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}

def parse_time_str(time_str):
    cleaned = re.sub(r'\s+', '', time_str).upper()
    try:
        dt = datetime.strptime(cleaned, "%I:%M%p")
        return dt.hour, dt.minute
    except ValueError:
        return None, None

def fetch_and_parse_month(year, month):
    cal_date_str = f"{year}-{month:02d}-01"
    params = {
        "cal_date": cal_date_str,
        "is_draft": "false",
        "is_load_more": "true",
        "page_id": "1415",
        "parent_id": "15028",
        "_": int(time.time() * 1000)
    }

    resp = requests.get(BASE_URL, params=params, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  [Error] HTTP {resp.status_code} fetching {cal_date_str}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    events = []

    # Find only the bottom-level day containers (cells that do not contain other day cells)
    # Using 'td' or containers with class 'fsCalendarDaybox' / 'fsCalendarDate'
    day_cells = soup.find_all("td")
    if not day_cells:
        # Fallback to leaf divs if not table-based
        day_cells = soup.find_all(class_=re.compile(r'day|cell', re.I))

    for cell in day_cells:
        anchors = cell.find_all("a", href=True)
        if not anchors:
            continue

        # Check the date header inside this specific cell
        cell_text = cell.get_text(" ", strip=True)
        date_match = DATE_REGEX.search(cell_text)
        if not date_match:
            continue

        mo_name = date_match.group(1).lower()
        day_num = int(date_match.group(2))
        mo_num = MONTH_MAP.get(mo_name)
        if not mo_num:
            continue

        ev_year = year if mo_num >= 8 else (year + 1 if year == 2026 else year)
        try:
            ev_date = date(ev_year, mo_num, day_num)
        except ValueError:
            continue

        # Extract only real event links
        for a in anchors:
            title = a.get_text(strip=True)
            # Skip UI buttons and weekday names
            if not title or title in ["<", ">", "Load More", "Back up to Calendar", "All Day"]:
                continue
            if title.lower() in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
                continue
            if DATE_REGEX.search(title):
                continue

            # Extract time string
            parent_text = a.parent.get_text(" ", strip=True) if a.parent else cell_text

            if not any(e["summary"] == title and e["date"] == ev_date for e in events):
                events.append({
                    "date": ev_date,
                    "summary": title,
                    "time_str": parent_text
                })

    return events

def build_ical(events, output_filename="salesian_school_year.ics"):
    cal = Calendar()
    cal.add("prodid", "-//Salesian Calendar Scraper//EN")
    cal.add("version", "2.0")

    seen = set()
    count = 0

    for ev in events:
        key = (ev["summary"], ev["date"])
        if key in seen:
            continue
        seen.add(key)

        event = Event()
        event.add("summary", ev["summary"])
        event.add("description", "Synced from Salesian College Preparatory calendar")

        time_match = TIME_RANGE_REGEX.search(ev["time_str"])
        if time_match:
            sh, sm = parse_time_str(time_match.group(1))
            eh, em = parse_time_str(time_match.group(2))
            if sh is not None and eh is not None:
                start_dt = datetime(ev["date"].year, ev["date"].month, ev["date"].day, sh, sm)
                end_dt = datetime(ev["date"].year, ev["date"].month, ev["date"].day, eh, em)
                event.add("dtstart", start_dt)
                event.add("dtend", end_dt)
            else:
                event.add("dtstart", ev["date"])
                event.add("dtend", ev["date"])
        else:
            # All-day event
            event.add("dtstart", ev["date"])
            event.add("dtend", ev["date"])

        cal.add_component(event)
        count += 1

    with open(output_filename, "wb") as f:
        f.write(cal.to_ical())

    print(f"\nSuccessfully wrote {count} events to {output_filename}")

def main():
    all_events = []
    for yr, mo in MONTHS_TO_FETCH:
        print(f"Fetching {yr}-{mo:02d}...")
        events = fetch_and_parse_month(yr, mo)
        print(f"  Found {len(events)} events.")
        all_events.extend(events)
        time.sleep(0.3)

    build_ical(all_events)

if __name__ == "__main__":
    main()
