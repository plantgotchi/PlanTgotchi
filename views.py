import random
import requests
import json
import calendar as py_calendar
from bs4 import BeautifulSoup
from datetime import date, timedelta, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.http import JsonResponse, HttpResponse

from .models import Plant, PlantSpecies, WateringSchedule, UserProfile, CareRecord
from .utils import get_smart_watering_interval, get_ai_encyclopedia_answer, generate_ai_medical_report, get_josa, scrape_plant_info

# OpenWeatherMap API 키 (없을 경우 fallback 적용)
OPENWEATHER_API_KEY = getattr(settings, 'OPENWEATHER_API_KEY', 'default_mock_key')

def get_dynamic_watering_offset(location_name):
    """
    [핵심 알고리즘] 실시간 기상 데이터를 파싱하여 증발량을 계산하고, 
    기준 물주기 주기에서 가감산할 날짜(Offset)를 정수로 반환합니다.
    """
    if OPENWEATHER_API_KEY == 'default_mock_key' or not OPENWEATHER_API_KEY:
        return 0
        
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location_name}&appid={OPENWEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=3)
        res.raise_for_status()
        data = res.json()
        
        temp = data['main']['temp']
        condition = data['weather'][0]['main']
        
        offset = 0
        # 강수 조건 (습도가 높아 증발량이 적으므로 주기를 연장)
        if 'Rain' in condition or 'Thunderstorm' in condition:
            offset += 2  # 비 오면 2일 연기
        elif 'Drizzle' in condition:
            offset += 1  # 이슬비 1일 연기
            
        # 기온 조건 (온도가 높아 증발량이 많으므로 주기를 단축)
        if temp >= 33.0:
            offset -= 2  # 33도 이상 폭염 시 2일 단축
        elif temp >= 28.0:
            offset -= 1  # 28도 이상 더위 시 1일 단축
            
        elif temp <= 5.0:
            offset += 3  # 한파 휴면기 3일 연기
            
        return offset
    except Exception as e:
        print(f"Weather API Error: {e}")
        return 0

# [인증 관련]
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('onboarding')
    else: form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def onboarding(request):
    if request.method == 'POST':
        themes = request.POST.getlist('themes')
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.theme_garden = 'GARDEN' in themes
        profile.theme_farm = 'FARM' in themes
        profile.is_onboarded = True
        profile.save()
        return redirect('home')
    return render(request, 'plants/onboarding.html')

