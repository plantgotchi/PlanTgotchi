from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    theme_garden = models.BooleanField(default=False, verbose_name="비밀의 정원 테마 사용")
    theme_farm = models.BooleanField(default=False, verbose_name="활기찬 농장 테마 사용")
    is_onboarded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}'s Profile"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class PlantSpecies(models.Model):
    """식물 종 정보 (RAG 지식 베이스 및 기본 설정값)"""
    name = models.CharField(max_length=100, verbose_name="식물 이름")
    scientific_name = models.CharField(max_length=200, blank=True, verbose_name="학명")
    description = models.TextField(verbose_name="설명")
    
    # 생육 적정 조건
    ideal_temp_min = models.FloatField(default=15.0, verbose_name="최저 적정 온도")
    ideal_temp_max = models.FloatField(default=28.0, verbose_name="최고 적정 온도")
    ideal_humidity_min = models.FloatField(default=40.0, verbose_name="최저 적정 습도")
    ideal_humidity_max = models.FloatField(default=70.0, verbose_name="최고 적정 습도")
    
    # 빛 요구도 (1: 음지, 2: 반음지, 3: 반양지, 4: 양지)
    sunlight_requirement = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        default=3,
        verbose_name="빛 요구도"
    )
    
    # 기본 물주기 주기 (일 단위)
    default_watering_interval = models.IntegerField(default=7, verbose_name="기본 물주기 주기(일)")

    def __str__(self):
        return self.name

class Plant(models.Model):
    """사용자가 등록한 식물 (Digital Twin)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='plants', null=True, blank=True)
    species = models.ForeignKey(PlantSpecies, on_delete=models.CASCADE, related_name='instances')
    nickname = models.CharField(max_length=50, verbose_name="식물 별명")
    emoji = models.CharField(max_length=10, default='🌿', verbose_name="식물 아이콘")
    location = models.CharField(max_length=100, default='강남구', verbose_name="재배 지역 (시/군/구)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="등록일")
    
    # 디지털 트윈 상태 데이터
    vitality = models.IntegerField(default=100, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="활력도")
    stress_level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="스트레스 지수")
    growth_stage = models.CharField(max_length=20, choices=[
        ('SEED', '새싹'),
        ('GROWING', '성장기'),
        ('MATURE', '성체'),
        ('FLOWERING', '개화'),
    ], default='SEED', verbose_name="성장 단계")
    
    # 가상 정원 배치 정보
    garden_position_x = models.FloatField(default=0.0)
    garden_position_y = models.FloatField(default=0.0)
    garden_theme = models.CharField(max_length=50, default='indoor', verbose_name="정원 테마")

    def __str__(self):
        return f"{self.nickname} ({self.species.name})"

class CareRecord(models.Model):
    """케어 이력 (물주기, 영양제 등)"""
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='care_records')
    action_type = models.CharField(max_length=20, choices=[
        ('WATER', '물주기'),
        ('NUTRIENT', '영양제'),
        ('REPOT', '분갈이'),
        ('PRUNE', '가지치기'),
    ], verbose_name="수행 작업")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="수행 시간")
    note = models.TextField(blank=True, verbose_name="메모")

    def __str__(self):
        return f"{self.plant.nickname} - {self.action_type} at {self.timestamp}"

class WateringSchedule(models.Model):
    """지능형 동적 스케줄러 데이터"""
    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='schedules')
    planned_date = models.DateField(verbose_name="예정일")
    is_completed = models.BooleanField(default=False, verbose_name="완료 여부")
    
    # 동적 조정 정보
    adjustment_reason = models.CharField(max_length=255, blank=True, verbose_name="일정 조정 사유")
    original_date = models.DateField(null=True, blank=True, verbose_name="기초 예정일")

    class Meta:
        ordering = ['planned_date']

class WeatherSnapshot(models.Model):
    """기상청 API 연동 데이터 스냅샷"""
    location_code = models.CharField(max_length=20, verbose_name="지역 코드")
    temperature = models.FloatField(verbose_name="기온")
    humidity = models.FloatField(verbose_name="습도")
    uv_index = models.FloatField(null=True, blank=True, verbose_name="자외선 지수")
    condition_text = models.CharField(max_length=100, verbose_name="날씨 상태")
    recorded_at = models.DateTimeField(auto_now_add=True, verbose_name="기록 시간")

    def __str__(self):
        return f"{self.location_code} at {self.recorded_at}"
