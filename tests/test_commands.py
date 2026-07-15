"""
Test Grubu 5: Komut Parser ve Entegrasyon Testleri
===================================================
CommandParser ve ExecutionResult entegrasyon testleri.
Ollama bağlantısı gerektirmez — sahte ParsedCommand kullanır.
"""

import pytest
from src.agent.command_parser import CommandParser, ExecutionResult
from src.agent.llm_client import ParsedCommand
from src.tools.drone_tools import DroneTools
from src.safety.validator import SafetyValidator
from src.simulation.drone import DroneState


def make_cmd(action, **kwargs) -> ParsedCommand:
    """Test için sahte ParsedCommand üreteci."""
    params = {k: v for k, v in kwargs.items()}
    return ParsedCommand(
        action=action,
        parameters=params,
        reasoning=f"Test komutu: {action}",
        confidence=0.99,
    )


@pytest.fixture
def parser(drone_tools, validator):
    return CommandParser(drone_tools, validator)


@pytest.fixture
def airborne_parser(airborne_tools, validator):
    return CommandParser(airborne_tools, validator)


class TestCommandParserClarify:
    def test_clarify_returns_not_success(self, parser):
        cmd = ParsedCommand(
            action="clarify",
            parameters={},
            reasoning="Belirsiz komut",
            confidence=0.9,
            needs_clarification=True,
            clarification_question="Ne yapmamı istiyorsunuz?",
        )
        result = parser.execute("biraz yüksel", cmd)
        assert result.success is False
        assert "Açıklama" in result.final_message or "?" in result.final_message

    def test_reject_returns_not_success(self, parser):
        cmd = make_cmd("reject")
        result = parser.execute("hava durumu nedir", cmd)
        assert result.success is False


class TestCommandParserTakeoff:
    def test_valid_takeoff_executes(self, parser):
        cmd = make_cmd("takeoff", target_altitude=30.0)
        result = parser.execute("30m kalk", cmd)
        assert result.success is True

    def test_takeoff_updates_state(self, parser):
        cmd = make_cmd("takeoff", target_altitude=50.0)
        parser.execute("50m kalk", cmd)
        assert parser.state.altitude == pytest.approx(50.0)

    def test_invalid_altitude_safety_rejected(self, parser):
        cmd = make_cmd("takeoff", target_altitude=5000.0)
        result = parser.execute("5000m kalk", cmd)
        assert result.success is False
        assert result.validation is not None
        assert not result.validation.is_valid

    def test_takeoff_when_airborne_translates_to_goto(self, airborne_parser):
        cmd = make_cmd("takeoff", target_altitude=80.0)
        result = airborne_parser.execute("tekrar kalk", cmd)
        assert result.success is True
        assert result.parsed_command.action == "go_to"
        assert result.parsed_command.parameters["altitude"] == 80.0


class TestCommandParserLand:
    def test_valid_land_executes(self, airborne_parser):
        cmd = make_cmd("land")
        result = airborne_parser.execute("in", cmd)
        assert result.success is True

    def test_land_on_ground_safety_rejected(self, parser):
        cmd = make_cmd("land")
        result = parser.execute("in", cmd)
        assert result.success is False


class TestCommandParserGoTo:
    def test_valid_goto_executes(self, airborne_parser):
        cmd = make_cmd("go_to", x=50.0, y=50.0, altitude=30.0)
        result = airborne_parser.execute("50,50 git", cmd)
        assert result.success is True

    def test_goto_outside_geofence_rejected(self, airborne_parser):
        cmd = make_cmd("go_to", x=9999.0, y=0.0, altitude=30.0)
        result = airborne_parser.execute("çok uzağa git", cmd)
        assert result.success is False

    def test_goto_on_ground_rejected(self, parser):
        cmd = make_cmd("go_to", x=50.0, y=50.0, altitude=30.0)
        result = parser.execute("50,50 git", cmd)
        assert result.success is False

    def test_goto_defaults_coordinates_to_current_state(self, airborne_parser):
        # Set drone state current coordinates to something non-zero
        airborne_parser.state.x = 42.0
        airborne_parser.state.y = 84.0
        # Send go_to with only altitude parameter
        cmd = make_cmd("go_to", altitude=50.0)
        result = airborne_parser.execute("50m yüksel", cmd)
        assert result.success is True
        assert airborne_parser.state.x == 42.0
        assert airborne_parser.state.y == 84.0
        assert airborne_parser.state.altitude == 50.0

    def test_relative_altitude_change_takeoff(self, parser):
        # Drone initially on ground, alt=0.0
        assert parser.state.altitude == 0.0
        cmd = make_cmd("takeoff", altitude_change=15.0)
        result = parser.execute("15m yüksel", cmd)
        assert result.success is True
        assert parser.state.altitude == 15.0

    def test_relative_altitude_change_goto(self, airborne_parser):
        # Airborne parser initially at alt=30.0 (default in airborne_parser fixture)
        initial_alt = airborne_parser.state.altitude
        cmd = make_cmd("go_to", altitude_change=20.0)
        result = airborne_parser.execute("20m daha yüksel", cmd)
        assert result.success is True
        assert airborne_parser.state.altitude == initial_alt + 20.0