# [메인 허브]
@login_required
def home(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.is_onboarded: return redirect('onboarding')
    return render(request, 'plants/home.html', {'profile': profile})

def get_weather_info(location_name):
    """뷰 상단에 표시될 날씨 요약 정보 (API 또는 Mocking)"""
    josa = get_josa(location_name, '은는')
    return {
        'location_name': location_name, 'temp': 21.5, 'humidity': 45,
        'condition': '맑음', 'icon': 'fa-sun',
        'recommendation': f"{location_name}{josa} 현재 아주 화창한 날씨예요! ☀️"
    }

@login_required
def dashboard(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'plants/dashboard.html', {'profile': profile})

# [가상 공간 상세 뷰]
@login_required
def space_view(request, space_type):
    profile = request.user.profile
    if (space_type == 'garden' and not profile.theme_garden) or (space_type == 'farm' and not profile.theme_farm):
        return redirect('home')
        
    if request.method == 'POST':
        species_name = request.POST.get('species_name', '').strip()
        nickname = request.POST.get('nickname', '').strip()
        location = request.POST.get('location', '서울')
        emoji = request.POST.get('emoji', '🌿')
        
        if species_name and nickname:
            # 1. SLM 또는 Fallback을 통해 기본 간격 산출
            base_interval = get_smart_watering_interval(species_name)
            
            species, _ = PlantSpecies.objects.get_or_create(
                name=species_name,
                defaults={
                    'scientific_name': f"{species_name} sp.",
                    'description': f"{species_name}의 생육 정보가 등록되었습니다.",
                    'default_watering_interval': base_interval
                }
            )
            plant = Plant.objects.create(
                user=request.user, species=species, nickname=nickname, 
                emoji=emoji, location=location, garden_theme=space_type
            )
            
            # 2. [날씨 동적 스케줄링 적용]
            weather_offset = get_dynamic_watering_offset(location)
            final_interval = max(1, base_interval + weather_offset) # 최소 1일 보장
            
            WateringSchedule.objects.create(plant=plant, planned_date=date.today() + timedelta(days=final_interval))
            msg = f"🎉 {nickname}가 심어졌습니다! (기본 {base_interval}일 주기"
            if weather_offset != 0:
                direction = "단축" if weather_offset < 0 else "연장"
                msg += f" / ☀️날씨 반영: {abs(weather_offset)}일 {direction})"
            else:
                msg += ")"
            messages.success(request, msg)
            return redirect('space_view', space_type=space_type)

    plants = request.user.plants.filter(garden_theme=space_type)
    weather = get_weather_info(plants.first().location if plants.exists() else '서울')
    
    ai_report = "식물을 등록하면 AI 주치의가 실시간 진단을 시작합니다."
    if plants.exists():
        p = plants.order_by('vitality').first()
        ai_report = generate_ai_medical_report(p, weather)
    
    return render(request, 'plants/space_view.html', {'space_type': space_type, 'plants': plants, 'weather': weather, 'ai_report': ai_report, 'theme_name': '비밀의 정원' if space_type == 'garden' else '활기찬 농장'})

# [데이터 관리]
@login_required
@require_POST
def water_plant(request, plant_id):
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)
    
    # 기록 생성 및 기존 미완료 일정 삭제 (Hard Delete)
    CareRecord.objects.create(plant=plant, action_type='WATER')
    WateringSchedule.objects.filter(plant=plant, is_completed=False).delete()
    
    # [날씨 동적 스케줄링 적용] 다음 물주기 날짜 계산
    base_interval = plant.species.default_watering_interval
    weather_offset = get_dynamic_watering_offset(plant.location)
    final_interval = max(1, base_interval + weather_offset)
    
    next_date = date.today() + timedelta(days=final_interval)
    WateringSchedule.objects.create(plant=plant, planned_date=next_date)
    
    msg = f"물주기 완료! "
    if weather_offset < 0:
        msg += f"폭염/건조가 예상되어 주기가 {abs(weather_offset)}일 앞당겨졌습니다. (다음: {next_date.strftime('%m월 %d일')})"
    elif weather_offset > 0:
        msg += f"비/다습이 예상되어 주기가 {weather_offset}일 연장되었습니다. (다음: {next_date.strftime('%m월 %d일')})"
    else:
        msg += f"다음 일정은 {next_date.strftime('%m월 %d일')}입니다."
        
    return JsonResponse({'status': 'success', 'message': msg})

@login_required
@require_POST
def delete_plant(request, plant_id):
    plant = get_object_or_404(Plant, id=plant_id, user=request.user)
    space_type = plant.garden_theme
    WateringSchedule.objects.filter(plant=plant).delete()
    CareRecord.objects.filter(plant=plant).delete()
    plant.delete()
    return redirect('space_view', space_type=space_type)

# [달력 뷰]
@login_required
def calendar_view(request):
    today = date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    cal_obj = py_calendar.Calendar(firstweekday=6)
    month_days = cal_obj.monthdatescalendar(year, month)
    schedules = WateringSchedule.objects.filter(plant__user=request.user, plant__isnull=False, is_completed=False, planned_date__range=[month_days[0][0], month_days[-1][-1]]).select_related('plant')
    sched_dict = {}
    for s in schedules:
        if s.planned_date not in sched_dict: sched_dict[s.planned_date] = []
        sched_dict[s.planned_date].append(s)
    calendar_data = []
    for week in month_days:
        week_data = []
        for d in week:
            day_schedules = sched_dict.get(d, [])
            plant_list = ", ".join([f"{s.plant.emoji}{s.plant.nickname}" for s in day_schedules])
            week_data.append({'date': d, 'display_date': d.strftime('%Y년 %m월 %d일'), 'day': d.day, 'is_today': d == today, 'is_current_month': d.month == month, 'has_schedules': len(day_schedules) > 0, 'plant_list': plant_list})
        calendar_data.append(week_data)
    return render(request, 'plants/calendar.html', {'calendar_data': calendar_data, 'current_year': year, 'current_month': month, 'prev_month': (datetime(year, month, 1) - timedelta(days=1)), 'next_month': (datetime(year, month, 1) + timedelta(days=32)).replace(day=1)})

