"""
IHA Pilot Asistanı — Görev Zinciri Yürütücüsü
===============================================

Bu modül, onaylanmış bir Mission'ı adım adım yürütür.
Her adım için güvenlik kontrolü yapılır ve sonuç loglanır.

Demo/Sunum Notu:
    Yürütme sırasında her adım için terminal çıktısı üretilir.
    Bu, demo videosunda görev zincirinin adım adım ilerleyişini
    görsel olarak gösterir.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.mission.planner import Mission, MissionStep, MissionStatus, StepStatus
from src.safety.validator import SafetyValidator
from src.tools.drone_tools import DroneTools

logger = logging.getLogger(__name__)


class MissionExecutor:
    """
    Görev zincirini güvenlik kontrolüyle adım adım yürüten sınıf.

    Her adım:
        1. Güvenlik doğrulamasından geçirilir
        2. Araç fonksiyonu çağrılır
        3. Sonuç loglanır ve gösterilir
        4. Başarısızlıkta görev durdurulur

    Args:
        tools: DroneTools örneği.
        validator: SafetyValidator örneği.
        on_step_update: Her adım tamamlandığında çağrılan callback
                        (web dashboard güncellemesi için).
    """

    def __init__(
        self,
        tools: DroneTools,
        validator: SafetyValidator,
        on_step_update: Optional[Callable[[Mission, MissionStep], None]] = None,
    ) -> None:
        self._tools = tools
        self._validator = validator
        self._on_step_update = on_step_update

    def execute(self, mission: Mission) -> Mission:
        """
        Görevi sırayla yürüt.

        Args:
            mission: Yürütülecek onaylanmış görev.

        Returns:
            Mission: Güncellenmiş görev durumu.
        """
        mission.status = MissionStatus.RUNNING
        mission.started_at = time.time()

        print(mission.format_for_display())

        for step in mission.steps:
            if step.status != StepStatus.PENDING:
                continue  # Önceden başarısız veya tamamlanmış adımları atla

            step.status = StepStatus.RUNNING
            step.started_at = time.time()
            print(f"\n  ▶️  Adım {step.step_index + 1}/{mission.total_steps} çalışıyor: "
                  f"{step.action.upper()} {step.parameters or ''}")

            # Güvenlik doğrulaması
            validation = self._validator.validate(
                step.action, step.parameters, self._tools.state
            )
            if not validation.is_valid:
                step.status = StepStatus.FAILED
                step.result_message = (
                    f"Güvenlik reddi — [{validation.rule_violated}] "
                    f"{validation.violation_detail}"
                )
                step.completed_at = time.time()
                print(f"  ❌ {step.result_message}")

                if self._on_step_update:
                    self._on_step_update(mission, step)

                # Kritik hata → görevi durdur
                mission.status = MissionStatus.FAILED
                mission.abort_reason = step.result_message
                mission.completed_at = time.time()
                print(f"\n  🛑 GÖREV DURDURULDU: {mission.abort_reason}")
                return mission

            # Araç çağrısı
            result = self._dispatch_step(step)
            step.completed_at = time.time()

            if result and result.success:
                step.status = StepStatus.COMPLETED
                step.result_message = result.message
                print(f"  ✅ {result.message}")
            else:
                step.status = StepStatus.FAILED
                step.result_message = result.message if result else "Araç hatası"
                print(f"  ❌ {step.result_message}")

                if self._on_step_update:
                    self._on_step_update(mission, step)

                mission.status = MissionStatus.FAILED
                mission.abort_reason = step.result_message
                mission.completed_at = time.time()
                print(f"\n  🛑 GÖREV DURDURULDU adım {step.step_index + 1}'de başarısız.")
                return mission

            if self._on_step_update:
                self._on_step_update(mission, step)

        # Tüm adımlar tamamlandı
        mission.status = MissionStatus.COMPLETED
        mission.completed_at = time.time()
        duration = mission.completed_at - mission.started_at
        print(f"\n  🏁 GÖREV TAMAMLANDI — {mission.total_steps} adım, {duration:.1f}s")
        return mission

    def _dispatch_step(self, step: MissionStep):
        """Adım eylemine göre araç fonksiyonunu çağır."""
        p = step.parameters
        dispatch = {
            "get_telemetry": lambda: self._tools.get_telemetry(),
            "takeoff": lambda: self._tools.takeoff(float(p.get("target_altitude", 30))),
            "land": lambda: self._tools.land(),
            "return_to_home": lambda: self._tools.return_to_home(),
            "go_to": lambda: self._tools.go_to(
                float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("altitude", 30))
            ),
        }
        handler = dispatch.get(step.action)
        if handler:
            try:
                return handler()
            except Exception as exc:
                logger.exception("Adım yürütme hatası: %s", step.action)
                return None
        return None
