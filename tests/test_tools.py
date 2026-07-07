"""
Test Grubu 3: Drone Araç Fonksiyonları
=======================================
DroneTools'un tüm araç fonksiyonları entegrasyon testleri.
"""

import pytest
from src.tools.drone_tools import DroneTools, ToolResult
from src.simulation.drone import DroneState, FlightMode


class TestTakeoff:
    def test_successful_takeoff(self, drone_tools):
        result = drone_tools.takeoff(30.0)
        assert result.success is True
        assert result.action == "takeoff"

    def test_takeoff_sets_altitude(self, drone_tools):
        drone_tools.takeoff(50.0)
        assert drone_tools.state.altitude == pytest.approx(50.0)

    def test_takeoff_sets_in_air(self, drone_tools):
        drone_tools.takeoff(30.0)
        assert drone_tools.state.in_air is True

    def test_takeoff_sets_mode_hovering(self, drone_tools):
        drone_tools.takeoff(30.0)
        assert drone_tools.state.mode == FlightMode.HOVERING

    def test_takeoff_drains_battery(self, drone_tools):
        initial_bat = drone_tools.state.battery
        drone_tools.takeoff(50.0)
        assert drone_tools.state.battery < initial_bat

    def test_takeoff_when_airborne_fails(self, airborne_tools):
        result = airborne_tools.takeoff(80.0)
        assert result.success is False
        assert "havada" in result.message.lower()

    def test_takeoff_state_before_captured(self, drone_tools):
        result = drone_tools.takeoff(30.0)
        assert result.state_before.altitude == 0.0

    def test_takeoff_result_has_data(self, drone_tools):
        result = drone_tools.takeoff(40.0)
        assert "target_altitude" in result.data
        assert result.data["target_altitude"] == pytest.approx(40.0)


class TestLand:
    def test_successful_land(self, airborne_tools):
        result = airborne_tools.land()
        assert result.success is True

    def test_land_sets_altitude_zero(self, airborne_tools):
        airborne_tools.land()
        assert airborne_tools.state.altitude == pytest.approx(0.0)

    def test_land_sets_in_air_false(self, airborne_tools):
        airborne_tools.land()
        assert airborne_tools.state.in_air is False

    def test_land_sets_mode_idle(self, airborne_tools):
        airborne_tools.land()
        assert airborne_tools.state.mode == FlightMode.IDLE

    def test_land_on_ground_fails(self, drone_tools):
        result = drone_tools.land()
        assert result.success is False

    def test_land_result_has_landing_time(self, airborne_tools):
        result = airborne_tools.land()
        assert "landing_time_s" in result.data


class TestReturnToHome:
    def test_rth_successful(self, airborne_tools):
        airborne_tools.state.x = 100.0
        airborne_tools.state.y = 100.0
        result = airborne_tools.return_to_home()
        assert result.success is True

    def test_rth_returns_to_origin(self, airborne_tools):
        airborne_tools.state.x = 80.0
        airborne_tools.state.y = 60.0
        airborne_tools.return_to_home()
        assert airborne_tools.state.x == pytest.approx(0.0)
        assert airborne_tools.state.y == pytest.approx(0.0)

    def test_rth_lands(self, airborne_tools):
        airborne_tools.return_to_home()
        assert airborne_tools.state.in_air is False
        assert airborne_tools.state.altitude == pytest.approx(0.0)

    def test_rth_on_ground_fails(self, drone_tools):
        result = drone_tools.return_to_home()
        assert result.success is False

    def test_rth_result_has_distance(self, airborne_tools):
        airborne_tools.state.x = 30.0
        airborne_tools.state.y = 40.0
        result = airborne_tools.return_to_home()
        assert "distance_covered_m" in result.data
        assert result.data["distance_covered_m"] == pytest.approx(50.0, rel=0.01)


class TestGoTo:
    def test_goto_successful(self, airborne_tools):
        result = airborne_tools.go_to(50.0, 50.0, 30.0)
        assert result.success is True

    def test_goto_updates_position(self, airborne_tools):
        airborne_tools.go_to(70.0, 80.0, 40.0)
        assert airborne_tools.state.x == pytest.approx(70.0)
        assert airborne_tools.state.y == pytest.approx(80.0)
        assert airborne_tools.state.altitude == pytest.approx(40.0)

    def test_goto_on_ground_fails(self, drone_tools):
        result = drone_tools.go_to(50.0, 50.0, 30.0)
        assert result.success is False

    def test_goto_result_has_distance(self, airborne_tools):
        result = airborne_tools.go_to(30.0, 40.0, 30.0)
        assert "distance_m" in result.data
        assert result.data["distance_m"] == pytest.approx(50.0, rel=0.01)

    def test_goto_drains_battery(self, airborne_tools):
        initial_bat = airborne_tools.state.battery
        airborne_tools.go_to(200.0, 0.0, 50.0)
        assert airborne_tools.state.battery < initial_bat


class TestGetTelemetry:
    def test_telemetry_always_succeeds(self, drone_tools):
        result = drone_tools.get_telemetry()
        assert result.success is True

    def test_telemetry_does_not_change_state(self, drone_tools):
        state_before = drone_tools.state.altitude
        drone_tools.get_telemetry()
        assert drone_tools.state.altitude == state_before

    def test_telemetry_result_has_message(self, drone_tools):
        result = drone_tools.get_telemetry()
        assert len(result.message) > 0

    def test_telemetry_result_has_flight_estimate(self, airborne_tools):
        result = airborne_tools.get_telemetry()
        assert "flight_estimate" in result.data


class TestToolResultStructure:
    """ToolResult veri yapısı bütünlük testleri."""

    def test_result_has_required_fields(self, drone_tools):
        result = drone_tools.takeoff(30.0)
        assert hasattr(result, "success")
        assert hasattr(result, "action")
        assert hasattr(result, "message")
        assert hasattr(result, "state_before")
        assert hasattr(result, "state_after")
        assert hasattr(result, "timestamp")

    def test_result_to_dict(self, airborne_tools):
        result = airborne_tools.land()
        d = result.to_dict()
        assert "success" in d
        assert "action" in d
        assert "state_after" in d


class TestEmergencyActions:
    def test_emergency_land_works_airborne(self, airborne_tools):
        result = airborne_tools.emergency_land()
        assert result.success is True
        assert airborne_tools.state.in_air is False
        assert airborne_tools.state.mode == FlightMode.EMERGENCY

    def test_emergency_land_on_ground_fails(self, drone_tools):
        result = drone_tools.emergency_land()
        assert result.success is False

    def test_motor_stop_in_air_causes_drop(self, airborne_tools):
        initial_alt = airborne_tools.state.altitude
        result = airborne_tools.motor_stop()
        assert result.success is True
        assert airborne_tools.state.altitude == 0.0
        assert airborne_tools.state.in_air is False
        assert "yere çakıldı" in result.message.lower() or "düşüş" in result.message.lower()

    def test_motor_stop_on_ground(self, drone_tools):
        result = drone_tools.motor_stop()
        assert result.success is True
        assert "motorlar kapatıldı" in result.message.lower()

