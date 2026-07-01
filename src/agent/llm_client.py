"""
IHA Pilot Asistanı — Ollama LLM İstemcisi
==========================================

Bu modül, Ollama yerel LLM sunucusuyla HTTP üzerinden iletişim kurar
ve ham model yanıtını yapılandırılmış komuta dönüştürür.

Ollama API Referansı:
    POST http://localhost:11434/api/generate
    Body: {
        "model"  : "llama3",
        "prompt" : "<tam prompt>",
        "format" : "json",      ← JSON modu: geçerli JSON üretmesi zorunlu
        "stream" : false,
        "options": {"temperature": 0.1}
    }

Hata Yönetimi Stratejisi (Graceful Degradation):
    1. Ollama bağlantı hatası → Açık hata mesajı + bağlantı rehberi
    2. JSON parse hatası      → Ham yanıtı logla + varsayılan 'clarify' döndür
    3. Bilinmeyen eylem       → 'reject' ile güvenli geri dön
    4. Timeout               → Zaman aşımı mesajı + tekrar deneme önerisi

Demo/Sunum Notu:
    LLM'in düşünce süreci ('reasoning') terminalda renkli olarak gösterilir.
    Bu, demo videosunda 'yapay zeka ne düşünüyor?' sorusunu görsel yanıtlar.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

from src.agent.prompts import build_system_prompt, build_user_message
from src.simulation.telemetry import TelemetryReader
from src.simulation.drone import DroneState
from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ayrıştırılmış LLM Komutu Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class ParsedCommand:
    """
    LLM'den alınan ve doğrulanmış komut yapısı.

    Bu nesne, güvenlik katmanına ve araç fonksiyonlarına iletilir.

    Attributes:
        action (str): Seçilen eylem adı.
        parameters (dict): Eylem parametreleri.
        reasoning (str): LLM'in karar gerekçesi (Türkçe açıklama).
        confidence (float): Modelin güven skoru (0.0–1.0).
        needs_clarification (bool): Kullanıcıdan bilgi gerekiyor mu?
        clarification_question (str): Sorulacak netleştirme sorusu.
        safety_note (str): LLM'in güvenlik notu.
        is_mission (bool): Bu bir çok adımlı görev mi?
        mission_steps (list): Görev adımları (plan_mission ise).
        raw_response (str): Ham LLM yanıtı (debug için).
        processing_time_ms (float): LLM işlem süresi (milisaniye).
    """
    action: str
    parameters: Dict[str, Any]
    reasoning: str
    confidence: float
    needs_clarification: bool = False
    clarification_question: str = ""
    safety_note: str = ""
    is_mission: bool = False
    mission_steps: list = field(default_factory=list)
    raw_response: str = ""
    processing_time_ms: float = 0.0

    # Geçerli eylemler
    VALID_ACTIONS = frozenset({
        "get_telemetry", "takeoff", "land",
        "return_to_home", "go_to",
        "plan_mission", "clarify", "reject",
    })

    @property
    def is_valid_action(self) -> bool:
        return self.action in self.VALID_ACTIONS

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "parameters": self.parameters,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "safety_note": self.safety_note,
            "is_mission": self.is_mission,
            "mission_steps_count": len(self.mission_steps),
            "processing_time_ms": round(self.processing_time_ms, 1),
        }

    def format_for_display(self) -> str:
        """Demo video için terminal çıktısı — LLM düşünce süreci."""
        lines = [
            "┌─────────────────────────────────────────┐",
            "│         🤖 LLM ANALİZ SONUCU           │",
            "└─────────────────────────────────────────┘",
            f"  Eylem      : {self.action.upper()}",
        ]
        if self.parameters:
            lines.append(f"  Parametreler: {self.parameters}")
        lines += [
            f"  Güven Skoru : %{self.confidence * 100:.0f}",
            f"  İşlem Süresi: {self.processing_time_ms:.0f}ms",
            "  ─────────────────────────────────────────",
            f"  💭 Gerekçe: {self.reasoning}",
        ]
        if self.safety_note:
            lines.append(f"  ⚠️  Güvenlik: {self.safety_note}")
        if self.needs_clarification:
            lines.append(f"  ❓ Soru: {self.clarification_question}")
        if self.is_mission:
            lines.append(f"  📋 Görev Adımları: {len(self.mission_steps)} adım")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback Komutlar
# ---------------------------------------------------------------------------
def _fallback_clarify(reason: str) -> ParsedCommand:
    """LLM hatası veya parse başarısızlığı için güvenli varsayılan."""
    return ParsedCommand(
        action="clarify",
        parameters={},
        reasoning=f"LLM yanıtı işlenemedi: {reason}. Güvenli varsayılan: açıklama iste.",
        confidence=0.0,
        needs_clarification=True,
        clarification_question="Komutunuzu daha açık ifade eder misiniz?",
    )


# ---------------------------------------------------------------------------
# Ollama LLM İstemcisi
# ---------------------------------------------------------------------------
class OllamaClient:
    """
    Ollama yerel LLM sunucusu ile iletişim kuran istemci sınıfı.

    Bu sınıf:
        1. DroneState'i LLM bağlamına dönüştürür
        2. System + User prompt oluşturur
        3. Ollama API'sine HTTP POST gönderir
        4. JSON yanıtı ayrıştırır ve doğrular

    Usage::
        client = OllamaClient()
        cmd = client.process("10 metreye kalk", drone_state)
        print(cmd.format_for_display())
    """

    def __init__(self) -> None:
        cfg = settings.llm
        self.base_url = cfg.OLLAMA_BASE_URL
        self.model = cfg.OLLAMA_MODEL
        self.timeout = cfg.OLLAMA_TIMEOUT
        self.temperature = cfg.TEMPERATURE
        self._session = requests.Session()

    def check_connection(self) -> tuple[bool, str]:
        """
        Ollama sunucusuna bağlantıyı kontrol et.

        Returns:
            tuple[bool, str]: (bağlı mı, durum mesajı)
        """
        try:
            resp = self._session.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                if self.model in models or any(self.model in m for m in models):
                    return True, f"Ollama bağlantısı OK — Model: {self.model}"
                else:
                    available = ", ".join(models) if models else "hiç model yok"
                    return False, (
                        f"'{self.model}' modeli bulunamadı. "
                        f"Mevcut modeller: {available}. "
                        f"Kurmak için: ollama pull {self.model}"
                    )
            return False, f"Ollama API hatası: HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, (
                f"Ollama sunucusuna bağlanılamadı ({self.base_url}). "
                f"Başlatmak için terminale: ollama serve"
            )
        except Exception as e:
            return False, f"Bağlantı hatası: {e}"

    def process(
        self,
        user_input: str,
        state: DroneState,
    ) -> ParsedCommand:
        """
        Kullanıcı komutunu LLM ile işle ve yapılandırılmış komuta dönüştür.

        İşlem Akışı:
            1. TelemetryReader ile drone bağlamını hazırla
            2. System + User prompt oluştur
            3. Ollama'ya HTTP POST gönder (JSON format)
            4. Yanıtı ayrıştır ve doğrula
            5. ParsedCommand döndür

        Args:
            user_input: Kullanıcının doğal dil komutu.
            state: Mevcut drone durumu.

        Returns:
            ParsedCommand: Ayrıştırılmış ve doğrulanmış komut.
        """
        reader = TelemetryReader(state)
        context = reader.get_llm_context()

        system_prompt = build_system_prompt(context)
        user_message = build_user_message(user_input)
        full_prompt = f"{system_prompt}\n\n{user_message}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": 512,
            },
        }

        start_time = time.time()
        try:
            resp = self._session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            elapsed_ms = (time.time() - start_time) * 1000

            if resp.status_code != 200:
                logger.error("Ollama HTTP hatası: %s — %s", resp.status_code, resp.text[:200])
                return _fallback_clarify(f"HTTP {resp.status_code}")

            raw_text = resp.json().get("response", "")
            logger.debug("LLM ham yanıt (%dms): %s", elapsed_ms, raw_text[:300])

            cmd = self._parse_response(raw_text, elapsed_ms)
            return cmd

        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning("Ollama zaman aşımı (%dms)", elapsed_ms)
            return _fallback_clarify(
                f"LLM zaman aşımı ({self.timeout}s). Model yükleniyor olabilir, tekrar deneyin."
            )
        except requests.exceptions.ConnectionError:
            return _fallback_clarify(
                "Ollama sunucusuna bağlanılamadı. 'ollama serve' komutunu çalıştırın."
            )
        except Exception as exc:
            logger.exception("Beklenmeyen LLM hatası")
            return _fallback_clarify(str(exc))

    def _parse_response(self, raw: str, elapsed_ms: float) -> ParsedCommand:
        """
        Ollama'dan gelen ham JSON yanıtını ParsedCommand'a dönüştür.

        Args:
            raw: Ham JSON string.
            elapsed_ms: İşlem süresi (loglama için).

        Returns:
            ParsedCommand: Ayrıştırılmış komut veya güvenli fallback.
        """
        raw = raw.strip()
        if not raw:
            return _fallback_clarify("Boş LLM yanıtı")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("JSON ayrıştırma hatası: %s | Ham: %s", e, raw[:200])
            return _fallback_clarify(f"Geçersiz JSON: {e}")

        action = data.get("action", "clarify")
        parameters = data.get("parameters", {})
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.5))
        needs_clarification = bool(data.get("needs_clarification", False))
        clarification_question = data.get("clarification_question", "")
        safety_note = data.get("safety_note", "")

        # Plan mission özel işleme
        is_mission = action == "plan_mission"
        mission_steps = []
        if is_mission:
            mission_steps = parameters.get("steps", [])

        # Bilinmeyen eylem → güvenli reject
        if action not in ParsedCommand.VALID_ACTIONS:
            logger.warning("Bilinmeyen LLM eylemi: '%s' → reject'e çevriliyor", action)
            return ParsedCommand(
                action="reject",
                parameters={},
                reasoning=f"LLM bilinmeyen eylem üretti ('{action}'). Güvenli redde çevrildi.",
                confidence=0.1,
                raw_response=raw,
                processing_time_ms=elapsed_ms,
            )

        return ParsedCommand(
            action=action,
            parameters=parameters,
            reasoning=reasoning,
            confidence=confidence,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            safety_note=safety_note,
            is_mission=is_mission,
            mission_steps=mission_steps,
            raw_response=raw,
            processing_time_ms=elapsed_ms,
        )
