#!/usr/bin/env python3

import requests
import urllib.parse
import re
from datetime import datetime, timedelta

APP_NAME = "PREDICT RAIN"

# ---------------------------------------------------------
# GENERAL FUNCTIONS
# ---------------------------------------------------------

def clear():
    print("\033c", end="")


def ask(question):
    return input(f"\n{question}: ").strip()


def get_json(url, params=None, headers=None):
    try:
        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[!] Connection error: {e}")
        return None


# ---------------------------------------------------------
# LOCATION
# ---------------------------------------------------------

def geocode_location(country, city):
    """
    Uses OpenStreetMap Nominatim to turn
    Country + City into latitude/longitude.
    """

    query = f"{city}, {country}"

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": query,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "PREDICT-RAIN-Termux/1.0"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        if not data:
            return None

        return {
            "lat": float(data[0]["lat"]),
            "lon": float(data[0]["lon"]),
            "display": data[0]["display_name"]
        }

    except Exception as e:
        print(f"[!] Location lookup failed: {e}")
        return None


# ---------------------------------------------------------
# WEATHER
# ---------------------------------------------------------

def get_weather(lat, lon):
    """
    Open-Meteo weather forecast.
    No API key required.
    """

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
        "forecast_days": 4
    }

    return get_json(url, params)


def weather_description(code):
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",

        45: "Fog",
        48: "Depositing rime fog",

        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",

        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",

        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",

        66: "Light freezing rain",
        67: "Heavy freezing rain",

        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",

        77: "Snow grains",

        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",

        85: "Slight snow showers",
        86: "Heavy snow showers",

        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Thunderstorm with heavy hail"
    }

    return codes.get(code, "Unknown")


# ---------------------------------------------------------
# WEATHER RISK
# ---------------------------------------------------------

def calculate_weather_risk(weather):
    """
    Produces a rough weather-related suspension risk.

    This is NOT an official government calculation.
    """

    daily = weather["daily"]

    # Tomorrow is index 1.
    tomorrow_probability = daily[
        "precipitation_probability_max"
    ][1]

    tomorrow_rain = daily[
        "rain_sum"
    ][1]

    tomorrow_precip = daily[
        "precipitation_sum"
    ][1]

    tomorrow_code = daily[
        "weather_code"
    ][1]

    score = 0

    # Rain probability
    score += tomorrow_probability * 0.45

    # Rain amount
    if tomorrow_rain >= 20:
        score += 25
    elif tomorrow_rain >= 10:
        score += 18
    elif tomorrow_rain >= 5:
        score += 10
    elif tomorrow_rain >= 1:
        score += 5

    # Total precipitation
    if tomorrow_precip >= 30:
        score += 15
    elif tomorrow_precip >= 15:
        score += 10
    elif tomorrow_precip >= 5:
        score += 5

    # Thunderstorm
    if tomorrow_code in [95, 96, 99]:
        score += 20

    # Rain-heavy weather codes
    if tomorrow_code in [
        63, 65,
        80, 81, 82
    ]:
        score += 10

    score = min(100, round(score))

    return {
        "score": score,
        "probability": tomorrow_probability,
        "rain": tomorrow_rain,
        "precip": tomorrow_precip,
        "code": tomorrow_code
    }


# ---------------------------------------------------------
# RAIN CONSISTENCY
# ---------------------------------------------------------

def check_rain_consistency(weather):
    """
    Checks whether rain is expected for multiple days.
    """

    daily = weather["daily"]

    rain_days = 0
    total_days = len(daily["time"])

    for i in range(total_days):
        rain_probability = daily[
            "precipitation_probability_max"
        ][i]

        rain_amount = daily[
            "rain_sum"
        ][i]

        if rain_probability >= 50 or rain_amount >= 2:
            rain_days += 1

    percentage = round(
        (rain_days / total_days) * 100
    )

    return rain_days, total_days, percentage


# ---------------------------------------------------------
# WEB SEARCH
# ---------------------------------------------------------

def search_web(query):
    """
    Uses DuckDuckGo's public HTML search page.

    This does not bypass Facebook.
    It only finds publicly indexed results.
    """

    url = "https://html.duckduckgo.com/html/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Linux; Android 10) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36"
        )
    }

    try:
        r = requests.get(
            url,
            params={"q": query},
            headers=headers,
            timeout=15
        )

        r.raise_for_status()

        html = r.text

        # Extract result links and titles
        results = []

        pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.I | re.S
        )

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
        print(f"[!] Search failed: {e}")
        return []


