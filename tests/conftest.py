"""
IHA Pilot Asistanı — pytest Konfigürasyonu ve Paylaşılan Fixtures
=================================================================

Bu modül, tüm test dosyalarının kullandığı ortak fixture'ları tanımlar.
Her test, birbirinden bağımsız taze nesne alır (test izolasyonu).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.simulation.drone import DroneState, FlightMode
from src.simulation.environment import PhysicsEngine
from src.simulation.telemetry import TelemetryReader
from src.tools.drone_tools import DroneTools
from src.safety.validator import SafetyValidator
from src.safety.rules import SAFETY_RULES
from src.battery.manager import BatteryManager
from src.mission.planner import MissionPlanner
from config.settings import settings


# ── Temel Fixture'lar ──────────────────────────────────────────────────────

@pytest.fixture
def fresh_state() -> DroneState:
    """Taze, sıfırlanmış drone durumu."""
    return DroneState()


@pytest.fixture
def airborne_state() -> DroneState:
    """Havada, 50m irtifada, %80 bataryada drone."""
    s = DroneState()
    s.altitude = 50.0
    s.in_air = True
    s.mode = FlightMode.HOVERING
    s.battery = 80.0
    return s


@pytest.fixture
def low_battery_state() -> DroneState:
    """Düşük bataryalı, havada drone (%25)."""
    s = DroneState()
    s.altitude = 40.0
    s.in_air = True
    s.mode = FlightMode.HOVERING
    s.battery = 25.0
    return s


@pytest.fixture
def critical_battery_state() -> DroneState:
    """Kritik bataryalı, havada drone (%18)."""
    s = DroneState()
    s.altitude = 40.0
    s.in_air = True
    s.mode = FlightMode.HOVERING
    s.battery = 18.0
    return s


@pytest.fixture
def drone_tools(fresh_state) -> DroneTools:
    """Taze state ile DroneTools örneği."""
    return DroneTools(fresh_state)


@pytest.fixture
def airborne_tools(airborne_state) -> DroneTools:
    """Havada drone için DroneTools."""
    return DroneTools(airborne_state)


@pytest.fixture
def validator() -> SafetyValidator:
    """Taze SafetyValidator örneği."""
    return SafetyValidator()


@pytest.fixture
def battery_manager() -> BatteryManager:
    """Taze BatteryManager örneği."""
    return BatteryManager()


@pytest.fixture
def mission_planner() -> MissionPlanner:
    """Taze MissionPlanner örneği."""
    return MissionPlanner()
