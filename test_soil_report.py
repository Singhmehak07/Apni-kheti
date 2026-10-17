from datetime import date
from backend.services.feasibility_service import FeasibilityRecommendationService

def main():
    service = FeasibilityRecommendationService()

    # Data extracted from uploaded Soil Health Card:
    # Farmer: Ramesh Kumar
    # Date of Report: 10-10-2026 (Early October)
    # Location: Rajasthan (e.g., Alwar / Bharatpur / Jaipur mustard-wheat belt: 26.9124, 75.7873)
    # Previous Crop: Bajra (Pearl Millet) -> Land ready for Rabi sowing
    # Soil Test:
    # - pH: 7.8 (Moderately alkaline)
    # - EC: 2.4 dS/m (Saline)
    # - OC: 0.42 % (Low)
    # - Available N: 185 kg/ha (Low -> scaled ~35)
    # - Available P: 11 kg/ha (Low -> scaled ~25)
    # - Available K: 210 kg/ha (Medium -> scaled ~45)
    # - Sulphur: 9.5 ppm (Low)
    # - Zinc: 0.5 ppm (Deficient)
    
    soil_features = {
        'N': 35.0,
        'P': 25.0,
        'K': 45.0,
        'ph': 7.8
    }

    result = service.get_weather_aware_recommendation(
        soil_features=soil_features,
        latitude=26.9124,
        longitude=75.7873,
        query_date=date(2024, 10, 10),
        top_k=5
    )

    w = result['weather_context']
    print("=" * 75)
    print("ANALYSIS OF UPLOADED SOIL HEALTH CARD (RAMESH KUMAR, RAJASTHAN)")
    print("=" * 75)
    print(f"Date of Analysis: 10-10-2024 (Rabi Transition Window, Post-Bajra)")
    print(f"Location: Rajasthan Coordinates (26.9124 N, 75.7873 E)")
    print(f"Soil Chemistry: pH 7.8 (Alkaline), EC 2.4 dS/m (Saline), N 185 (Low), P 11 (Low), K 210 (Med)")
    print("-" * 75)
    print(f"10-Day Real Weather Snapshot:")
    print(f"  • Total Rain (10d): {w['total_rain_10d_mm']} mm")
    print(f"  • Topsoil Moisture: {w['soil_moisture_m3_m3']} m3/m3 ({w['soil_moisture_condition']})")
    print(f"  • Thermal Profile: Mean {w['mean_temperature_c']} C (Min: {w['min_temperature_c']} C, Max: {w['max_temperature_c']} C)")
    print(f"  • Moisture Advice: {w['moisture_advice']}")
    print("=" * 75)
    print("FEASIBILITY-ADJUSTED CROP RECOMMENDATIONS:")
    print("=" * 75)

    for rec in result['recommendations']:
        print(f"\n#{rec['feasibility_rank']} {rec['display_name']} ({rec['season']} Season) — [{rec['status_badge']}]")
        print(f"  • Soil Suitability:      {rec['soil_suitability_score']*100:.1f}%")
        print(f"  • Weather Feasibility:   {rec['weather_feasibility_score']:.1f}%")
        print(f"  • Final Composite Score:  {rec['composite_score']*100:.1f}%")
        print(f"  • Sowing Window:         {rec['seasonal_status']}")
        if rec['field_positives']:
            for p in rec['field_positives']:
                print(f"  • [ADVANTAGE]: {p}")
        if rec['field_warnings']:
            for warn in rec['field_warnings']:
                print(f"  • [FIELD ALERT]: {warn}")

if __name__ == "__main__":
    main()
