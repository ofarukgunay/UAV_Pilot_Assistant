"""
IHA Pilot Asistanı — Komut Ayrıştırıcı ve Eylem Yönlendiricisi
===============================================================

Bu modül, LLM'den alınan ParsedCommand'ı alır ve uygun araç
fonksiyonunu çağıran köprü katmanı görevi görür.

Mimari Akış:
    Kullanıcı Girişi
        ↓
    OllamaClient.process() → ParsedCommand
        ↓
    CommandParser.execute() ← BU MODÜL
        ↓
    SafetyValidator.validate()
        ↓
    DroneTools.<action>()
        ↓
    ToolResult → Kullanıcıya göster

Tasarım Prensibi (Açıklanabilirlik):
    Her eylem geçişi loglanır ve terminalda gösterilir.
    "Ne oldu, neden oldu, sonuç ne?" soruları her zaman yanıtlanır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.agent.llm_client import ParsedCommand
from src.safety.validator import SafetyValidator, ValidationResult
from src.tools.drone_tools import DroneTools, ToolResult
from src.simulation.drone import DroneState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Komut Yürütme Sonuç Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class ExecutionResult:
    """
    Bir komutun tam yürütme sonucu.

    Bu nesne loglama, web API ve terminal çıktısı için kullanılır.

    Attributes:
        user_input (str): Orijinal kullanıcı komutu.
        parsed_command (ParsedCommand): LLM'in ürettiği komut.
        validation (Optional[ValidationResult]): Güvenlik doğrulama sonucu.
        tool_result (Optional[ToolResult]): Araç fonksiyonu sonucu.
        final_message (str): Kullanıcıya gösterilecek son mesaj.
        success (bool): Komut başarıyla yürütüldü mü?
    """
    user_input: str
    parsed_command: ParsedCommand
    validation: Optional[ValidationResult] = None
    tool_result: Optional[ToolResult] = None
    final_message: str = ""
    success: bool = False

    def to_dict(self) -> dict:
        return {
            "user_input": self.user_input,
            "action": self.parsed_command.action,
            "parameters": self.parsed_command.parameters,
            "reasoning": self.parsed_command.reasoning,
            "confidence": self.parsed_command.confidence,
            "safety_valid": self.validation.is_valid if self.validation else None,
            "safety_rule_violated": (
                self.validation.rule_violated if self.validation else None
            ),
            "tool_success": self.tool_result.success if self.tool_result else None,
            "final_message": self.final_message,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Ana Komut Ayrıştırıcı
# ---------------------------------------------------------------------------
class CommandParser:
    """
    ParsedCommand → Güvenlik Doğrulama → Araç Fonksiyonu zincirini yönetir.

    Bu sınıf sistemin orkestratörüdür:
        - Güvenlik katmanını çağırır
        - Doğrulama sonucuna göre araçları aktive eder
        - Her adımı loglar ve gösterir
        - Kullanıcıya anlaşılır yanıt üretir

    Usage::
        parser = CommandParser(drone_tools, safety_validator)
        result = parser.execute("50m kalk", parsed_cmd)
    """

    def __init__(
        self,
        tools: DroneTools,
        validator: SafetyValidator,
    ) -> None:
        self._tools = tools
        self._validator = validator

    @property
    def state(self) -> DroneState:
        return self._tools.state

    def execute(
        self,
        user_input: str,
        cmd: ParsedCommand,
    ) -> ExecutionResult:
        """
        Ayrıştırılmış komutu güvenlik kontrolünden geçirip uygula.

        Args:
            user_input: Orijinal kullanıcı metni.
            cmd: LLM'den gelen ayrıştırılmış komut.

        Returns:
            ExecutionResult: Tam yürütme sonucu.
        """
        # ── Özel durumlar: clarify / reject ──────────────────────────────
        if cmd.action == "clarify":
            return ExecutionResult(
                user_input=user_input,
                parsed_command=cmd,
                final_message=(
                    f"🔍 Açıklama gerekiyor\n"
                    f"   {cmd.clarification_question}"
                ),
                success=False,
            )

        if cmd.action == "reject":
            return ExecutionResult(
                user_input=user_input,
                parsed_command=cmd,
                final_message=(
                    f"❌ Komut reddedildi\n"
                    f"   Gerekçe: {cmd.reasoning}"
                ),
                success=False,
            )

        # ── Güvenlik Doğrulaması ─────────────────────────────────────────
        validation = self._validator.validate(
            cmd.action,
            cmd.parameters,
            self._tools.state,
        )
        logger.info(
            "Güvenlik doğrulama: action=%s valid=%s rule=%s",
            cmd.action,
            validation.is_valid,
            validation.rule_violated,
        )

        if not validation.is_valid:
            return ExecutionResult(
                user_input=user_input,
                parsed_command=cmd,
                validation=validation,
                final_message=validation.format_for_user(),
                success=False,
            )

        # ── Araç Fonksiyonu Çağrısı ──────────────────────────────────────
        tool_result = self._dispatch(cmd)

        final_msg = (
            tool_result.message
            if tool_result
            else "Komut işlendi."
        )

        return ExecutionResult(
            user_input=user_input,
            parsed_command=cmd,
            validation=validation,
            tool_result=tool_result,
            final_message=final_msg,
            success=tool_result.success if tool_result else False,
        )

    def _dispatch(self, cmd: ParsedCommand) -> Optional[ToolResult]:
        """
        Eylem adına göre doğru araç fonksiyonunu çağır.

        Args:
            cmd: Doğrulanmış ParsedCommand.

        Returns:
            ToolResult veya None.
        """
        p = cmd.parameters

        dispatch_map = {
            "get_telemetry": lambda: self._tools.get_telemetry(),
            "takeoff": lambda: self._tools.takeoff(
                float(p.get("target_altitude", 30.0))
            ),
            "land": lambda: self._tools.land(),
            "return_to_home": lambda: self._tools.return_to_home(),
            "go_to": lambda: self._tools.go_to(
                float(p.get("x", 0.0)),
                float(p.get("y", 0.0)),
                float(p.get("altitude", self._tools.state.altitude)),
            ),
        }

        handler = dispatch_map.get(cmd.action)
        if handler:
            try:
                return handler()
            except Exception as exc:
                logger.exception("Araç fonksiyonu hatası: %s", cmd.action)
                # Güvenli başarısızlık: exception fırlatmadan hata döndür
                from src.tools.drone_tools import ToolResult
                return ToolResult(
                    success=False,
                    action=cmd.action,
                    message=f"Araç hatası ({cmd.action}): {exc}",
                    state_before=self._tools.state.clone(),
                    state_after=self._tools.state.clone(),
                )

        logger.warning("Bilinmeyen eylem dispatch'e geldi: %s", cmd.action)
        return None
