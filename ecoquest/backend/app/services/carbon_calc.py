from pydantic import BaseModel, Field

# Constants & Emission Factors
EMISSION_FACTORS = {
    "transport": {"public": 0.1, "car": 0.25, "bike_walk": 0.0},     # kg CO2 per km
    "diet":      {"meat": 120.0, "vegetarian": 45.0, "vegan": 30.0},   # kg CO2 per month
    "electricity": 0.4,                                              # kg CO2 per kWh
}
NATIONAL_AVERAGE_KG_MONTHLY = 416.0  # India national baseline

class QuizInput(BaseModel):
    transport_type: str = Field(..., description="Must be 'public', 'car', or 'bike_walk'")
    transport_distance_km: float = Field(..., ge=0, description="Monthly distance traveled in km")
    diet_type: str = Field(..., description="Must be 'meat', 'vegetarian', or 'vegan'")
    electricity_kwh: float = Field(..., ge=0, description="Monthly electricity consumption in kWh")

class FootprintBreakdown(BaseModel):
    transport: float
    diet: float
    electricity: float

class FootprintResult(BaseModel):
    total_kg: float
    breakdown: FootprintBreakdown
    breakdown_pct: FootprintBreakdown
    vs_national_avg_pct: float
    baseline_set: bool

def calculate_footprint(data: QuizInput) -> FootprintResult:
    """
    Pure deterministic carbon footprint calculation.
    Uses exact emission factors provided.
    """
    # 1. Calculate category emissions
    transport_factor = EMISSION_FACTORS["transport"].get(data.transport_type, 0.0)
    transport_co2 = data.transport_distance_km * transport_factor
    
    diet_co2 = EMISSION_FACTORS["diet"].get(data.diet_type, 0.0)
    
    electricity_co2 = data.electricity_kwh * EMISSION_FACTORS["electricity"]
    
    # 2. Total
    total_kg = transport_co2 + diet_co2 + electricity_co2
    
    # 3. Percentages breakdown
    if total_kg > 0:
        transport_pct = (transport_co2 / total_kg) * 100
        diet_pct = (diet_co2 / total_kg) * 100
        electricity_pct = (electricity_co2 / total_kg) * 100
    else:
        transport_pct = 0.0
        diet_pct = 0.0
        electricity_pct = 0.0
        
    # 4. Compare vs India national average
    vs_national_avg_pct = ((total_kg - NATIONAL_AVERAGE_KG_MONTHLY) / NATIONAL_AVERAGE_KG_MONTHLY) * 100
    
    return FootprintResult(
        total_kg=round(total_kg, 1),
        breakdown=FootprintBreakdown(
            transport=round(transport_co2, 1),
            diet=round(diet_co2, 1),
            electricity=round(electricity_co2, 1)
        ),
        breakdown_pct=FootprintBreakdown(
            transport=round(transport_pct, 1),
            diet=round(diet_pct, 1),
            electricity=round(electricity_pct, 1)
        ),
        vs_national_avg_pct=round(vs_national_avg_pct, 1),
        baseline_set=False  # Database layer determines and overrides this
    )