# ---------------------------------------------------------
# SCHOOL ANNOUNCEMENTS
# ---------------------------------------------------------

def search_school(school, city):
    """
    Searches for suspension announcements and
    public school/social-media results.
    """

    searches = [

        f'"{school}" suspension classes suspended',

        f'"{school}" no classes tomorrow',

        f'"{school}" class suspension',

        f'"{school}" weather announcement',

        f'"{school}" announcement {city}',

        f'site:facebook.com "{school}" suspension',

        f'site:facebook.com "{school}" announcement',

    ]

    all_results = []

    for query in searches:

        print(f"[*] Searching: {query}")

        results = search_web(query)

        for result in results:

            # Prevent duplicates
            if result["url"] not in [
                x["url"] for x in all_results
            ]:
                all_results.append(result)

    return all_results


# ---------------------------------------------------------
# ANALYZE SCHOOL RESULTS
# ---------------------------------------------------------

def analyze_school_results(results):

    suspension_words = [
        "suspended",
        "suspension",
        "no classes",
        "classes suspended",
        "class suspension",
        "walang pasok",
        "cancelled classes",
        "cancel classes",
        "cancelled",
        "cancellation"
    ]

    negative_words = [
        "classes will continue",
        "classes continue",
        "no suspension",
        "regular classes",
        "classes shall proceed"
    ]

    suspension_hits = 0
    negative_hits = 0

    evidence = []

    for result in results:

        text = (
            result["title"] +
            " " +
            result["url"]
        ).lower()

        found = False

        for word in suspension_words:

            if word in text:
                suspension_hits += 1
                found = True
                break

        for word in negative_words:

            if word in text:
                negative_hits += 1
                found = True
                break

        if found:
            evidence.append(result)

    # Limit influence of search results.
    #
    # Search results are NOT official confirmation.

    score = suspension_hits * 8
    score -= negative_hits * 8

    score = max(0, min(40, score))

    return score, evidence


# ---------------------------------------------------------
# FACEBOOK RESULT DETECTION
# ---------------------------------------------------------

def facebook_results(results):

    fb = []

    for result in results:

        if "facebook.com" in result["url"].lower():

            fb.append(result)

    return fb


# ---------------------------------------------------------
# FINAL PREDICTION
# ---------------------------------------------------------

def calculate_final_prediction(
    weather_score,
    announcement_score
):

    """
    Weather has the biggest influence.

    School announcements add evidence but
    are deliberately capped because web search
    cannot guarantee official information.
    """

    final_score = (
        weather_score * 0.70
        +
        announcement_score * 0.30
    )

    final_score = round(
        max(0, min(100, final_score))
    )

    if final_score >= 75:
        result = "HIGH CHANCE OF SUSPENSION"

    elif final_score >= 55:
        result = "POSSIBLE SUSPENSION"

    elif final_score >= 35:
        result = "LOW-MODERATE CHANCE"

    else:
        result = "LIKELY NO SUSPENSION"

    return final_score, result


# ---------------------------------------------------------
# DISPLAY WEATHER
# ---------------------------------------------------------

