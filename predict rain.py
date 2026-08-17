#!/usr/bin/env python3

import requests
import re
import json
import os
import math
from datetime import datetime, timedelta

APP_NAME = "PREDICT RAIN"

HISTORY_FILE = "predict_rain_history.json"

USER_AGENT = (
    "Mozilla/5.0 "
    "(Linux; Android 10) "
    "AppleWebKit/537.36 "
    "Chrome/120 Safari/537.36"
)


# =========================================================
# BASIC FUNCTIONS
# =========================================================

def clear():
    print("\033c", end="")


def ask(question):
    return input(f"\n{question}: ").strip()


def get_json(url, params=None):
    try:
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=15
        )
        r.raise_for_status()
        return r.json()

    except Exception as e:
        print(f"[!] Request failed: {e}")
        return None


# =========================================================
# HISTORY / PATTERN MEMORY
# =========================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:
        return []


def save_history(history):

    # Keep last 100 observations
    history = history[-100:]

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            history,
            f,
            indent=2,
            ensure_ascii=False
        )


def save_observation(
    school,
    country,
    city,
    forecast
):

    history = load_history()

    observation = {
        "checked_at":
            datetime.now().isoformat(),

        "school": school,

        "country": country,

        "city": city,

        "forecast": forecast
    }

    history.append(observation)

    save_history(history)


# =========================================================
# LOCATION
# =========================================================

def geocode_location(country, city):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": f"{city}, {country}",
        "format": "json",
        "limit": 1
    }

    try:

        r = requests.get(
            url,
            params=params,
            headers={
                "User-Agent":
                    "PREDICT-RAIN-Termux/2.0"
            },
            timeout=15
        )

        r.raise_for_status()

        data = r.json()

        if not data:
            return None

        return {
            "lat": float(data[0]["lat"]),
            "lon": float(data[0]["lon"]),
            "display": data[0]["display_name"]
        }

    except Exception as e:

        print(
            f"[!] Location lookup error: {e}"
        )

        return None


# =========================================================
# WEATHER
# =========================================================

def get_weather(lat, lon):

    url = "https://api.open-meteo.com/v1/forecast"

    params = {

        "latitude": lat,

        "longitude": lon,

        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "rain_sum",
            "precipitation_probability_max"
        ]),

        "timezone": "auto",

        "forecast_days": 8
    }

    return get_json(
        url,
        params
    )


def weather_description(code):

    codes = {

        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",

        45: "Fog",
        48: "Rime fog",

        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",

        61: "Light rain",
        63: "Moderate rain",
        65: "Heavy rain",

        71: "Light snow",
        73: "Moderate snow",
        75: "Heavy snow",

        80: "Light rain showers",
        81: "Moderate rain showers",
        82: "Heavy rain showers",

        85: "Snow showers",
        86: "Heavy snow showers",

        95: "Thunderstorm",
        96: "Thunderstorm",
        99: "Severe thunderstorm"
    }

    return codes.get(
        code,
        "Unknown"
    )


# =========================================================
# WEATHER RISK ENGINE
# =========================================================

def calculate_weather_risk(
    probability,
    rain_mm,
    code
):

    score = 0

    # -----------------------------------------------------
    # Rain probability
    # -----------------------------------------------------

    score += probability * 0.45

    # -----------------------------------------------------
    # Rain quantity
    # -----------------------------------------------------

    if rain_mm >= 50:
        score += 35

    elif rain_mm >= 30:
        score += 28

    elif rain_mm >= 20:
        score += 20

    elif rain_mm >= 10:
        score += 12

    elif rain_mm >= 5:
        score += 7

    elif rain_mm >= 1:
        score += 3

    # -----------------------------------------------------
    # Thunderstorm
    # -----------------------------------------------------

    if code in [95, 96, 99]:
        score += 25

    # Heavy rain
    elif code in [65, 82]:
        score += 15

    elif code in [63, 81]:
        score += 8

    return min(
        100,
        round(score)
    )


# =========================================================
# RAIN CONSISTENCY
# =========================================================

def calculate_consistency(
    probabilities,
    rain_amounts
):

    rainy_days = 0

    for probability, rain in zip(
        probabilities,
        rain_amounts
    ):

        if probability >= 50 or rain >= 2:

            rainy_days += 1

    total = len(probabilities)

    if total == 0:
        return 0

    return round(
        rainy_days / total * 100
    )


def consecutive_rain_days(
    probabilities,
    rain_amounts
):

    longest = 0
    current = 0

    for probability, rain in zip(
        probabilities,
        rain_amounts
    ):

        if probability >= 50 or rain >= 2:

            current += 1

            longest = max(
                longest,
                current
            )

        else:

            current = 0

    return longest


# =========================================================
# SCHOOL WEB SEARCH
# =========================================================

