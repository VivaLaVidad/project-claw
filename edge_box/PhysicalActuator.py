from __future__ import annotations

import shlex
import subprocess
import time
from typing import Any, Optional

from edge_box.action_space import Action, parse_actions
from edge_box.VLM_Observer import VLMObserver


class PhysicalActuator:
    def __init__(self, observer: Optional[VLMObserver] = None, device_serial: Optional[str] = None):
        self.observer = observer or VLMObserver()
        self.device_serial = device_serial or self.observer.config.device_serial

    def run_instruction(self, instruction: str) -> dict[str, Any]:
        # 1) 让 VLM 规划动作
        plan = self.observer.plan_actions(instruction)
        actions = parse_actions(plan)
        goal = str(plan.get("goal") or instruction)

        # 2) 执行动作前截图
        before_b64 = self.observer.capture_screen_base64()

        executed = []
        for action in actions:
            self._execute(action)
            executed.append({"type": action.type, "params": action.params})

        # 3) 执行动作后截图 + 视觉反馈闭环校验
        after_b64 = self.observer.capture_screen_base64()
        verify = self.observer.validate_state_change(before_b64, after_b64, goal)

        return {
            "instruction": instruction,
            "goal": goal,
            "executed_actions": executed,
            "verify": verify,
        }

    def _execute(self, action: Action) -> None:
        t = action.type.upper()
        p = action.params or {}

        if t == "CLICK":
            x = int(p.get("x", 0))
            y = int(p.get("y", 0))
            self._adb_shell(["input", "tap", str(x), str(y)])
            return

        if t == "SWIPE":
            x1 = int(p.get("x1", 0))
            y1 = int(p.get("y1", 0))
            x2 = int(p.get("x2", 0))
            y2 = int(p.get("y2", 0))
            duration = int(p.get("duration_ms", 280))
            self._adb_shell(["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
            return

        if t == "TYPE":
            text = str(p.get("text", ""))
            safe = shlex.quote(text)
            self._adb_shell(["input", "text", safe])
            send_enter = bool(p.get("enter", False))
            if send_enter:
                self._adb_shell(["input", "keyevent", "66"])
            return

        if t == "WAIT":
            ms = int(p.get("ms", p.get("duration_ms", 800)))
            time.sleep(max(0.0, ms / 1000.0))
            return

        raise ValueError(f"unsupported action type: {t}")

    def _adb_shell(self, args: list[str]) -> None:
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        cmd += ["shell"] + args
        subprocess.run(cmd, check=True, timeout=8)
