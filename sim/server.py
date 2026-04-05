"""PocketPD simulation web server.

Extends framebuf_canvas's DisplayServer with:
- REST API for device control (/api/*)
- WebSocket for real-time status broadcast (/ws/status)
"""

import asyncio
import json

from microdot.websocket import with_websocket


def add_status_snapshot(sm):
    """Add to_dict() method to StateMachine for JSON serialization."""

    def to_dict():
        fixed = []
        for p in sm.pd.fixed_pdos:
            fixed.append({
                "voltage_mv": p.voltage_mv,
                "max_current_ma": p.max_current_ma,
                "index": p.index,
            })
        pps = []
        for p in sm.pd.pps_pdos:
            pps.append({
                "min_voltage_mv": p.min_voltage_mv,
                "max_voltage_mv": p.max_voltage_mv,
                "max_current_ma": p.max_current_ma,
                "index": p.index,
            })
        return {
            "state": sm.state,
            "output_on": sm.output_on,
            "voltage_mv": sm.voltage_mv,
            "current_ma": sm.current_ma,
            "power_mw": sm.voltage_mv * sm.current_ma // 1000,
            "cv_mode": sm.cv_mode,
            "adjust_voltage": sm.adjust_voltage,
            "v_scale_idx": sm.v_scale_idx,
            "i_scale_idx": sm.i_scale_idx,
            "display_energy": sm.display_energy,
            "blink_on": sm.blink_on,
            "target_voltage_mv": sm.settings.target_voltage_mv,
            "target_current_ma": sm.settings.target_current_ma,
            "has_pps": sm.pd.has_pps,
            "fixed_pdos": fixed,
            "pps_pdos": pps,
            "wh": sm.energy.wh,
            "ah": sm.energy.ah,
            "elapsed_s": sm.energy.elapsed_s,
        }

    sm.to_dict = to_dict


def setup_routes(app, sm, sim_ina=None):
    """Add PocketPD REST API and status WebSocket routes to a microdot app.

    Args:
        app: Microdot app instance (from DisplayServer.app)
        sm: StateMachine instance
        sim_ina: Optional SimINA226 for sim-only INA control
    """
    status_clients = set()

    # --- REST API ---

    @app.route("/api/status")
    async def api_status(request):
        return json.dumps(sm.to_dict()), 200, {"Content-Type": "application/json"}

    @app.route("/api/output", methods=["POST"])
    async def api_output(request):
        data = json.loads(request.body)
        sm.set_output(bool(data.get("on", False)))
        if sim_ina:
            sim_ina.set_output(sm.output_on)
        return json.dumps({"ok": True, "output_on": sm.output_on})

    @app.route("/api/voltage", methods=["POST"])
    async def api_voltage(request):
        data = json.loads(request.body)
        mv = int(data.get("mv", sm.settings.target_voltage_mv))
        sm.settings.target_voltage_mv = mv
        if sm.pd.has_pps and sm.pd.pps_pdos:
            pps = sm.pd.pps_pdos[0]
            sm.pd.request_pps(pps, mv, sm.settings.target_current_ma)
        return json.dumps({"ok": True, "target_voltage_mv": sm.settings.target_voltage_mv})

    @app.route("/api/current", methods=["POST"])
    async def api_current(request):
        data = json.loads(request.body)
        ma = int(data.get("ma", sm.settings.target_current_ma))
        sm.settings.target_current_ma = ma
        if sm.pd.has_pps and sm.pd.pps_pdos:
            pps = sm.pd.pps_pdos[0]
            sm.pd.request_pps(pps, sm.settings.target_voltage_mv, ma)
        return json.dumps({"ok": True, "target_current_ma": sm.settings.target_current_ma})

    @app.route("/api/encoder", methods=["POST"])
    async def api_encoder(request):
        data = json.loads(request.body)
        delta = int(data.get("delta", 0))
        # Inject encoder rotation directly into state machine
        from drivers.button import EVENT_NONE

        sm._handle_normal_inputs(EVENT_NONE, EVENT_NONE, EVENT_NONE, delta)
        return json.dumps({"ok": True})

    @app.route("/api/button/<name>", methods=["POST"])
    async def api_button(request, name):
        data = json.loads(request.body)
        event_str = data.get("event", "short")
        from drivers.button import EVENT_LONG, EVENT_SHORT

        event = EVENT_SHORT if event_str == "short" else EVENT_LONG

        none = 0  # EVENT_NONE
        if name == "output":
            sm._handle_normal_inputs(event, none, none, 0)
        elif name == "select":
            sm._handle_normal_inputs(none, event, none, 0)
        elif name == "encoder":
            sm._handle_normal_inputs(none, none, event, 0)
        else:
            return json.dumps({"error": "unknown button"}), 400

        return json.dumps({"ok": True})

    if sim_ina:

        @app.route("/api/sim/ina", methods=["POST"])
        async def api_sim_ina(request):
            data = json.loads(request.body)
            if "voltage_mv" in data:
                sim_ina._voltage_mv = int(data["voltage_mv"])
            if "current_ma" in data:
                sim_ina._current_ma = int(data["current_ma"])
            sim_ina._update_registers()
            return json.dumps({"ok": True})

    # --- WebSocket status broadcast ---

    @app.route("/ws/status")
    @with_websocket
    async def ws_status(request, ws):
        status_clients.add(ws)
        try:
            # Send initial state
            await ws.send(json.dumps(sm.to_dict()))
            while True:
                try:
                    await ws.receive()
                except Exception:
                    break
        finally:
            status_clients.discard(ws)

    async def broadcast_status():
        """Broadcast state to all status WebSocket clients. Call periodically."""
        if not status_clients:
            return
        msg = json.dumps(sm.to_dict())
        dead = []
        for ws in status_clients:
            try:
                await ws.send(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            status_clients.discard(ws)

    return broadcast_status
