from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('space/<str:space_type>/', views.space_view, name='space_view'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('ai-chat/', views.ai_chat, name='ai_chat'),
    path('water/<int:plant_id>/', views.water_plant, name='water_plant'),
    path('delete/<int:plant_id>/', views.delete_plant, name='delete_plant'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # PWA 필수 파일 라우팅
    path('manifest.json', views.manifest_json, name='manifest_json'),
    path('sw.js', views.service_worker, name='service_worker'),
]

