"""
IHA Pilot Asistanı — Ana Giriş Noktası
=======================================

Bu modül, sistemin tüm bileşenlerini bir araya getirerek
interaktif CLI arayüzü sunar.

Çalışma Modları:
    python src/main.py              → Standart CLI modu
    python src/main.py --web        → Web dashboard modu (Flask)
    python src/main.py --demo       → 5 otomatik demo komutu çalıştır

Demo Video İpuçları:
    1. '--demo' modu kayıt için idealdir — otomatik, tekrarlanabilir
    2. Web modu ('--web') dashboard görselliği için kullanılır
    3. CLI modu gerçek zamanlı interaktif kullanımı gösterir

Sistem Başlatma Sırası:
    1. Bağımlılık kontrolü (Ollama, dotenv)
    2. DroneState başlatma
    3. Tüm katmanların örneklenmesi
    4. Ollama bağlantı testi
    5. İnteraktif döngü başlatma
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# Windows terminal UTF-8 zorlaması (cp1254 / emoji hatası önleme)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Proje kökünü Python path'ine ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# rich importu — terminal görselleştirme
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.rule import Rule
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from src.simulation.drone import DroneState
from src.simulation.telemetry import TelemetryReader
from src.tools.drone_tools import DroneTools
from src.safety.validator import SafetyValidator
from src.safety.rules import SAFETY_RULES
from src.agent.llm_client import OllamaClient, ParsedCommand
from src.agent.command_parser import CommandParser, ExecutionResult
from src.battery.manager import BatteryManager, BatteryStatus
from src.mission.planner import MissionPlanner
from src.mission.executor import MissionExecutor
from src.logger.flight_logger import FlightLogger, LogEntry
from config.settings import settings

# ---------------------------------------------------------------------------
# Loglama konfigürasyonu
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(settings.log.LOG_DIR / "system.log", encoding="utf-8"),
    ],
)

console = Console(file=sys.stdout) if RICH_AVAILABLE else None


def _print(msg: str, style: str = "") -> None:
    """Rich varsa renkli, yoksa düz yazdır."""
    if RICH_AVAILABLE and console:
        console.print(msg, style=style)
    else:
        print(msg)


def _banner() -> None:
    """Başlangıç başlık ekranı."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║          🛩️  IHA PİLOT ASİSTANI  v1.0                       ║
