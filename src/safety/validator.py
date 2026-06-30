"""
IHA Pilot Asistanı — Açıklanabilir Güvenlik Doğrulayıcı
=========================================================

Bu modül, LLM agent'ından gelen komutları güvenlik kurallarına
karşı doğrular ve her kararı gerekçesiyle birlikte raporlar.

Tasarım Prensibi — Açıklanabilir Yapay Zeka (Explainable AI):
    Sistemin her güvenlik kararı kullanıcıya açıklanabilir olmalıdır.
    "Neden reddedildi?" sorusu her zaman yanıtlanabilmeli.
    Bu, geleneksel siyah kutu güvenlik sistemlerinden ayrışan temel
    tasarım tercihidir.

    Referans: EASA AI Roadmap 2.0 (2023) — Explainability Requirements
              for AI/ML systems in aviation.

Mimari:
    SafetyValidator.validate() → ValidationResult
        ↳ is_valid: bool
        ↳ reason: açıklama (neden kabul/red)
        ↳ rule_violated: ihlal edilen kural kodu
        ↳ suggestion: kullanıcıya öneri
        ↳ severity: şiddet seviyesi
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.safety.rules import SAFETY_RULES, RuleSeverity, SafetyRule
from src.simulation.drone import DroneState


# ---------------------------------------------------------------------------
# Doğrulama Sonuç Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """
    Bir güvenlik doğrulama işleminin tam sonucu.

    Attributes:
        is_valid (bool): Komut güvenli ve uygulanabilir mi?
        action (str): Doğrulanan eylem adı.
        parameters (dict): Doğrulanan parametreler.
        reason (str): Kararın gerekçesi (neden kabul/red).
        rules_checked (list[str]): Kontrol edilen kural kimlikleri.
        rule_violated (Optional[str]): İhlal edilen kural (varsa).
        violation_detail (str): İhlal ayrıntısı.
        suggestion (str): Kullanıcıya önerilen alternatif.
        severity (RuleSeverity): En yüksek ihlal şiddeti.
        legal_ref (str): İlgili yasal referans.
    """
    is_valid: bool
    action: str
    parameters: dict
    reason: str
    rules_checked: List[str] = field(default_factory=list)
    rule_violated: Optional[str] = None
    violation_detail: str = ""
    suggestion: str = ""
    severity: RuleSeverity = RuleSeverity.CAUTION
    legal_ref: str = ""

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "action": self.action,
            "parameters": self.parameters,
            "reason": self.reason,
            "rule_violated": self.rule_violated,
            "violation_detail": self.violation_detail,
            "suggestion": self.suggestion,
            "severity": self.severity.value,
            "legal_ref": self.legal_ref,
            "rules_checked_count": len(self.rules_checked),
        }

    def format_for_user(self) -> str:
        """Kullanıcıya gösterilecek okunabilir doğrulama raporu."""
        if self.is_valid:
            checked = ", ".join(self.rules_checked) if self.rules_checked else "-"
            return (
                f"✅ GÜVENLİK ONAYI\n"
                f"   Eylem    : {self.action}\n"
                f"   Durum    : Tüm güvenlik kurallarından geçti\n"
                f"   Kontroller: {checked}\n"
                f"   Gerekçe  : {self.reason}"
            )
        else:
            return (
                f"❌ GÜVENLİK REDDİ [{self.severity.value}]\n"
                f"   Eylem        : {self.action}\n"
                f"   İhlal Kuralı : {self.rule_violated}\n"
                f"   Gerekçe      : {self.violation_detail}\n"
                f"   Öneri        : {self.suggestion}\n"
                f"   Yasal Ref.   : {self.legal_ref or 'Operasyonel prosedür'}"
            )


# ---------------------------------------------------------------------------
# Ana Güvenlik Doğrulayıcı Sınıfı
# ---------------------------------------------------------------------------
class SafetyValidator:
    """
    Komutları güvenlik kurallarına karşı doğrulayan katman.

    Özellikler:
        - Her kural ayrı ayrı test edilir
        - İlk kritik ihlalde doğrulama durdurulur (fail-fast)
        - Tüm kontrol geçmişi raporlanır
        - Karar gerekçesi Türkçe olarak açıklanır

    Usage::
        validator = SafetyValidator()
        result = validator.validate("takeoff", {"target_altitude": 50}, state)
        print(result.format_for_user())
    """

    def __init__(self) -> None:
        self._rules: list[SafetyRule] = SAFETY_RULES

    def validate(
        self,
        action: str,
        parameters: dict,
        state: DroneState,
    ) -> ValidationResult:
        """
        Bir eylemi güvenlik kurallarına karşı doğrula.

        Doğrulama Stratejisi:
            1. Tüm kurallar taranır, ilgili olanlar (applies_to) filtrelenir
            2. Kritik/Error kurallar fail-fast (ilk ihlalde dur)
            3. Warning/Caution kurallar kaydedilir ama durdurulmaz
            4. Tüm kontrolleri geçen komut onaylanır

        Args:
            action: Eylem adı ('takeoff', 'land', 'go_to', vb.)
            parameters: Eylem parametreleri sözlüğü.
            state: Mevcut drone durumu.

        Returns:
            ValidationResult: Detaylı doğrulama sonucu.
        """
        checked_rule_ids: list[str] = []
        applicable_rules = [
            r for r in self._rules
            if not r.applies_to or action in r.applies_to
        ]

        for rule in applicable_rules:
            checked_rule_ids.append(rule.rule_id)
            try:
                passed, detail = rule.check(action, parameters, state)
            except Exception as exc:
                # Kural değerlendirmesinde hata → güvenli red
                return ValidationResult(
                    is_valid=False,
                    action=action,
                    parameters=parameters,
                    reason=f"Kural değerlendirme hatası: {rule.rule_id}",
                    rules_checked=checked_rule_ids,
                    rule_violated=rule.rule_id,
                    violation_detail=f"İç hata: {exc}",
                    suggestion="Lütfen parametreleri kontrol edin.",
                    severity=RuleSeverity.ERROR,
                )

            if not passed:
                return ValidationResult(
                    is_valid=False,
                    action=action,
                    parameters=parameters,
                    reason=f"Kural ihlali: {rule.name} ({rule.rule_id})",
                    rules_checked=checked_rule_ids,
                    rule_violated=rule.rule_id,
                    violation_detail=detail,
                    suggestion=rule.suggestion,
                    severity=rule.severity,
                    legal_ref=rule.legal_ref,
                )

        # Tüm kurallar geçti → ONAY
        return ValidationResult(
            is_valid=True,
            action=action,
            parameters=parameters,
            reason=(
                f"'{action}' eylemi {len(checked_rule_ids)} güvenlik kuralından geçti."
            ),
            rules_checked=checked_rule_ids,
            severity=RuleSeverity.CAUTION,
        )

    def validate_batch(
        self,
        commands: list[dict],
        state: DroneState,
    ) -> list[ValidationResult]:
        """
        Çoklu komut listesini toplu doğrula (görev planlama için).

        Args:
            commands: [{"action": str, "parameters": dict}, ...] listesi.
            state: Başlangıç drone durumu.

        Returns:
            list[ValidationResult]: Her komut için doğrulama sonucu.
        """
        results = []
        for cmd in commands:
            result = self.validate(
                cmd.get("action", ""),
                cmd.get("parameters", {}),
                state,
            )
            results.append(result)
            if not result.is_valid and result.severity in (
                RuleSeverity.ERROR, RuleSeverity.CRITICAL
            ):
                # Görev zincirinde kritik ihlal → sonraki adımlar anlamsız
                break
        return results

    def get_active_rules_summary(self) -> str:
        """Aktif güvenlik kurallarının özet listesini döndür."""
        lines = ["📋 Aktif Güvenlik Kuralları:"]
        for rule in self._rules:
            applies = ", ".join(rule.applies_to) if rule.applies_to else "Tümü"
            lines.append(
                f"  [{rule.rule_id}] {rule.name} "
                f"({rule.severity.value}) — {applies}"
            )
        return "\n".join(lines)