def display_weather(weather):

    daily = weather["daily"]

    tomorrow_date = daily["time"][1]

    probability = daily[
        "precipitation_probability_max"
    ][1]

    rain = daily[
        "rain_sum"
    ][1]

    precip = daily[
        "precipitation_sum"
    ][1]

    code = daily[
        "weather_code"
    ][1]

    minimum = daily[
        "temperature_2m_min"
    ][1]

    maximum = daily[
        "temperature_2m_max"
    ][1]

    print("\n" + "=" * 50)

    print("TOMORROW'S WEATHER")

    print("=" * 50)

    print(f"Date:              {tomorrow_date}")
    print(f"Weather:           {weather_description(code)}")
    print(f"Temperature:       {minimum}°C - {maximum}°C")
    print(f"Rain probability:  {probability}%")
    print(f"Rain amount:       {rain} mm")
    print(f"Precipitation:     {precip} mm")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    clear()

    print("=" * 50)
    print("             PREDICT RAIN")
    print("=" * 50)

    print(
        "\nPredicts the POSSIBILITY of school suspension "
        "using weather + public announcements."
    )

    print(
        "\nIMPORTANT:"
        "\nThis is not an official suspension checker."
        "\nAlways verify the school's official announcement."
    )

    # -----------------------------------------------------
    # STEP 1
    # -----------------------------------------------------

    print("\n\nSTEP 1 - LOCATION")

    country = ask("What is your country?")
    city = ask("What is your specific city?")

    print("\n[*] Finding your location...")

    location = geocode_location(
        country,
        city
    )

    if not location:

        print(
            "\n[ERROR] Could not find that location."
        )

        return

    print(
        f"\n[+] Location found:"
        f"\n    {location['display']}"
    )

    print("\n[*] Checking online weather forecast...")

    weather = get_weather(
        location["lat"],
        location["lon"]
    )

    if not weather:

        print(
            "\n[ERROR] Weather service unavailable."
        )

        return

    display_weather(weather)

    weather_result = calculate_weather_risk(
        weather
    )

    rain_days, total_days, consistency = (
        check_rain_consistency(weather)
    )

    print(
        f"\nRain consistency:"
        f" {consistency}% "
        f"({rain_days}/{total_days} forecast days)"
    )

    print(
        f"Weather suspension risk:"
        f" {weather_result['score']}%"
    )

    # -----------------------------------------------------
    # STEP 2
    # -----------------------------------------------------

    print("\n\nSTEP 2 - SCHOOL")

    school = ask("What is your school?")

    print(
        "\n[*] Searching public announcements..."
    )

    results = search_school(
        school,
        city
    )

    print(
        f"\n[+] Found {len(results)} public search results."
    )

    announcement_score, evidence = (
        analyze_school_results(results)
    )

    fb = facebook_results(results)

    print(
        f"[+] Facebook results found:"
        f" {len(fb)}"
    )

    print(
        f"[+] Announcement evidence score:"
        f" {announcement_score}%"
    )

    # -----------------------------------------------------
    # SHOW EVIDENCE
    # -----------------------------------------------------

    print("\n" + "=" * 50)
    print("PUBLIC ANNOUNCEMENT EVIDENCE")
    print("=" * 50)

    if evidence:

        for item in evidence[:8]:

            print(
                "\n• " +
                item["title"]
            )

            print(
                "  " +
                item["url"]
            )

    else:

        print(
            "\nNo suspension-related public results found."
        )

    # -----------------------------------------------------
    # FACEBOOK
    # -----------------------------------------------------

    print("\n" + "=" * 50)
    print("PUBLIC FACEBOOK RESULTS")
    print("=" * 50)

    if fb:

        for item in fb[:5]:

            print(
                "\n• " +
                item["title"]
            )

            print(
                "  " +
                item["url"]
            )

    else:

        print(
            "\nNo publicly indexed Facebook results found."
        )

    # -----------------------------------------------------
    # STEP 3
    # -----------------------------------------------------

    print("\n\nSTEP 3 - FINAL PREDICTION")

    final_score, final_result = (
        calculate_final_prediction(
            weather_result["score"],
            announcement_score
        )
    )

    print("\n" + "=" * 50)
    print("                 RESULT")
    print("=" * 50)

    print(
        f"\nSchool: {school}"
    )

    print(
        f"Location: {city}, {country}"
    )

    print(
        f"\nWeather risk: "
        f"{weather_result['score']}%"
    )

    print(
        f"Rain consistency: "
        f"{consistency}%"
    )

    print(
        f"Announcement evidence: "
        f"{announcement_score}%"
    )

    print(
        f"\nFINAL SUSPENSION ESTIMATE:"
        f"\n\n     {final_score}%"
    )

    print(
        f"\n     {final_result}"
    )

    print("\n" + "=" * 50)

    # -----------------------------------------------------
    # EXPLANATION
    # -----------------------------------------------------

    if final_score >= 75:

        print(
            "\n🌧️ The forecast shows significant weather risk "
            "and/or public suspension evidence."
        )

    elif final_score >= 55:

        print(
            "\n🌦️ There are some indicators that suspension "
            "could happen, but confirmation is needed."
        )

    elif final_score >= 35:

        print(
            "\n⛅ There is some weather risk, but the evidence "
            "is not strong enough for a high-confidence prediction."
        )

    else:

        print(
            "\n☀️ Current information does not strongly "
            "indicate a suspension."
        )

    print(
        "\nIMPORTANT:"
        "\nThe official school/LGU announcement always "
        "takes priority over this prediction."
    )

    print("\n")


if __name__ == "__main__":
    main()
