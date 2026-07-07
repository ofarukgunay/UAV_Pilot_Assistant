"""
Test Grubu 4: Batarya Yöneticisi ve Görev Planlayıcı
=====================================================
"""

import pytest
from src.battery.manager import BatteryManager, BatteryStatus, BatteryAlert
from src.mission.planner import MissionPlanner, Mission, MissionStatus, StepStatus
from src.simulation.drone import DroneState, FlightMode


class TestBatteryManager:
    """BatteryManager testleri."""

    def test_full_battery_is_normal(self, battery_manager, fresh_state):
        alert = battery_manager.evaluate(fresh_state)
        assert alert.status == BatteryStatus.NORMAL

    def test_low_battery_status(self, battery_manager, fresh_state):
        fresh_state.battery = 25.0
        alert = battery_manager.evaluate(fresh_state)
        assert alert.status == BatteryStatus.LOW

    def test_critical_battery_status(self, battery_manager, fresh_state):
        fresh_state.battery = 18.0
        alert = battery_manager.evaluate(fresh_state)
        assert alert.status == BatteryStatus.CRITICAL

    def test_emergency_battery_status(self, battery_manager, fresh_state):
        fresh_state.battery = 8.0
        alert = battery_manager.evaluate(fresh_state)
        assert alert.status == BatteryStatus.EMERGENCY

    def test_auto_rth_triggered_when_critical_and_airborne(self, battery_manager):
        s = DroneState()
        s.battery = 18.0
        s.in_air = True
        s.altitude = 30.0
        s.mode = FlightMode.HOVERING
        alert = battery_manager.evaluate(s)
        assert alert.should_auto_rth is True

    def test_auto_rth_not_triggered_on_ground(self, battery_manager):
        s = DroneState()
        s.battery = 18.0
        s.in_air = False
        alert = battery_manager.evaluate(s)
        assert alert.should_auto_rth is False

    def test_alert_has_remaining_seconds(self, battery_manager, airborne_state):
        alert = battery_manager.evaluate(airborne_state)
        assert alert.remaining_flight_seconds >= 0

    def test_alert_to_dict(self, battery_manager, fresh_state):
        alert = battery_manager.evaluate(fresh_state)
        d = alert.to_dict()
        assert "status" in d
        assert "battery_percent" in d
        assert "remaining_flight_minutes" in d

    def test_can_reach_destination_nearby(self, battery_manager, airborne_state):
        ok, msg = battery_manager.can_reach_destination(airborne_state, 20, 20, 30)
        assert ok is True

    def test_can_reach_destination_too_far(self, battery_manager):
        s = DroneState()
        s.battery = 22.0
        s.in_air = True
        ok, msg = battery_manager.can_reach_destination(s, 10000, 10000, 30)
        assert ok is False

    def test_format_for_display_contains_status(self, battery_manager, fresh_state):
        alert = battery_manager.evaluate(fresh_state)
        display = alert.format_for_display()
        assert "NORMAL" in display or "BATARYA" in display


class TestMissionPlanner:
    """MissionPlanner testleri."""

    def test_valid_mission_created(self, mission_planner, fresh_state):
        """Gecerli tekli kalkis gorevi olusturulabilmeli."""
        steps = [
            {"action": "takeoff", "parameters": {"target_altitude": 30.0}},
            {"action": "get_telemetry", "parameters": {}},
        ]
        mission, err = mission_planner.create_mission("Test", steps, fresh_state)
        assert err == ""
        assert mission is not None

    def test_mission_has_correct_steps(self, mission_planner, fresh_state):
        steps = [
            {"action": "takeoff", "parameters": {"target_altitude": 30.0}},
            {"action": "get_telemetry", "parameters": {}},
        ]
        mission, _ = mission_planner.create_mission("Test", steps, fresh_state)
        assert mission.total_steps == 2

    def test_mission_id_generated(self, mission_planner, fresh_state):
        steps = [{"action": "takeoff", "parameters": {"target_altitude": 30.0}}]
        mission, _ = mission_planner.create_mission("Test", steps, fresh_state)
        assert mission.mission_id.startswith("MSN-")

    def test_invalid_mission_detected(self, mission_planner, fresh_state):
        """Yerde RTH komutuyla baslayan gorev reddedilmeli."""
        steps = [
            {"action": "return_to_home", "parameters": {}},
        ]
        # Drone yerde, RTH gecersiz (SR-FLT-002)
        mission, err = mission_planner.create_mission("Hatali", steps, fresh_state)
        assert mission is None
        assert len(err) > 0

    def test_empty_steps_returns_error(self, mission_planner, fresh_state):
        mission, err = mission_planner.create_mission("Bos", [], fresh_state)
        assert mission is None
        assert len(err) > 0

    def test_mission_progress_starts_zero(self, mission_planner, fresh_state):
        steps = [{"action": "takeoff", "parameters": {"target_altitude": 30.0}}]
        mission, _ = mission_planner.create_mission("Test", steps, fresh_state)
        assert mission.completed_steps == 0
        assert mission.progress_percent == pytest.approx(0.0)

    def test_mission_to_dict(self, mission_planner, fresh_state):
        steps = [{"action": "takeoff", "parameters": {"target_altitude": 30.0}}]
        mission, _ = mission_planner.create_mission("Test", steps, fresh_state)
        d = mission.to_dict()
        assert "mission_id" in d
        assert "steps" in d
        assert "status" in d