def search_web(query):

    url = "https://html.duckduckgo.com/html/"

    try:

        r = requests.get(
            url,
            params={"q": query},
            headers={
                "User-Agent":
                    USER_AGENT
            },
            timeout=15
        )

        r.raise_for_status()

        html = r.text

        pattern = re.compile(
            r'class="result__a"'
            r'[^>]*href="([^"]+)"'
            r'[^>]*>(.*?)</a>',
            re.I | re.S
        )

        results = []

        for match in pattern.findall(html):

            link = match[0]

            title = re.sub(
                r"<.*?>",
                "",
                match[1]
            )

            title = title.strip()

            results.append({
                "title": title,
                "url": link
            })

        return results[:10]

    except Exception as e:

        print(
            f"[!] Search failed: {e}"
        )

        return []


def search_school(
    school,
    city
):

    queries = [

        f'"{school}" suspension',

        f'"{school}" "no classes"',

        f'"{school}" "class suspension"',

        f'"{school}" "walang pasok"',

        f'"{school}" announcement',

        f'"{school}" weather',

        f'site:facebook.com "{school}"',

        f'site:facebook.com "{school}" suspension',

        f'site:facebook.com "{school}" "no classes"',

        f'"{school}" {city} suspension'
    ]

    results = []

    for query in queries:

        print(
            f"[*] Searching: {query}"
        )

        found = search_web(query)

        for item in found:

            if item["url"] not in [
                x["url"]
                for x in results
            ]:

                results.append(item)

    return results


# =========================================================
# ANNOUNCEMENT ANALYSIS
# =========================================================

SUSPENSION_WORDS = [

    "suspended",
    "suspension",
    "class suspension",
    "classes suspended",
    "no classes",
    "walang pasok",
    "cancelled classes",
    "cancel classes",
    "class cancellation",
    "cancellation"
]


CONTINUE_WORDS = [

    "classes continue",
    "classes will continue",
    "regular classes",
    "classes shall proceed",
    "no suspension"
]


def analyze_result(result):

    text = (
        result["title"]
        + " "
        + result["url"]
    ).lower()

    suspension_hits = 0
    continue_hits = 0

    for word in SUSPENSION_WORDS:

        if word in text:
            suspension_hits += 1

    for word in CONTINUE_WORDS:

        if word in text:
            continue_hits += 1

    is_facebook = (
        "facebook.com"
        in result["url"].lower()
    )

    return {
        "suspension_hits":
            suspension_hits,

        "continue_hits":
            continue_hits,

        "facebook":
            is_facebook
    }


def analyze_school_results(
    results
):

    suspension_score = 0

    continuation_score = 0

    evidence = []

    facebook_evidence = []

    for result in results:

        analysis = analyze_result(
            result
        )

        # -------------------------------------------------
        # Suspension evidence
        # -------------------------------------------------

        if analysis[
            "suspension_hits"
        ]:

            weight = 1

            # Public Facebook result
            if analysis["facebook"]:
                weight = 1.15

            suspension_score += (
                analysis[
                    "suspension_hits"
                ] * weight
            )

            evidence.append(
                result
            )

            if analysis["facebook"]:

                facebook_evidence.append(
                    result
                )

        # -------------------------------------------------
        # Continuation evidence
        # -------------------------------------------------

        continuation_score += (
            analysis[
                "continue_hits"
            ]
        )

    # -----------------------------------------------------
    # Convert search evidence into 0-100
    # -----------------------------------------------------

    raw = (
        suspension_score
        * 8
    )

    raw -= (
        continuation_score
        * 8
    )

    raw = max(
        0,
        min(100, raw)
    )

    return {
        "score": round(raw),

        "evidence":
            evidence,

        "facebook":
            facebook_evidence,

        "suspension_hits":
            suspension_score,

        "continue_hits":
            continuation_score
    }


# =========================================================
# SCHOOL BEHAVIOR PATTERN
# =========================================================

def calculate_school_pattern(
    school
):

    history = load_history()

    school_history = []

    for item in history:

        if item.get(
            "school",
            ""
        ).lower() == school.lower():

            school_history.append(
                item
            )

    if not school_history:

        return {
            "score": 50,
            "samples": 0
        }

    total = 0
    samples = 0

    for item in school_history:

        forecast = item.get(
            "forecast",
            {}
        )

        for day in forecast:

            weather_risk = day.get(
                "weather_risk",
                0
            )

            announcement = day.get(
                "announcement_score",
                0
            )

            if weather_risk >= 60:

                total += announcement
                samples += 1

    if samples == 0:

        return {
            "score": 50,
            "samples": 0
        }

    score = total / samples

    return {
        "score": round(score),
        "samples": samples
    }


# =========================================================
# FINAL PREDICTION ENGINE
# =========================================================

def combine_prediction(
    weather_risk,
    announcement_score,
    school_pattern,
    rain_consistency,
    consecutive_rain
):

    # -----------------------------------------------------
    # Base weather signal
    # -----------------------------------------------------

    score = (
        weather_risk * 0.55
    )

    # -----------------------------------------------------
    # Current school evidence
    # -----------------------------------------------------

    score += (
        announcement_score * 0.25
    )

    # -----------------------------------------------------
    # Historical school behavior
    # -----------------------------------------------------

    score += (
        school_pattern * 0.15
    )

    # -----------------------------------------------------
    # Persistent rain pattern
    # -----------------------------------------------------

    score += (
        rain_consistency * 0.05
    )

    # -----------------------------------------------------
    # Consecutive rain bonus
    # -----------------------------------------------------

    if consecutive_rain >= 4:
        score += 5

    elif consecutive_rain >= 3:
        score += 3

    score = max(
        0,
        min(100, score)
    )

    score = round(score)

    if score >= 80:

        label = (
            "VERY HIGH SUSPENSION RISK"
        )

    elif score >= 65:

        label = (
            "HIGH SUSPENSION RISK"
        )

    elif score >= 50:

        label = (
            "POSSIBLE SUSPENSION"
        )

    elif score >= 30:

        label = (
            "LOW SUSPENSION RISK"
        )

    else:

        label = (
            "LIKELY NO SUSPENSION"
        )

    return score, label


