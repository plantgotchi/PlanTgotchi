import math
import requests
import os
from datetime import datetime, timedelta

OWM_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY')
OWM_URL = 'https://api.openweathermap.org/data/2.5/weather'


def get_weather_data(lat: float, lon: float) -> dict:
    params = {
        'lat': lat, 'lon': lon,
        'appid': OWM_API_KEY,
        'units': 'metric'
    }
    resp = requests.get(OWM_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        'temp':     data['main']['temp'],
        'temp_max': data['main']['temp_max'],
        'temp_min': data['main']['temp_min'],
        'humidity': data['main']['humidity'],
        'rain':     data.get('rain', {}).get('1h', 0.0),
        'lat':      lat
    }


def calc_extraterrestrial_radiation(lat: float, doy: int) -> float:
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    d  = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(d))
    Gsc = 0.0820
    Ra = (24 * 60 / math.pi) * Gsc * dr * (
        ws * math.sin(phi) * math.sin(d) +
        math.cos(phi) * math.cos(d) * math.sin(ws)
    )
    return Ra


def calc_eto_hargreaves(tmax: float, tmin: float, tmean: float, lat: float) -> float:
    doy = datetime.now().timetuple().tm_yday
    Ra  = calc_extraterrestrial_radiation(lat, doy)
    ETo = 0.0023 * (tmean + 17.8) * math.sqrt(tmax - tmin) * Ra
    return round(ETo, 2)


def adjust_watering_schedule(plant, weather: dict, eto: float):
    """
    관수 주기 동적 조정
    우선순위: 강수량 조건 > 온도/ETo 조건

    기준 출처:
    - 기상청 폭염특보 발령 기준 (35도/33도)
    - FAO Irrigation and Drainage Paper No.56 (유효강수량 10mm)
    - 농촌진흥청 물주기 가이드 (5mm 미만 무효)
    """
    temp     = weather['temp']
    humidity = weather['humidity']
    rain     = weather['rain'] * 24  # mm/h → mm/day

    next_watering = plant.next_watering

    
    if rain >= 10:
        # 정식강수/폭우: 토양 포화 → 1일 미루기
        return next_watering + timedelta(days=1)

    if 5 <= rain < 10:
       
        return next_watering

   
    if temp >= 35 and eto >= 5.0:
       
        return next_watering - timedelta(days=1)

    if temp >= 33 and humidity <= 40 and 3.5 <= eto < 5.0:
        
        return next_watering - timedelta(hours=12)

    return next_watering


def update_plant_watering_calendar(plant, lat, lon):
    weather = get_weather_data(lat, lon)
    eto = calc_eto_hargreaves(
        weather['temp_max'], weather['temp_min'],
        weather['temp'], weather['lat']
    )
    weather['eto'] = eto
    plant.next_watering = adjust_watering_schedule(plant, weather, eto)
    plant.save()
