import calendar
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def find_events(args: dict[str, Any]) -> dict[str, Any]:
    """Find events that overlap with a given month in a specified city.

    Args:
        args: Dictionary containing:
            - city: City name to search for events (e.g., 'Melbourne')
            - month: Month name to search (e.g., 'April')

    Returns:
        Dictionary with 'events' list and 'note' with search context.
    """
    search_city = args.get("city", "").lower()
    search_month = args.get("month", "").capitalize()

    file_path = Path(__file__).resolve().parent / "data" / "find_events_data.json"
    if not file_path.exists():
        return {"error": "Data file not found."}

    try:
        month_number = datetime.strptime(search_month, "%B").month
    except ValueError:
        return {"error": "Invalid month provided."}

    # Determine the target year: use next upcoming occurrence of the month
    today = datetime.now()
    if month_number >= today.month:
        target_year = today.year
    else:
        target_year = today.year + 1

    # Build the search month date range
    month_start = datetime(target_year, month_number, 1)
    last_day = calendar.monthrange(target_year, month_number)[1]
    month_end = datetime(target_year, month_number, last_day)

    matching_events = []
    with open(file_path) as f:
        data = json.load(f)

    for city_name, events in data.items():
        if search_city and search_city not in city_name.lower():
            continue

        for event in events:
            event_start = datetime.strptime(event["dateFrom"], "%Y-%m-%d")
            event_end = datetime.strptime(event["dateTo"], "%Y-%m-%d")

            # Check if the event overlaps with the search month
            # Two date ranges overlap if: start1 <= end2 AND start2 <= end1
            if month_start <= event_end and event_start <= month_end:
                matching_events.append(
                    {
                        "city": city_name,
                        "eventName": event["eventName"],
                        "dateFrom": event["dateFrom"],
                        "dateTo": event["dateTo"],
                        "description": event["description"],
                    }
                )

    return {
        "note": f"Returning events that overlap with {search_month} {target_year}.",
        "events": matching_events,
    }