# =========================================================
# DISPLAY 7 DAY FORECAST
# =========================================================

def build_forecast(
    weather,
    announcement_score,
    school_pattern
):

    daily = weather["daily"]

    output = []

    probabilities = (
        daily[
            "precipitation_probability_max"
        ]
    )

    rain_amounts = (
        daily["rain_sum"]
    )

    codes = (
        daily["weather_code"]
    )

    consistency = calculate_consistency(
        probabilities,
        rain_amounts
    )

    consecutive = consecutive_rain_days(
        probabilities,
        rain_amounts
    )

    for i in range(
        len(daily["time"])
    ):

        weather_risk = calculate_weather_risk(
            probabilities[i],
            rain_amounts[i],
            codes[i]
        )

        final_score, label = (
            combine_prediction(
                weather_risk,
                announcement_score,
                school_pattern,
                consistency,
                consecutive
            )
        )

        output.append({

            "date":
                daily["time"][i],

            "weather":
                weather_description(
                    codes[i]
                ),

            "rain_probability":
                probabilities[i],

            "rain_mm":
                rain_amounts[i],

            "weather_risk":
                weather_risk,

            "announcement_score":
                announcement_score,

            "school_pattern":
                school_pattern,

            "prediction":
                final_score,

            "label":
                label
        })

    return output, consistency, consecutive


# =========================================================
# SAVE PATTERN DATA
# =========================================================

def save_run(
    school,
    country,
    city,
    forecast
):

    history = load_history()

    history.append({

        "checked_at":
            datetime.now().isoformat(),

        "school":
            school,

        "country":
            country,

        "city":
            city,

        "forecast":
            forecast
    })

    # Keep last 200 runs
    history = history[-200:]

    save_history(history)


# =========================================================
# DISPLAY
# =========================================================

def display_results(
    forecast,
    consistency,
    consecutive
):

    print("\n")
    print("=" * 75)
    print("                     7-DAY PREDICTION")
    print("=" * 75)

    print(
        f"\nRain consistency: {consistency}%"
    )

    print(
        f"Longest rainy streak: "
        f"{consecutive} day(s)"
    )

    print("\n")

    for item in forecast:

        print(
            f"{item['date']} | "
            f"{item['weather']}"
        )

        print(
            f"  Rain: "
            f"{item['rain_probability']}% | "
            f"{item['rain_mm']} mm"
        )

        print(
            f"  Weather risk: "
            f"{item['weather_risk']}%"
        )

        print(
            f"  Suspension estimate: "
            f"{item['prediction']}%"
        )

        print(
            f"  >>> {item['label']}"
        )

        print("-" * 75)


# =========================================================
# MAIN
# =========================================================

def main():

    clear()

    print("=" * 75)
    print("                         PREDICT RAIN")
    print("=" * 75)

    print(
        "\nWeather + School Announcement + "
        "School Behavior Pattern Engine"
    )

    print(
        "\nNOTE:"
        "\nThis is a prediction system."
        "\nIt does NOT replace an official announcement."
    )

    # =====================================================
    # STEP 1
    # =====================================================

    print("\n\nSTEP 1 - LOCATION")

    country = ask(
        "What is your country?"
    )

    city = ask(
        "What is your specific city?"
    )

    print(
        "\n[*] Locating city..."
    )

    location = geocode_location(
        country,
        city
    )

    if not location:

        print(
            "\n[ERROR] Location not found."
        )

        return

    print(
        "\n[+] Location:"
    )

    print(
        location["display"]
    )

    print(
        "\n[*] Downloading 8-day forecast..."
    )

    weather = get_weather(
        location["lat"],
        location["lon"]
    )

    if not weather:

        print(
            "[ERROR] Weather unavailable."
        )

        return

    # =====================================================
    # STEP 2
    # =====================================================

    print("\n\nSTEP 2 - SCHOOL")

    school = ask(
        "What is your school?"
    )

    # =====================================================
    # SEARCH
    # =====================================================

    print(
        "\n[*] Searching school announcements..."
    )

    results = search_school(
        school,
        city
    )

    print(
        f"\n[+] Search results: "
        f"{len(results)}"
    )

    analysis = analyze_school_results(
        results
    )

    announcement_score = (
        analysis["score"]
    )

    print(
        "[+] Current announcement evidence: "
        f"{announcement_score}%"
    )

    print(
        "[+] Public Facebook results: "
        f"{len(analysis['facebook'])}"
    )

   