# [AI 챗봇 - SLM RAG 연동 버전]
@login_required
def ai_chat(request):
    plants = request.user.plants.all()
    weather = get_weather_info(plants.first().location if plants.exists() else '서울')
    chat_history = request.session.get('chat_history', [])
    
    if request.method == 'POST':
        user_msg = request.POST.get('message', '').strip()
        ai_reply = ""
        fast_track = False
        
        # 1. Fast-Track: 기록 조회 및 행동 연동 (Bypass)
        if any(k in user_msg for k in ["물 줬나", "언제", "기록", "마지막"]):
            for p in plants:
                if p.nickname in user_msg:
                    last = CareRecord.objects.filter(plant=p, action_type='WATER').order_by('-timestamp').first()
                    ai_reply = f"집사님! '{p.nickname}'는 {last.timestamp.strftime('%m월 %d일')}에 마지막으로 물을 마셨어요. 💧" if last else f"'{p.nickname}'의 기록이 아직 없네요!"
                    fast_track = True; break
        elif "물" in user_msg and any(k in user_msg for k in ["줬어", "완료", "줬다"]):
            for p in plants:
                if p.nickname in user_msg:
                    CareRecord.objects.create(plant=p, action_type='WATER')
                    WateringSchedule.objects.filter(plant=p, is_completed=False).delete()
                    
                    # 동적 스케줄링 적용
                    base_int = p.species.default_watering_interval
                    offset = get_dynamic_watering_offset(p.location)
                    next_d = date.today() + timedelta(days=max(1, base_int + offset))
                    
                    WateringSchedule.objects.create(plant=p, planned_date=next_d)
                    ai_reply = f"📝 '{p.nickname}' 물주기 완료! 날씨({offset}일 조정)를 반영해 다음 물주기는 {next_d.strftime('%m월 %d일')}로 달력에 업데이트했어요. ✨"
                    fast_track = True; break
        
        # 2. RAG AI 상담 (SLM 연동)
        if not fast_track:
            plant_info = "\n".join([f"- {p.nickname}({p.species.name}): {p.species.description}" for p in plants])
            context = f"현재 날씨: {weather['temp']}도, {weather['condition']}\n보유 식물 정보:\n{plant_info}"
            ai_reply = get_ai_encyclopedia_answer(user_msg, context)

        chat_history.append({'role': 'user', 'content': user_msg})
        chat_history.append({'role': 'ai', 'content': ai_reply})
        request.session['chat_history'] = chat_history[-10:]
        return redirect('ai_chat')

    reports = []
    if plants.exists():
        for p in plants[:2]:
            josa = get_josa(p.nickname, '은는')
            reports.append({'plant': p, 'report': f"{p.nickname}{josa} 쾌적한 환경 속에 잘 자라고 있네요! 건강한 반려생활 되세요. 🌱"})
            
# [PWA 지원용 뷰]
def manifest_json(request):
    manifest = {
        "name": "PlanTgotchi",
        "short_name": "PlanTgotchi",
        "description": "지능형 야외 정원 반려식물 케어 플랫폼",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#238636",
        "icons": [
            {
                "src": "/static/plants/images/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/plants/images/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return JsonResponse(manifest)

def service_worker(request):
    sw_code = """
    const CACHE_NAME = 'plantgotchi-v3';

    self.addEventListener('install', event => {
        // 즉시 설치 및 활성화하여 기존의 꼬인 캐시/워커 밀어내기
        self.skipWaiting();
    });

    self.addEventListener('activate', event => {
        event.waitUntil(clients.claim());
    });

    self.addEventListener('fetch', event => {
        // [긴급 핫픽스] 브라우저 이동 무반응(Silent Fail)을 원천 차단하기 위해
        // 서비스 워커의 fetch 가로채기 기능을 완전히 비활성화합니다.
        // 이렇게 하면 PWA(앱 설치) 기능은 유지되면서, 페이지 이동은 기존 웹처럼 정상 작동합니다.
        return; 
    });
    """
    return HttpResponse(sw_code, content_type='application/javascript')