║     LLM Tabanlı İnsansız Hava Aracı Komut Sistemi           ║
║                                                              ║
║  Güvenlik: SHGM SHY-İHA-01 | ICAO Annex 2 referanslı       ║
║  LLM     : Ollama (yerel)                                    ║
║  Özellik : Açıklanabilir Güvenlik + Görev Planlama          ║
╚══════════════════════════════════════════════════════════════╝
"""
    _print(banner, style="bold cyan")


def _check_ollama(client: OllamaClient) -> bool:
    """Ollama bağlantısını kontrol et ve sonucu göster."""
    _print("\n[*] Ollama bağlantısı kontrol ediliyor...")
    ok, msg = client.check_connection()
    if ok:
        _print(f"[OK] {msg}", style="bold green")
    else:
        _print(f"[UYARI] {msg}", style="bold yellow")
        _print(
            "      Ollama olmadan sistem çalışamaz. "
            "Kurulum: https://ollama.com",
            style="yellow",
        )
    return ok


def _display_safety_rules() -> None:
    """Aktif güvenlik kurallarını listele."""
    _print("\n[*] Aktif Güvenlik Kuralları:")
    for rule in SAFETY_RULES:
        applies = ", ".join(rule.applies_to) if rule.applies_to else "Tüm eylemler"
        _print(
            f"    [{rule.rule_id}] {rule.name} "
            f"({rule.severity.value}) — {applies}"
        )


def _build_execution_log(
    session_id: str,
    user_input: str,
    cmd: ParsedCommand,
    result: ExecutionResult,
    state_before: DroneState,
    state_after: DroneState,
) -> LogEntry:
    """ExecutionResult'tan LogEntry oluştur."""
    # Sonuç sınıflandırması
    if cmd.action == "clarify":
        outcome = "CLARIFIED"
    elif cmd.action == "reject":
        outcome = "REJECTED"
    elif result.validation and not result.validation.is_valid:
        outcome = "SAFETY_REJECTED"
    elif result.tool_result and not result.tool_result.success:
        outcome = "TOOL_FAILED"
    elif result.success:
        outcome = "SUCCESS"
    else:
        outcome = "UNKNOWN"

    return LogEntry(
        session_id=session_id,
        timestamp=time.time(),
        user_input=user_input,
        action=cmd.action,
        parameters=cmd.parameters,
        reasoning=cmd.reasoning,
        confidence=cmd.confidence,
        safety_valid=result.validation.is_valid if result.validation else None,
        safety_rule_violated=(
            result.validation.rule_violated if result.validation else None
        ),
        safety_violation_detail=(
            result.validation.violation_detail if result.validation else ""
        ),
        tool_success=result.tool_result.success if result.tool_result else None,
        tool_message=result.tool_result.message if result.tool_result else result.final_message,
        state_before=state_before.to_dict(),
        state_after=state_after.to_dict(),
        llm_processing_ms=cmd.processing_time_ms,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Demo Komutları
# ---------------------------------------------------------------------------
DEMO_COMMANDS = [
    "Mevcut durumu göster",
    "10 metreye kalk",
    "Havada mıyız ve batarya ne kadar?",
    "100000 metreye çık",           # → Güvenlik reddi (SR-ALT-001)
    "Biraz yüksel",                 # → Belirsiz, açıklama iste
    "Koordinat (50, 80) metre, 30m irtifaya git",
    "Eve dön",
    "Önce 20 metreye kalk, sonra doğuya 100 metre git, durum bildir ve eve dön",
]


# ---------------------------------------------------------------------------
# Ana Döngü
# ---------------------------------------------------------------------------
def run_cli(demo_mode: bool = False) -> None:
    """
    İnteraktif CLI döngüsü.

    Args:
        demo_mode: True ise DEMO_COMMANDS otomatik çalışır.
    """
    _banner()

    # Bileşenler
    state = DroneState()
    tools = DroneTools(state)
    validator = SafetyValidator()
    llm_client = OllamaClient()
    parser = CommandParser(tools, validator)
    battery_mgr = BatteryManager()
    mission_planner = MissionPlanner()
    mission_executor = MissionExecutor(tools, validator)
    flight_logger = FlightLogger()

    session_id = str(uuid.uuid4())[:8].upper()
    _print(f"\n[*] Oturum ID: {session_id}")
    _print(f"[*] Model    : {settings.llm.OLLAMA_MODEL}")
    _print(f"[*] Loglar   : {settings.log.LOG_DIR}")

    # Ollama bağlantı kontrolü
    ollama_ok = _check_ollama(llm_client)
    if not ollama_ok and not demo_mode:
        _print("\n[!] Ollama olmadan devam edilemiyor. Çıkılıyor.", style="bold red")
        return

    _display_safety_rules()

    _print("\n" + "─" * 62)
    _print("  Komut girin (çıkmak için 'exit' veya Ctrl+C)")
    _print("  Yardım için 'yardim', loglar için 'rapor'")
    _print("─" * 62 + "\n")

    commands_to_run = DEMO_COMMANDS if demo_mode else []

    try:
        while True:
            # ── Batarya izleme ───────────────────────────────────────────
            battery_alert = battery_mgr.evaluate(tools.state)
            if battery_alert.status != BatteryStatus.NORMAL:
                _print(battery_alert.format_for_display(), style="yellow")

            # Otomatik RTH tetikle
            if battery_alert.should_auto_rth:
                _print(
                    "\n[!] OTOMATİK RTH TETIKLENDI — Batarya kritik!",
                    style="bold red",
                )
                cmd = ParsedCommand(
                    action="return_to_home",
                    parameters={},
                    reasoning="Otomatik RTH — batarya kritik eşiğin altına düştü.",
                    confidence=1.0,
                )
                state_before = tools.state.clone()
                result = parser.execute("(otomatik RTH)", cmd)
                _print(result.final_message)
                entry = _build_execution_log(
                    session_id, "(otomatik RTH)", cmd, result,
                    state_before, tools.state
                )
                flight_logger.log(entry)
                continue

            # ── Giriş al ────────────────────────────────────────────────
            telemetry_reader = TelemetryReader(tools.state)
            prompt_line = f"\n{telemetry_reader.get_concise()}\n  >> "

            if demo_mode and commands_to_run:
                user_input = commands_to_run.pop(0)
                _print(f"{prompt_line}{user_input}", style="bold")
                time.sleep(0.5)  # demo görünürlüğü için kısa bekleme
            else:
                try:
                    user_input = input(prompt_line).strip()
                except EOFError:
                    break

            if not user_input:
                continue

            # ── Özel komutlar ────────────────────────────────────────────
            if user_input.lower() in ("exit", "quit", "çıkış", "çık"):
                break
            if user_input.lower() in ("yardim", "yardım", "help"):
                _print_help()
                continue
            if user_input.lower() == "rapor":
                paths = flight_logger.save_all()
                _print(f"\n  Rapor kaydedildi:")
                for fmt, path in paths.items():
                    _print(f"    {fmt.upper()}: {path}")
                continue
            if user_input.lower() == "durum":
                _print(TelemetryReader(tools.state).get_human_readable())
                continue
            if user_input.lower() == "kurallar":
                _display_safety_rules()
                continue

            # ── LLM İşleme ──────────────────────────────────────────────
            _print("\n  [LLM] İşleniyor...", style="dim")
            state_before = tools.state.clone()

            parsed_cmd = llm_client.process(user_input, tools.state)
            _print(parsed_cmd.format_for_display())

            # ── Görev Planlama ───────────────────────────────────────────
            if parsed_cmd.is_mission:
                mission, error = mission_planner.create_mission(
                    name=parsed_cmd.parameters.get("mission_name", "İsimsiz Görev"),
                    raw_steps=parsed_cmd.mission_steps,
                    initial_state=tools.state,
                )
                if error:
                    _print(f"\n  [!] Görev planlanamadı: {error}", style="red")
                    continue
                _print(f"\n  [*] Görev oluşturuldu: {mission.name} "
                       f"({mission.total_steps} adım)")
                mission_executor._tools = tools
                completed_mission = mission_executor.execute(mission)
                _print(completed_mission.format_for_display())
                # Görev logunu kaydet
                entry = LogEntry(
                    session_id=session_id,
                    timestamp=time.time(),
                    user_input=user_input,
                    action="plan_mission",
                    parameters=parsed_cmd.parameters,
                    reasoning=parsed_cmd.reasoning,
                    confidence=parsed_cmd.confidence,
                    safety_valid=True,
                    safety_rule_violated=None,
                    safety_violation_detail="",
                    tool_success=completed_mission.status.value == "COMPLETED",
                    tool_message=f"Görev {completed_mission.status.value}",
                    state_before=state_before.to_dict(),
                    state_after=tools.state.to_dict(),
                    llm_processing_ms=parsed_cmd.processing_time_ms,
                    outcome="SUCCESS" if completed_mission.status.value == "COMPLETED" else "TOOL_FAILED",
                )
                flight_logger.log(entry)
                continue

            # ── Tekil Komut Yürütme ──────────────────────────────────────
            result = parser.execute(user_input, parsed_cmd)
            _print(f"\n  {result.final_message}")

            entry = _build_execution_log(
                session_id, user_input, parsed_cmd, result,
                state_before, tools.state
            )
            flight_logger.log(entry)

            # Demo modunda tüm komutlar bittiyse çık
            if demo_mode and not commands_to_run:
                _print("\n  [*] Demo tamamlandı.", style="bold green")
                break

    except KeyboardInterrupt:
        _print("\n\n  [*] Kullanıcı tarafından kesildi.", style="yellow")

    finally:
        # Oturum sonu — kaydet ve istatistik göster
        _print("\n  [*] Log dosyaları kaydediliyor...")
        paths = flight_logger.save_all()
        flight_logger.print_statistics()
        _print(f"\n  HTML Rapor : {paths['html']}", style="bold")
        _print(f"  JSON Log   : {paths['json']}")
        _print(f"  CSV Log    : {paths['csv']}")
        _print("\n  Güvenli uçuşlar dileriz. Hoşçakalın!\n", style="bold cyan")


def _print_help() -> None:
    """Yardım menüsü."""
    _print("""
  ┌─────────────────────────────────────────────────┐
  │           YÜK KOMUTLARI VE ÖRNEKLER             │
  ├─────────────────────────────────────────────────┤
  │  Telemetri  : "durum nedir", "neredeyim"        │
  │  Kalkış     : "30 metreye kalk", "50m yüksel"   │
  │  İniş       : "in", "iniş yap", "yere in"      │
  │  Eve Dön    : "eve dön", "geri gel", "RTH"      │
  │  Koordinat  : "(100,50) 20m irtifaya git"       │
  │  Görev Zinciri: "kalk, git, bildir, eve dön"    │
  ├─────────────────────────────────────────────────┤
  │  Sistem Komutları:                              │
  │  'durum'    → Tam telemetri raporu              │
  │  'kurallar' → Güvenlik kurallarını listele      │
  │  'rapor'    → Log dosyalarını kaydet            │
  │  'exit'     → Çıkış                            │
  └─────────────────────────────────────────────────┘
""")


# ---------------------------------------------------------------------------
# Web Modu (Flask)
# ---------------------------------------------------------------------------
def run_web() -> None:
    """Web dashboard modunu başlat."""
    try:
        from src.web.app import create_app
        app, socketio = create_app()
        cfg = settings.web
        _print(f"\n  [WEB] Dashboard: http://{cfg.HOST}:{cfg.PORT}", style="bold cyan")
        socketio.run(app, host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
    except ImportError as e:
        _print(f"  [!] Web bağımlılıkları eksik: {e}", style="red")
        _print("  pip install flask flask-socketio eventlet")


# ---------------------------------------------------------------------------
# CLI Argüman Ayrıştırıcı
# ---------------------------------------------------------------------------
def main() -> None:
    """Ana giriş noktası."""
    ap = argparse.ArgumentParser(
        description="IHA Pilot Asistanı — LLM tabanlı drone komut sistemi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python src/main.py              # İnteraktif CLI
  python src/main.py --web        # Web dashboard
  python src/main.py --demo       # Otomatik demo (8 komut)
        """,
    )
    ap.add_argument(
        "--web",
        action="store_true",
        help="Web dashboard modunda çalıştır (Flask + SocketIO)",
    )
    ap.add_argument(
        "--demo",
        action="store_true",
        help="Otomatik demo modunda çalıştır (önceden tanımlı komutlar)",
    )
    args = ap.parse_args()

    if args.web:
        run_web()
    else:
        run_cli(demo_mode=args.demo)


if __name__ == "__main__":
    main()