class TestCommandParserRTH:
    def test_rth_executes_when_airborne(self, airborne_parser):
        cmd = make_cmd("return_to_home")
        result = airborne_parser.execute("eve dön", cmd)
        assert result.success is True

    def test_rth_on_ground_rejected(self, parser):
        cmd = make_cmd("return_to_home")
        result = parser.execute("eve dön", cmd)
        assert result.success is False


class TestCommandParserTelemetry:
    def test_telemetry_always_succeeds(self, parser):
        cmd = make_cmd("get_telemetry")
        result = parser.execute("durum", cmd)
        assert result.success is True

    def test_telemetry_does_not_need_validation(self, airborne_parser):
        """Telemetri güvenlik doğrulamasına takılmamalı."""
        cmd = make_cmd("get_telemetry")
        result = airborne_parser.execute("durum", cmd)
        assert result.success is True


class TestExecutionResultStructure:
    def test_result_has_to_dict(self, parser):
        cmd = make_cmd("get_telemetry")
        result = parser.execute("durum", cmd)
        d = result.to_dict()
        assert "user_input" in d
        assert "action" in d
        assert "success" in d

    def test_result_captures_user_input(self, parser):
        cmd = make_cmd("get_telemetry")
        result = parser.execute("benim komutum", cmd)
        assert result.user_input == "benim komutum"


class TestCommandParserCriticalConfirmation:
    def test_critical_action_initially_rejected_demanding_confirmation(self, airborne_parser):
        """Kritik işlem ilk seferde teyit uyarısıyla engellenmeli."""
        cmd = make_cmd("motor_stop")
        result = airborne_parser.execute("motorları durdur", cmd)
        assert result.success is False
        assert "GÜVENLİK UYARISI" in result.final_message
        assert "devam etmek için" in result.final_message.lower()
        # parser içinde pending critical action kurulmalı
        assert airborne_parser._pending_critical_action == cmd

    def test_critical_action_executes_after_confirmation(self, airborne_parser):
        """Kritik işlem teyit edildiğinde çalışmalı."""
        cmd = make_cmd("motor_stop")
        # İlk komut: uyarı verir
        airborne_parser.execute("motorları durdur", cmd)
        # İkinci komut: 'evet' gelince yürütür
        result = airborne_parser.execute("evet", cmd)
        assert result.success is True
        assert "TEYİT EDİLDİ" in result.final_message
        assert airborne_parser._pending_critical_action is None
        assert airborne_parser.state.in_air is False

    def test_critical_action_cancelled_on_other_command(self, airborne_parser):
        """Başka bir komut gelince kritik işlem teyidi iptal edilmeli."""
        cmd_stop = make_cmd("motor_stop")
        airborne_parser.execute("motorları durdur", cmd_stop)
        
        # Araya başka bir komut giriyor
        cmd_telemetry = make_cmd("get_telemetry")
        airborne_parser.execute("durum nedir", cmd_telemetry)
        
        assert airborne_parser._pending_critical_action is None

    def test_substring_not_matched_as_confirmation(self, airborne_parser):
        """Metni 'y' veya 'onay' kelimesinin alt dizisini içeren alakasız komutlar teyit olarak algılanmamalı."""
        cmd_stop = make_cmd("motor_stop")
        airborne_parser.execute("motorları durdur", cmd_stop)
        assert airborne_parser._pending_critical_action == cmd_stop

        # "metreye" kelimesinde "y" harfi bulunur, ancak teyit olmamalıdır
        cmd_takeoff = make_cmd("takeoff", target_altitude=30.0)
        result = airborne_parser.execute("30 metreye kalk", cmd_takeoff)
        assert result.success is True
        assert airborne_parser._pending_critical_action is None  # Yeni alakasız komut teyidi sıfırladı

