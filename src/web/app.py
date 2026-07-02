"""
IHA Pilot Asistanı — Flask Web Dashboard (Özgün Özellik #1)
============================================================

Bu modül, drone'u gerçek zamanlı olarak izleyip komut vermenizi
sağlayan Flask tabanlı web dashboard'u sunar.

Özellikler:
    - REST API: /api/state, /api/command, /api/logs, /api/stats
    - WebSocket: Her saniye telemetri push (Flask-SocketIO)
    - Leaflet.js haritasında drone konumu
    - Anlık batarya, irtifa, hız göstergeleri

Demo/Sunum Notu:
    Web modu, demo videosu için CLI'dan çok daha görsel bir arayüz sunar.
    Tarayıcıda açık tutarak drone hareketleri haritada izlenebilir.

Başlatma:
    python src/main.py --web
    → http://127.0.0.1:5000
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from src.simulation.drone import DroneState
from src.tools.drone_tools import DroneTools
from src.safety.validator import SafetyValidator
from src.agent.llm_client import OllamaClient
from src.agent.command_parser import CommandParser, ExecutionResult
from src.battery.manager import BatteryManager
from src.mission.planner import MissionPlanner
from src.mission.executor import MissionExecutor
from src.logger.flight_logger import FlightLogger, LogEntry
from config.settings import settings


def create_app():
    """
    Flask uygulamasını ve WebSocket sunucusunu oluştur.

    Returns:
        tuple[Flask, SocketIO]: Uygulama ve SocketIO örneği.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = settings.web.SECRET_KEY
    CORS(app)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

    # ── Global sistem nesneleri ─────────────────────────────────────────
    state = DroneState()
    tools = DroneTools(state)
    validator = SafetyValidator()
    llm_client = OllamaClient()
    parser = CommandParser(tools, validator)
    battery_mgr = BatteryManager()
    mission_planner = MissionPlanner()
    flight_logger = FlightLogger()
    session_id = str(uuid.uuid4())[:8].upper()

    # ── Telemetri push thread ───────────────────────────────────────────
    def telemetry_background_task():
        """WebSocket ile her saniye telemetri gönder."""
        while True:
            socketio.sleep(settings.web.TELEMETRY_PUSH_INTERVAL)
            try:
                bat_alert = battery_mgr.evaluate(tools.state)
                data = {
                    "state": tools.state.to_dict(),
                    "battery_alert": bat_alert.to_dict(),
                    "timestamp": time.time(),
                }
                socketio.emit("telemetry_update", data)

                # Otomatik RTH
                if bat_alert.should_auto_rth:
                    from src.agent.llm_client import ParsedCommand
                    auto_cmd = ParsedCommand(
                        action="return_to_home",
                        parameters={},
                        reasoning="Otomatik RTH — batarya kritik eşiğin altına düştü.",
                        confidence=1.0,
                    )
                    result = parser.execute("(Otomatik RTH)", auto_cmd)
                    socketio.emit("auto_rth", {"message": result.final_message})
            except Exception:
                pass

    # ── REST API Rotaları ───────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("index.html",
                               model=settings.llm.OLLAMA_MODEL,
                               max_altitude=settings.safety.MAX_ALTITUDE,
                               geofence_radius=settings.safety.GEOFENCE_RADIUS)

    @app.route("/api/state")
    def api_state():
        """Anlık drone durumu."""
        bat_alert = battery_mgr.evaluate(tools.state)
        return jsonify({
            "state": tools.state.to_dict(),
            "battery_alert": bat_alert.to_dict(),
        })

    @app.route("/api/command", methods=["POST"])
    def api_command():
        """Doğal dil komutu al ve işle."""
        data = request.get_json(force=True)
        user_input = data.get("command", "").strip()
        if not user_input:
            return jsonify({"error": "Komut boş olamaz"}), 400

        state_before = tools.state.clone()

        # LLM ile işle
        parsed_cmd = llm_client.process(user_input, tools.state)

        # Görev zinciri
        if parsed_cmd.is_mission:
            mission, err = mission_planner.create_mission(
                name=parsed_cmd.parameters.get("mission_name", "Web Görevi"),
                raw_steps=parsed_cmd.mission_steps,
                initial_state=tools.state,
            )
            if err:
                return jsonify({
                    "success": False,
                    "message": f"Görev oluşturulamadı: {err}",
                    "parsed": parsed_cmd.to_dict(),
                })

            executor = MissionExecutor(tools, validator)
            completed = executor.execute(mission)
            response = {
                "success": completed.status.value == "COMPLETED",
                "message": f"Görev {completed.status.value}: {mission.name}",
                "parsed": parsed_cmd.to_dict(),
                "mission": completed.to_dict(),
                "state": tools.state.to_dict(),
            }
        else:
            result = parser.execute(user_input, parsed_cmd)

            # Loglama
            outcome = _classify_outcome(parsed_cmd, result)
            entry = LogEntry(
                session_id=session_id,
                timestamp=time.time(),
                user_input=user_input,
                action=parsed_cmd.action,
                parameters=parsed_cmd.parameters,
                reasoning=parsed_cmd.reasoning,
                confidence=parsed_cmd.confidence,
                safety_valid=result.validation.is_valid if result.validation else None,
                safety_rule_violated=result.validation.rule_violated if result.validation else None,
                safety_violation_detail=result.validation.violation_detail if result.validation else "",
                tool_success=result.tool_result.success if result.tool_result else None,
                tool_message=result.final_message,
                state_before=state_before.to_dict(),
                state_after=tools.state.to_dict(),
                llm_processing_ms=parsed_cmd.processing_time_ms,
                outcome=outcome,
            )
            flight_logger.log(entry)

            response = {
                "success": result.success,
                "message": result.final_message,
                "parsed": parsed_cmd.to_dict(),
                "state": tools.state.to_dict(),
                "outcome": outcome,
            }

        # WebSocket ile anlık state push
        socketio.emit("command_result", response)
        return jsonify(response)

    @app.route("/api/logs")
    def api_logs():
        """Son log girişlerini döndür."""
        entries = [e.to_dict() for e in flight_logger._entries[-50:]]
        return jsonify({"entries": entries, "total": len(flight_logger._entries)})

    @app.route("/api/stats")
    def api_stats():
        """Oturum istatistikleri."""
        return jsonify(flight_logger.get_statistics())

    @app.route("/api/save_report")
    def api_save_report():
        """Log dosyalarını kaydet ve yolları döndür."""
        paths = flight_logger.save_all()
        return jsonify({"saved": True, "paths": paths})

    @app.route("/api/rules")
    def api_rules():
        """Aktif güvenlik kurallarını listele."""
        from src.safety.rules import SAFETY_RULES
        rules = [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "severity": r.severity.value,
                "applies_to": r.applies_to,
                "legal_ref": r.legal_ref,
            }
            for r in SAFETY_RULES
        ]
        return jsonify({"rules": rules})

    # ── WebSocket Olayları ──────────────────────────────────────────────
    @socketio.on("connect")
    def on_connect():
        """Yeni istemci bağlandı — arka plan görevini başlat."""
        socketio.start_background_task(telemetry_background_task)
        emit("connected", {
            "session_id": session_id,
            "model": settings.llm.OLLAMA_MODEL,
            "state": tools.state.to_dict(),
        })

    return app, socketio


def _classify_outcome(parsed_cmd, result: ExecutionResult) -> str:
    """Komut sonucunu sınıflandır."""
    if parsed_cmd.action == "clarify":
        return "CLARIFIED"
    if parsed_cmd.action == "reject":
        return "REJECTED"
    if result.validation and not result.validation.is_valid:
        return "SAFETY_REJECTED"
    if result.tool_result and not result.tool_result.success:
        return "TOOL_FAILED"
    if result.success:
        return "SUCCESS"
    return "UNKNOWN"
