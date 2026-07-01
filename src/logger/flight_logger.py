"""
IHA Pilot Asistanı — Uçuş Kayıt Sistemi (Özgün Özellik #5)
============================================================

Bu modül, tüm komutları JSON, CSV ve otomatik HTML rapor
olarak kaydeder. Test doğrulama ve teknik rapor için kullanılır.

Kayıt Formatları:
    JSON : Makine okunabilir, programatik analiz için
    CSV  : Excel/pandas ile kolayca açılır
    HTML : Demo sunumunda gösterilecek renkli test raporu

Her Log Kaydı İçerir:
    - Orijinal kullanıcı komutu
    - LLM'in yorumu (action, parameters, reasoning)
    - Güvenlik doğrulama sonucu
    - Araç fonksiyonu çıktısı
    - Drone öncesi/sonrası durumu
    - Zaman damgası ve işlem süresi

HTML Rapor Tasarımı:
    Renk kodlama: Yeşil=Başarılı, Kırmızı=Hatalı, Sarı=Uyarı
    İstatistik özeti: Toplam/Başarılı/Başarısız sayıları
    Filtreleme: Eylem tipine göre filtre
"""

from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Log Girişi Veri Sınıfı
# ---------------------------------------------------------------------------
@dataclass
class LogEntry:
    """
    Tek bir komut yürütme oturumunun tam kaydı.

    Attributes:
        session_id (str): Oturum kimliği.
        timestamp (float): Unix zaman damgası.
        user_input (str): Kullanıcının ham komutu.
        action (str): LLM'in seçtiği eylem.
        parameters (dict): Eylem parametreleri.
        reasoning (str): LLM gerekçesi.
        confidence (float): LLM güven skoru.
        safety_valid (Optional[bool]): Güvenlik geçti mi?
        safety_rule_violated (Optional[str]): İhlal edilen kural.
        safety_violation_detail (str): İhlal ayrıntısı.
        tool_success (Optional[bool]): Araç başarılı mı?
        tool_message (str): Araç yanıt mesajı.
        state_before (dict): Komut öncesi drone durumu.
        state_after (dict): Komut sonrası drone durumu.
        llm_processing_ms (float): LLM işlem süresi.
        outcome (str): Genel sonuç: SUCCESS/SAFETY_REJECTED/TOOL_FAILED/CLARIFIED/REJECTED
    """
    session_id: str
    timestamp: float
    user_input: str
    action: str
    parameters: dict
    reasoning: str
    confidence: float
    safety_valid: Optional[bool]
    safety_rule_violated: Optional[str]
    safety_violation_detail: str
    tool_success: Optional[bool]
    tool_message: str
    state_before: dict
    state_after: dict
    llm_processing_ms: float
    outcome: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "datetime": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)
            ),
            "user_input": self.user_input,
            "action": self.action,
            "parameters": self.parameters,
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
            "safety_valid": self.safety_valid,
            "safety_rule_violated": self.safety_rule_violated,
            "safety_violation_detail": self.safety_violation_detail,
            "tool_success": self.tool_success,
            "tool_message": self.tool_message,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "llm_processing_ms": round(self.llm_processing_ms, 1),
            "outcome": self.outcome,
        }

    def to_csv_row(self) -> dict:
        """CSV'ye yazılacak düz satır."""
        return {
            "session_id": self.session_id,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
            "user_input": self.user_input,
            "action": self.action,
            "parameters": json.dumps(self.parameters, ensure_ascii=False),
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
            "safety_valid": self.safety_valid,
            "safety_rule_violated": self.safety_rule_violated or "",
            "tool_success": self.tool_success,
            "tool_message": self.tool_message,
            "altitude_before": self.state_before.get("position", {}).get("altitude", ""),
            "altitude_after": self.state_after.get("position", {}).get("altitude", ""),
            "battery_before": self.state_before.get("status", {}).get("battery", ""),
            "battery_after": self.state_after.get("status", {}).get("battery", ""),
            "outcome": self.outcome,
            "llm_ms": round(self.llm_processing_ms, 1),
        }


