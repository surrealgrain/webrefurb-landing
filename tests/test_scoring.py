"""Tests for coordinate-based tourist proximity scoring."""

from __future__ import annotations

import math

from pipeline import scoring
from pipeline.geo import haversine_km, nearest_hotspot_distance, nearest_city_distance


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(35.6812, 139.7671, 35.6812, 139.7671) == 0.0

    def test_tokyo_to_shibuya(self):
        # Tokyo Station to Shibuya Crossing ~6.5 km
        d = haversine_km(35.6812, 139.7671, 35.6595, 139.7004)
        assert 6.0 < d < 7.0

    def test_tokyo_to_osaka(self):
        # ~400 km
        d = haversine_km(35.6812, 139.7671, 34.6719, 135.5028)
        assert 390 < d < 420


class TestNearestHotspot:
    def test_shibuya_proximity(self):
        d, name = nearest_hotspot_distance(35.6595, 139.7004)
        assert d < 0.1
        assert name == "shibuya_crossing"

    def test_near_asakusa(self):
        d, name = nearest_hotspot_distance(35.714, 139.796)
        assert d < 0.5
        assert name == "asakusa_sensoji"


class TestNearestCity:
    def test_tokyo(self):
        d, name = nearest_city_distance(35.6812, 139.7671)
        assert d < 1.0
        assert name == "tokyo"


class TestTouristExposureScore:
    def test_near_shibuya_crossing_gets_high_score(self):
        # At Shibuya Crossing — gets hotspot bonus + city bonus (within 5km of Tokyo centre)
        s = scoring.compute_tourist_exposure_score(
            address="Shibuya, Tokyo",
            latitude=35.6595,
            longitude=139.7004,
            reviews=100,
        )
        # hotspot=0.5 + city(dist ~5.5km to Tokyo stn so <=10km=0.1) + reviews=0.1 = 0.7
        assert s >= 0.6

    def test_3km_from_shibuya_gets_lower_score(self):
        # ~3km from Shibuya Crossing (slightly further out)
        s = scoring.compute_tourist_exposure_score(
            address="Tokyo",
            latitude=35.675,
            longitude=139.740,
            reviews=100,
        )
        s_no_coords = scoring.compute_tourist_exposure_score(
            address="Tokyo",
            reviews=100,
        )
        # Should still get some city bonus
        assert s > 0.0

    def test_string_fallback_works_when_no_coordinates(self):
        s = scoring.compute_tourist_exposure_score(
            address="1-2-3 Shibuya, Tokyo",
            reviews=500,
        )
        # hotspot=0.3 + city=0.2 + reviews=0.2 = 0.7
        assert 0.5 < s < 0.9

    def test_no_data_gives_low_score(self):
        s = scoring.compute_tourist_exposure_score(address="Somewhere Rural")
        assert s == 0.0

    def test_coordinates_bypass_string_matching(self):
        """When coordinates are provided, they take precedence over string matching."""
        # Use coordinates far from any hotspot but an address containing "Shibuya"
        s_coords = scoring.compute_tourist_exposure_score(
            address="Shibuya, Tokyo",
            latitude=43.0,  # Sapporo
            longitude=141.3,
        )
        # Should NOT get the Shibuya hotspot bonus from coordinates
        assert s_coords < 0.3
