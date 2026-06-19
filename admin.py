from django.contrib import admin
from .models import PlantSpecies, Plant, CareRecord, WateringSchedule, WeatherSnapshot

@admin.register(PlantSpecies)
class PlantSpeciesAdmin(admin.ModelAdmin):
    list_display = ('name', 'scientific_name', 'ideal_temp_min', 'ideal_temp_max', 'sunlight_requirement', 'default_watering_interval')
    list_filter = ('sunlight_requirement',)
    search_fields = ('name', 'scientific_name', 'description')

@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'species', 'vitality', 'stress_level', 'growth_stage', 'created_at')
    list_filter = ('growth_stage', 'species', 'garden_theme')
    search_fields = ('nickname', 'species__name')
    # 디지털 트윈 상태를 강조하기 위해 활력도와 스트레스 지수를 리스트에서 바로 볼 수 있게 함

@admin.register(CareRecord)
class CareRecordAdmin(admin.ModelAdmin):
    list_display = ('plant', 'action_type', 'timestamp')
    list_filter = ('action_type', 'timestamp')
    search_fields = ('plant__nickname', 'note')
    date_hierarchy = 'timestamp'

@admin.register(WateringSchedule)
class WateringScheduleAdmin(admin.ModelAdmin):
    list_display = ('plant', 'planned_date', 'is_completed', 'adjustment_reason')
    list_filter = ('is_completed', 'planned_date')
    search_fields = ('plant__nickname', 'adjustment_reason')
    list_editable = ('is_completed',) # 관리자 페이지에서 바로 체크 가능하게 함
    date_hierarchy = 'planned_date'

@admin.register(WeatherSnapshot)
class WeatherSnapshotAdmin(admin.ModelAdmin):
    list_display = ('location_code', 'temperature', 'humidity', 'uv_index', 'condition_text', 'recorded_at')
    list_filter = ('location_code', 'recorded_at')
    search_fields = ('location_code', 'condition_text')
    readonly_fields = ('recorded_at',) # 생성 시간은 읽기 전용으로 설정
