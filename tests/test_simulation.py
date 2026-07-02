"""
Test Grubu 1: Fizik Simülasyonu
================================
DroneState, PhysicsEngine ve TelemetryReader birim testleri.
"""

import pytest
from src.simulation.drone import DroneState, FlightMode
from src.simulation.environment import PhysicsEngine
from src.simulation.telemetry import TelemetryReader


class TestDroneState:
    """DroneState veri sınıfı testleri."""

    def test_initial_state_is_on_ground(self, fresh_state):
        assert fresh_state.in_air is False
        assert fresh_state.altitude == 0.0
        assert fresh_state.mode == FlightMode.IDLE

    def test_initial_battery_is_full(self, fresh_state):
        assert fresh_state.battery == 100.0

    def test_clone_independence(self, fresh_state):
        """Clone değiştirmek orijinali etkilememeli."""
        clone = fresh_state.clone()
        clone.altitude = 999.0
        clone.battery = 1.0
        assert fresh_state.altitude == 0.0
        assert fresh_state.battery == 100.0

    def test_distance_to_home_when_at_home(self, fresh_state):
        assert fresh_state.distance_to_home_2d == pytest.approx(0.0)

    def test_distance_to_home_after_move(self, fresh_state):
        fresh_state.x = 30.0
        fresh_state.y = 40.0
        assert fresh_state.distance_to_home_2d == pytest.approx(50.0)

    def test_to_dict_has_required_keys(self, fresh_state):
        d = fresh_state.to_dict()
        assert "position" in d
        assert "kinematics" in d
        assert "status" in d
        assert "home" in d

    def test_to_dict_position_keys(self, fresh_state):
        pos = fresh_state.to_dict()["position"]
        assert "x" in pos
        assert "y" in pos
        assert "altitude" in pos


class TestPhysicsEngine:
    """PhysicsEngine birim testleri."""

    def test_tick_interval_positive(self):
        engine = PhysicsEngine()
        assert engine.tick_interval > 0

    def test_tick_returns_drone_state(self, fresh_state):
        """PhysicsEngine hover simülasıyonƒ DroneState döndürür."""
        engine = PhysicsEngine()
        fresh_state.in_air = True
        fresh_state.altitude = 30.0
        result = engine.simulate_hover(fresh_state, dt=0.1)
        assert isinstance(result, DroneState)

    def test_battery_drains_over_time(self, airborne_state):
        """Havada beklerken batarya azalmalı."""
        engine = PhysicsEngine()
        initial_bat = airborne_state.battery
        state = airborne_state
        for _ in range(10):
            state = engine.simulate_hover(state, dt=1.0)
        assert state.battery < initial_bat

    def test_battery_stays_non_negative(self, airborne_state):
        """Batarya 0'ın altına düşmemeli."""
        airborne_state.battery = 0.1
        engine = PhysicsEngine()
        state = airborne_state
        for _ in range(100):
            state = engine.simulate_hover(state, dt=1.0)
        assert state.battery >= 0.0


class TestTelemetryReader:
    """TelemetryReader birim testleri."""

    def test_concise_format_not_empty(self, fresh_state):
        reader = TelemetryReader(fresh_state)
        concise = reader.get_concise()
        assert len(concise) > 0
        assert "IDLE" in concise

    def test_human_readable_contains_altitude(self, airborne_state):
        reader = TelemetryReader(airborne_state)
        report = reader.get_human_readable()
        assert "50" in report or "irtifa" in report.lower()

    def test_llm_context_is_string(self, fresh_state):
        reader = TelemetryReader(fresh_state)
        ctx = reader.get_llm_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 50

    def test_raw_data_has_state(self, fresh_state):
        reader = TelemetryReader(fresh_state)
        raw = reader.get_raw()
        assert "position" in raw or "status" in raw

    def test_flight_estimate_returns_dict(self, airborne_state):
        reader = TelemetryReader(airborne_state)
        estimate = reader.estimate_flight_remaining()
        assert isinstance(estimate, dict)
        assert len(estimate) > 0
