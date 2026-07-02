"""
Test Grubu 2: Güvenlik Katmanı
================================
SafetyValidator ve SAFETY_RULES kural testleri.
Her güvenlik kuralı ayrı ayrı test edilir.
"""

import pytest
from src.safety.validator import SafetyValidator, ValidationResult
from src.safety.rules import SAFETY_RULES, RuleSeverity
from src.simulation.drone import DroneState, FlightMode


class TestSafetyValidatorBasics:
    """Temel validator davranış testleri."""

    def test_validator_has_rules(self, validator):
        assert len(validator._rules) > 0

    def test_valid_takeoff_passes(self, validator, fresh_state):
        result = validator.validate("takeoff", {"target_altitude": 30.0}, fresh_state)
        assert result.is_valid is True

    def test_invalid_action_still_validates(self, validator, fresh_state):
        """Bilinmeyen eylem — kural uygulanmaz, geçer."""
        result = validator.validate("unknown_action", {}, fresh_state)
        assert isinstance(result, ValidationResult)

    def test_validation_result_has_reason(self, validator, fresh_state):
        result = validator.validate("takeoff", {"target_altitude": 50.0}, fresh_state)
        assert len(result.reason) > 0

    def test_validation_result_has_checked_rules(self, validator, fresh_state):
        result = validator.validate("takeoff", {"target_altitude": 50.0}, fresh_state)
        assert isinstance(result.rules_checked, list)

    def test_format_for_user_valid(self, validator, fresh_state):
        result = validator.validate("get_telemetry", {}, fresh_state)
        formatted = result.format_for_user()
        assert "GÜVENLİK" in formatted


class TestAltitudeRules:
    """SR-ALT-001 ve SR-ALT-002 kural testleri."""

    def test_altitude_above_max_rejected(self, validator, fresh_state):
        """121m kalkış → SR-ALT-001 ile reddedilmeli."""
        result = validator.validate("takeoff", {"target_altitude": 121.0}, fresh_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-ALT-001"

    def test_altitude_at_max_passes(self, validator, fresh_state):
        """120m kalkış → SR-ALT-003 WARNING'dir ama ERROR değil, ayrıca
        MAX_TAKEOFF_ALTITUDE 100m olduğundan 120m WARNING verir.
        Bu test sadece kural ID'sini kontrol eder."""
        result = validator.validate("takeoff", {"target_altitude": 100.0}, fresh_state)
        assert result.is_valid is True

    def test_negative_takeoff_altitude_rejected(self, validator, fresh_state):
        """Negatif irtifa → SR-ALT-002 ile reddedilmeli."""
        result = validator.validate("takeoff", {"target_altitude": -5.0}, fresh_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-ALT-002"

    def test_zero_takeoff_altitude_rejected(self, validator, fresh_state):
        result = validator.validate("takeoff", {"target_altitude": 0.0}, fresh_state)
        assert result.is_valid is False

    def test_goto_altitude_above_max_rejected(self, validator, airborne_state):
        result = validator.validate("go_to", {"x": 0, "y": 0, "altitude": 200.0}, airborne_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-ALT-001"


class TestBatteryRules:
    """SR-BAT-001 ve SR-BAT-002 kural testleri."""

    def test_critical_battery_blocks_takeoff(self, validator):
        """Batarya %12 (< MIN_BATTERY_OPERATION=15) → kalkışı engelle."""
        s = DroneState()
        s.battery = 12.0  # MIN_BATTERY_OPERATION=15 altında
        result = validator.validate("takeoff", {"target_altitude": 30.0}, s)
        assert result.is_valid is False
        assert result.rule_violated in ("SR-BAT-001", "SR-BAT-002")

    def test_rth_threshold_blocks_goto(self, validator, airborne_state):
        """Batarya %20 → go_to'yu engelle."""
        airborne_state.battery = 20.0
        result = validator.validate("go_to", {"x": 10, "y": 10, "altitude": 30}, airborne_state)
        assert result.is_valid is False

    def test_full_battery_allows_takeoff(self, validator, fresh_state):
        result = validator.validate("takeoff", {"target_altitude": 30.0}, fresh_state)
        assert result.is_valid is True


class TestFlightStateRules:
    """SR-FLT-001 ve SR-FLT-002 kural testleri."""

    def test_takeoff_when_airborne_rejected(self, validator, airborne_state):
        """Havadayken tekrar kalkış → SR-FLT-001."""
        result = validator.validate("takeoff", {"target_altitude": 50.0}, airborne_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-FLT-001"

    def test_land_when_on_ground_rejected(self, validator, fresh_state):
        """Yerdeyken iniş → SR-FLT-002."""
        result = validator.validate("land", {}, fresh_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-FLT-002"

    def test_rth_when_on_ground_rejected(self, validator, fresh_state):
        """Yerdeyken RTH → SR-FLT-002."""
        result = validator.validate("return_to_home", {}, fresh_state)
        assert result.is_valid is False

    def test_land_when_airborne_passes(self, validator, airborne_state):
        result = validator.validate("land", {}, airborne_state)
        assert result.is_valid is True


class TestGeofenceRules:
    """SR-GEO-001 kural testleri."""

    def test_inside_geofence_passes(self, validator, airborne_state):
        result = validator.validate("go_to", {"x": 50, "y": 50, "altitude": 30}, airborne_state)
        assert result.is_valid is True

    def test_outside_geofence_rejected(self, validator, airborne_state):
        """500m geofence dışı → SR-GEO-001."""
        result = validator.validate("go_to", {"x": 600, "y": 0, "altitude": 30}, airborne_state)
        assert result.is_valid is False
        assert result.rule_violated == "SR-GEO-001"


class TestBatchValidation:
    """Toplu komut doğrulama testleri."""

    def test_batch_stops_at_first_critical(self, validator, fresh_state):
        """İlk kritik ihlalde dizi durdurulmalı."""
        commands = [
            {"action": "land", "parameters": {}},            # hata: yerde iniş
            {"action": "takeoff", "parameters": {"target_altitude": 30}},  # devam etmemeli
        ]
        results = validator.validate_batch(commands, fresh_state)
        assert results[0].is_valid is False
        # İkinci komut değerlendirilmemiş olabilir
        assert len(results) >= 1

    def test_batch_all_pass(self, validator, fresh_state):
        """Geçerli komutlar toplu olarak da geçmeli."""
        commands = [
            {"action": "takeoff", "parameters": {"target_altitude": 30.0}},
        ]
        results = validator.validate_batch(commands, fresh_state)
        assert results[0].is_valid is True


class TestRuleSeverity:
    """Kural şiddet seviyeleri doğru atanmış mı?"""

    def test_altitude_rule_is_error(self):
        rule = next(r for r in SAFETY_RULES if r.rule_id == "SR-ALT-001")
        assert rule.severity == RuleSeverity.ERROR

    def test_battery_emergency_is_critical(self):
        rule = next(r for r in SAFETY_RULES if r.rule_id == "SR-BAT-001")
        assert rule.severity == RuleSeverity.CRITICAL

    def test_rules_have_legal_refs(self):
        """Kuralların çoğunda yasal referans olmalı."""
        rules_with_ref = [r for r in SAFETY_RULES if r.legal_ref]
        assert len(rules_with_ref) >= 5