# ---------------------------------------------------------------------------
# Uçuş Log Sistemi
# ---------------------------------------------------------------------------
class FlightLogger:
    """
    Tüm komutları çoklu formatta kaydeden log sistemi.

    Özellikler:
        - Bellekte log tutma + dosyaya yazma
        - JSON ve CSV formatları
        - Otomatik HTML test raporu üretimi
        - Demo sırasında anlık istatistik gösterimi

    Usage::
        logger = FlightLogger()
        logger.log(entry)
        logger.save_all()
        html_path = logger.generate_html_report()
    """

    CSV_FIELDS = [
        "session_id", "datetime", "user_input", "action", "parameters",
        "reasoning", "confidence", "safety_valid", "safety_rule_violated",
        "tool_success", "tool_message", "altitude_before", "altitude_after",
        "battery_before", "battery_after", "outcome", "llm_ms",
    ]

    def __init__(self) -> None:
        cfg = settings.log
        self._log_dir = cfg.LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._entries: List[LogEntry] = []
        self._json_path = self._log_dir / cfg.JSON_LOG_FILE
        self._csv_path = self._log_dir / cfg.CSV_LOG_FILE
        self._html_path = self._log_dir / cfg.HTML_REPORT_FILE

    def log(self, entry: LogEntry) -> None:
        """Log girişi kaydet (bellek + anlık dosya append)."""
        self._entries.append(entry)
        self._append_csv(entry)
        logger.debug("Log: %s → %s", entry.user_input[:40], entry.outcome)

    def save_json(self) -> Path:
        """Tüm logları JSON formatında kaydet."""
        data = {
            "meta": {
                "total_entries": len(self._entries),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "system": "IHA Pilot Asistanı v1.0",
            },
            "entries": [e.to_dict() for e in self._entries],
            "statistics": self.get_statistics(),
        }
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("JSON log kaydedildi: %s", self._json_path)
        return self._json_path

    def _append_csv(self, entry: LogEntry) -> None:
        """CSV dosyasına satır ekle (her log anında yazılır)."""
        file_exists = self._csv_path.exists()
        with open(self._csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry.to_csv_row())

    def get_statistics(self) -> dict:
        """Log istatistiklerini hesapla."""
        total = len(self._entries)
        if total == 0:
            return {"total": 0}
        success = sum(1 for e in self._entries if e.outcome == "SUCCESS")
        safety_rejected = sum(1 for e in self._entries if e.outcome == "SAFETY_REJECTED")
        clarified = sum(1 for e in self._entries if e.outcome == "CLARIFIED")
        rejected = sum(1 for e in self._entries if e.outcome == "REJECTED")
        tool_failed = sum(1 for e in self._entries if e.outcome == "TOOL_FAILED")
        avg_confidence = sum(e.confidence for e in self._entries) / total
        avg_llm_ms = sum(e.llm_processing_ms for e in self._entries) / total
        actions = {}
        for e in self._entries:
            actions[e.action] = actions.get(e.action, 0) + 1
        return {
            "total": total,
            "success": success,
            "safety_rejected": safety_rejected,
            "clarified": clarified,
            "rejected": rejected,
            "tool_failed": tool_failed,
            "success_rate_percent": round(success / total * 100, 1),
            "avg_confidence": round(avg_confidence, 3),
            "avg_llm_ms": round(avg_llm_ms, 1),
            "actions_breakdown": actions,
        }

    def save_all(self) -> dict:
        """JSON + HTML kaydet ve dosya yollarını döndür."""
        json_path = self.save_json()
        html_path = self.generate_html_report()
        return {"json": str(json_path), "csv": str(self._csv_path), "html": str(html_path)}

    def generate_html_report(self) -> Path:
        """
        Renkli, interaktif HTML test raporu üret.

        Bu rapor teslim dokümantasyonunun bir parçasıdır
        ve demo sunumunda doğrudan açılabilir.
        """
        stats = self.get_statistics()
        rows_html = ""
        for e in self._entries:
            outcome_colors = {
                "SUCCESS": "#22c55e",
                "SAFETY_REJECTED": "#ef4444",
                "TOOL_FAILED": "#f97316",
                "CLARIFIED": "#eab308",
                "REJECTED": "#6b7280",
            }
            color = outcome_colors.get(e.outcome, "#6b7280")
            safety_txt = (
                f"✅ OK" if e.safety_valid
                else f"❌ {e.safety_rule_violated or 'N/A'}"
            )
            rows_html += f"""
            <tr>
                <td style="color:#94a3b8">{time.strftime('%H:%M:%S', time.localtime(e.timestamp))}</td>
                <td><strong>{e.user_input}</strong></td>
                <td><code style="background:#1e3a5f;padding:2px 6px;border-radius:4px">{e.action}</code></td>
                <td style="max-width:300px;font-size:0.85em;color:#94a3b8">{e.reasoning[:100]}{'...' if len(e.reasoning)>100 else ''}</td>
                <td>{safety_txt}</td>
                <td>{'✅' if e.tool_success else ('❌' if e.tool_success is False else '—')}</td>
                <td><span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:0.8em">{e.outcome}</span></td>
                <td style="color:#94a3b8">{e.llm_processing_ms:.0f}ms</td>
            </tr>"""

        action_rows = ""
        for action, count in stats.get("actions_breakdown", {}).items():
            action_rows += f"<tr><td><code>{action}</code></td><td>{count}</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IHA Pilot Asistanı — Test Raporu</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0e1a; color: #e2e8f0; padding: 2rem; }}
  h1 {{ color: #00d4ff; font-size: 1.8rem; margin-bottom: 0.5rem; }}
  .subtitle {{ color: #64748b; margin-bottom: 2rem; font-size: 0.95rem; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card {{ background: #0f172a; border: 1px solid #1e3a5f; border-radius: 12px; padding: 1.2rem; text-align: center; }}
  .stat-card .value {{ font-size: 2rem; font-weight: 700; color: #00d4ff; }}
  .stat-card .label {{ font-size: 0.8rem; color: #64748b; margin-top: 0.3rem; }}
  .success .value {{ color: #22c55e; }}
  .failed .value {{ color: #ef4444; }}
  .warn .value {{ color: #eab308; }}
  table {{ width: 100%; border-collapse: collapse; background: #0f172a; border-radius: 12px; overflow: hidden; }}
  thead th {{ background: #1e293b; color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.8rem 1rem; text-align: left; }}
  tbody td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #1e293b; font-size: 0.88rem; }}
  tbody tr:hover {{ background: #1e293b33; }}
  h2 {{ color: #00d4ff; font-size: 1.2rem; margin: 2rem 0 1rem; }}
  .mini-table {{ max-width: 300px; }}
  .footer {{ margin-top: 2rem; color: #475569; font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<h1>🛩️ IHA Pilot Asistanı — Test Raporu</h1>
<p class="subtitle">Oluşturulma: {time.strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Sistem: IHA Pilot Asistanı v1.0</p>

<div class="stats-grid">
  <div class="stat-card"><div class="value">{stats.get('total',0)}</div><div class="label">Toplam Komut</div></div>
  <div class="stat-card success"><div class="value">{stats.get('success',0)}</div><div class="label">Başarılı</div></div>
  <div class="stat-card failed"><div class="value">{stats.get('safety_rejected',0)}</div><div class="label">Güvenlik Reddi</div></div>
  <div class="stat-card warn"><div class="value">{stats.get('clarified',0)}</div><div class="label">Açıklama İstendi</div></div>
  <div class="stat-card"><div class="value">{stats.get('success_rate_percent',0)}%</div><div class="label">Başarı Oranı</div></div>
  <div class="stat-card"><div class="value">{stats.get('avg_confidence',0):.2f}</div><div class="label">Ort. Güven Skoru</div></div>
  <div class="stat-card"><div class="value">{stats.get('avg_llm_ms',0):.0f}ms</div><div class="label">Ort. LLM Süresi</div></div>
</div>

<h2>📝 Komut Logları</h2>
<table>
  <thead>
    <tr>
      <th>Saat</th><th>Komut</th><th>Eylem</th><th>LLM Gerekçesi</th>
      <th>Güvenlik</th><th>Araç</th><th>Sonuç</th><th>Süre</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>

<h2>📊 Eylem Dağılımı</h2>
<table class="mini-table">
  <thead><tr><th>Eylem</th><th>Sayı</th></tr></thead>
  <tbody>{action_rows}</tbody>
</table>

<div class="footer">IHA Pilot Asistanı — Eğitim Amaçlı Proje | SHGM SHY-İHA-01 referanslı</div>
</body>
</html>"""

        with open(self._html_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("HTML rapor kaydedildi: %s", self._html_path)
        return self._html_path

    def print_statistics(self) -> None:
        """Terminal'de istatistik özeti göster."""
        stats = self.get_statistics()
        print("\n" + "═" * 45)
        print("   📊 OTURUM İSTATİSTİKLERİ")
        print("═" * 45)
        print(f"  Toplam komut      : {stats.get('total', 0)}")
        print(f"  Başarılı          : {stats.get('success', 0)}")
        print(f"  Güvenlik reddi    : {stats.get('safety_rejected', 0)}")
        print(f"  Açıklama istendi  : {stats.get('clarified', 0)}")
        print(f"  Başarı oranı      : %{stats.get('success_rate_percent', 0)}")
        print(f"  Ort. LLM süresi   : {stats.get('avg_llm_ms', 0):.0f}ms")
        print("═" * 45)
