"""
IHA Pilot Asistanı — Çok Adımlı Görev Planlayıcı (Özgün Özellik #2)
=====================================================================

Bu modül, LLM tarafından üretilen çok adımlı görev planlarını
yapılandırılmış görev nesnelerine dönüştürür ve doğrular.

Görev Planlama Prensibi:
    Kullanıcı tek bir doğal dil cümlesiyle çok adımlı görev tanımlayabilir.
    Örnek: "Kalk, 100m doğuya git, durum bildir, eve dön"
    LLM bu cümleyi 4 adımlı görev planına çevirir.
    Bu plan, güvenlik kontrolünden geçirilip sırayla yürütülür.

Görev Durumu Makinesi:
    PENDING → RUNNING → COMPLETED
                     → FAILED (hata veya güvenlik reddi)
                     → ABORTED (kullanıcı iptali)

Demo/Sunum Notu:
    Görev yürütme sırasında her adım için "Adım X/N" göstergesi
    çıkar. Bu, demo videosunda görev zincirinin nasıl işlediğini
    açıkça gösterir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.safety.validator import SafetyValidator
from src.simulation.drone import DroneState


# ---------------------------------------------------------------------------
# Görev Adımı Durumu
# ---------------------------------------------------------------------------
class StepStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

    @property
    def icon(self) -> str:
        icons = {
            "PENDING": "⏳",
            "RUNNING": "▶️",
            "COMPLETED": "✅",
            "FAILED": "❌",
            "SKIPPED": "⏭️",
        }
        return icons.get(self.value, "❓")


# ---------------------------------------------------------------------------
# Görev Durumu
# ---------------------------------------------------------------------------
class MissionStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


# ---------------------------------------------------------------------------
# Görev Adımı Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class MissionStep:
    """
    Tek bir görev adımını temsil eder.

    Attributes:
        step_index (int): Adım sırası (0'dan başlar).
        action (str): Eylem adı.
        parameters (dict): Eylem parametreleri.
        status (StepStatus): Mevcut adım durumu.
        result_message (str): Adım sonuç mesajı.
        started_at (Optional[float]): Başlangıç zaman damgası.
        completed_at (Optional[float]): Bitiş zaman damgası.
    """
    step_index: int
    action: str
    parameters: Dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    result_message: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration_s(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return round(self.completed_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "parameters": self.parameters,
            "status": self.status.value,
            "result_message": self.result_message,
            "duration_s": self.duration_s,
        }

    def format_for_display(self) -> str:
        return (
            f"  {self.status.icon} Adım {self.step_index + 1}: "
            f"{self.action.upper()} {self.parameters or ''}"
            + (f" → {self.result_message}" if self.result_message else "")
        )


# ---------------------------------------------------------------------------
# Görev Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class Mission:
    """
    Tam görev tanımı ve yürütme durumu.

    Attributes:
        mission_id (str): Benzersiz görev kimliği.
        name (str): Görev adı.
        steps (list[MissionStep]): Sıralı adım listesi.
        status (MissionStatus): Görev genel durumu.
        created_at (float): Oluşturma zaman damgası.
        started_at (Optional[float]): Yürütme başlangıcı.
        completed_at (Optional[float]): Tamamlanma zamanı.
        abort_reason (str): İptal nedeni (varsa).
    """
    mission_id: str
    name: str
    steps: List[MissionStep]
    status: MissionStatus = MissionStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    abort_reason: str = ""

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def progress_percent(self) -> float:
        if not self.steps:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

    @property
    def current_step(self) -> Optional[MissionStep]:
        for step in self.steps:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                return step
        return None

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "name": self.name,
            "status": self.status.value,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "progress_percent": round(self.progress_percent, 1),
            "steps": [s.to_dict() for s in self.steps],
        }

    def format_for_display(self) -> str:
        """Demo video için görev durum paneli."""
        lines = [
            f"╔══════════════════════════════════════════╗",
            f"║  📋 GÖREV: {self.name[:30]:<30}  ║",
            f"║  Durum: {self.status.value:<10} | İlerleme: %{self.progress_percent:.0f}  ║",
            f"╠══════════════════════════════════════════╣",
        ]
        for step in self.steps:
            lines.append(step.format_for_display())
        lines.append(f"╚══════════════════════════════════════════╝")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Görev Planlayıcı
# ---------------------------------------------------------------------------
class MissionPlanner:
    """
    LLM çıktısından Mission nesnesi oluşturan planlayıcı.

    Bu sınıf, LLM'in plan_mission eylemiyle ürettiği steps listesini
    alıp doğrulayarak tam Mission nesnesi oluşturur.
    """

    def __init__(self) -> None:
        self._mission_counter = 0
        self._validator = SafetyValidator()

    def create_mission(
        self,
        name: str,
        raw_steps: list,
        initial_state: DroneState,
    ) -> tuple[Optional[Mission], str]:
        """
        Ham adım listesinden doğrulanmış Mission oluştur.

        Args:
            name: Görev adı.
            raw_steps: LLM'den gelen raw step listesi.
            initial_state: Mevcut drone durumu.

        Returns:
            tuple[Optional[Mission], str]: (görev veya None, hata mesajı)
        """
        if not raw_steps:
            return None, "Boş görev planı — en az 1 adım gerekli."

        self._mission_counter += 1
        mission_id = f"MSN-{self._mission_counter:04d}"

        # Adımları toplu doğrula
        commands = [
            {"action": s.get("action", ""), "parameters": s.get("parameters", {})}
            for s in raw_steps
        ]
        validation_results = self._validator.validate_batch(commands, initial_state)

        steps = []
        for i, (raw, val) in enumerate(zip(raw_steps, validation_results)):
            step = MissionStep(
                step_index=i,
                action=raw.get("action", ""),
                parameters=raw.get("parameters", {}),
            )
            if not val.is_valid:
                step.status = StepStatus.FAILED
                step.result_message = (
                    f"Planlama reddi — {val.rule_violated}: {val.violation_detail}"
                )
            steps.append(step)

        # Herhangi bir adım kritik ihlalle başarısızsa plan reddedilir
        failed = [s for s in steps if s.status == StepStatus.FAILED]
        if failed:
            fail_msg = " | ".join(s.result_message for s in failed)
            return None, f"Görev planı güvenlik kontrolünden geçemedi:\n{fail_msg}"

        mission = Mission(
            mission_id=mission_id,
            name=name,
            steps=steps,
        )
        return mission, ""
