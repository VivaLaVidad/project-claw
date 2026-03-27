from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

from config import settings

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog, Static

try:
    from cloud_server.match_orchestrator import MatchOrchestrator
except Exception:
    MatchOrchestrator = None


MERCHANTS = [
    "王记快餐",
    "阿强烧烤",
    "老城区炒粉",
    "夜航牛肉面",
    "江湖盖码饭",
    "雾都烤鱼档",
    "南门煲仔饭",
]

ITEMS = [
    "黄焖鸡米饭",
    "香辣鸡腿堡",
    "牛肉炒粉",
    "酸菜鱼套餐",
    "藤椒鸡饭",
    "黑椒牛柳饭",
    "麻辣香锅单人份",
]

PERSONAS = ["学生党", "夜班骑手", "写字楼白领", "电竞少年", "健身党", "熬夜程序员"]

SCAN_GLYPHS = ["◜", "◠", "◝", "◞", "◡", "◟"]
SHOWCASE_EVENT_FILE = Path(settings.SHOWCASE_EVENT_FILE)


@dataclass
class NetworkMetrics:
    boxes_online: int = 1402
    npu_pool: float = 8.4
    passive_income: int = 12405
    scan_ratio: float = 0.18
    active_intents: int = 17
    matched_trades: int = 2384
    saved_fees: int = 7126
    route_heat: int = 67
    consumer_agents: int = 9241
    sandbox_rounds: int = 321
    anonymous_links: int = 5812


class GodView(Static):
    frame = reactive(0)
    ratio = reactive(0.18)
    intents = reactive(17)
    matched = reactive(2384)

    def render(self) -> str:
        width = 48
        filled = max(1, min(width, int(self.ratio * width)))
        bar = "█" * filled + "░" * (width - filled)
        wave = "".join(SCAN_GLYPHS[(self.frame + i) % len(SCAN_GLYPHS)] for i in range(18))
        radar_radius = 8
        lines: list[str] = []
        sweep = self.frame % 16
        for y in range(-radar_radius, radar_radius + 1):
            row = []
            for x in range(-radar_radius * 2, radar_radius * 2 + 1):
                norm = math.sqrt((x / 2) ** 2 + y**2)
                angle_bucket = (x + radar_radius * 2 + y + sweep) % 16
                if abs(norm - radar_radius) < 0.65:
                    row.append("[green]•[/green]")
                elif norm < radar_radius - 1 and angle_bucket == sweep:
                    row.append("[bold bright_green]▌[/bold bright_green]")
                elif norm < radar_radius - 1 and (x + y + self.frame) % 13 == 0:
                    row.append("[bright_cyan]·[/bright_cyan]")
                else:
                    row.append(" ")
            lines.append("".join(row))
        return (
            "[b bright_green]〔 上帝视角 / Intent Radar 〕[/b bright_green]\n"
            f"[bright_cyan]{wave}[/bright_cyan]\n"
            f"[bold green][{bar}] {self.ratio * 100:05.1f}%[/bold green]   "
            f"[yellow]扫描中意图[/yellow]: [b]{self.intents}[/b]   "
            f"[magenta]已促成撮合[/magenta]: [b]{self.matched}[/b]\n"
            + "\n".join(lines)
        )


class MetricsPanel(Static):
    metrics = reactive(NetworkMetrics())

    def render(self) -> str:
        pulse = "█" * (2 + int(time.time() * 3) % 6)
        m = self.metrics
        return (
            "[b bright_cyan]〔 DePIN 算力网 〕[/b bright_cyan]\n\n"
            f"[bright_green]{pulse:<8}[/bright_green] [white]全网在线盒子[/white]: [b bright_white]{m.boxes_online:,} 台[/b bright_white]\n\n"
            f"[cyan]◉[/cyan] [white]闲置 NPU 算力池[/white]: [b bright_cyan]{m.npu_pool:.2f} PFLOPS[/b bright_cyan]\n\n"
            f"[yellow]¥[/yellow] [white]累计为商户创造被动收益[/white]: [b yellow]¥ {m.passive_income:,}[/b yellow]\n\n"
            f"[magenta]↯[/magenta] [white]实时撮合中订单[/white]: [b magenta]{m.active_intents}[/b magenta]\n\n"
            f"[green]⛓[/green] [white]今日节省平台抽成[/white]: [b green]¥ {m.saved_fees:,}[/b green]\n\n"
            f"[bright_white]C 端 Consumer Agents[/bright_white]: [b]{m.consumer_agents:,}[/b]\n"
            f"[bright_red]热路由负载[/bright_red]: [b]{m.route_heat}%[/b]\n"
            f"[bright_magenta]匿名链路数[/bright_magenta]: [b]{m.anonymous_links:,}[/b]\n"
            f"[bright_green]沙盒博弈轮次[/bright_green]: [b]{m.sandbox_rounds:,}[/b]\n\n"
            "[dim]闲置盒子正在把本地 NPU / OCR / 推理空窗打包进共享网络，边营业边挖收益。[/dim]"
        )


class StatusBar(Static):
    metrics = reactive(NetworkMetrics())

    def render(self) -> str:
        m = self.metrics
        return (
            f"[b bright_green]LIVE[/b bright_green]  "
            f"[cyan]Consumer Agents[/cyan]: {m.consumer_agents:,}  "
            f"[magenta]A2A Matched[/magenta]: {m.matched_trades:,}  "
            f"[yellow]Fee Saved[/yellow]: ¥{m.saved_fees:,}  "
            f"[bright_red]Route Heat[/bright_red]: {m.route_heat}%  "
            f"[bright_magenta]Anon Links[/bright_magenta]: {m.anonymous_links:,}"
        )


class DemoDashboard(App):
    CSS = """
    Screen {
        background: #050b0a;
        color: #d7ffe8;
    }

    #root {
        layout: vertical;
        padding: 1 2;
        background: radial-gradient(#0f2019 0%, #09110f 45%, #040706 100%);
    }

    #titlebar {
        height: 3;
        content-align: center middle;
        color: #c6ffd9;
        background: #091d13;
        border: tall #2cff88;
        margin-bottom: 1;
    }

    #top {
        height: 20;
        border: heavy #25ff83;
        background: #07110d;
        padding: 1 2;
        margin-bottom: 1;
    }

    #bottom {
        height: 1fr;
    }

    #left {
        width: 2fr;
        border: heavy #17ff75;
        background: #06100b;
        margin-right: 1;
        padding: 1;
    }

    #right {
        width: 1fr;
        border: heavy #00d1ff;
        background: #071019;
        padding: 1 2;
    }

    #statusbar {
        height: 3;
        margin-top: 1;
        border: tall #ff5f87;
        background: #12070d;
        content-align: center middle;
    }

    RichLog {
        background: transparent;
        color: #d8ffe7;
    }
    """

    BINDINGS = [("q", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self) -> None:
        super().__init__()
        self.metrics = NetworkMetrics()
        self.orchestrator = MatchOrchestrator() if MatchOrchestrator else None
        self._showcase_offset = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="root"):
            yield Static("[b bright_green]PROJECT CLAW // INVESTOR DEMO // NEURAL MARKET OVERLAY[/b bright_green]", id="titlebar")
            yield GodView(id="top")
            with Horizontal(id="bottom"):
                with Vertical(id="left"):
                    yield Static("[b bright_green]A2A 交易暗网[/b bright_green]  [dim]去平台化撮合 / 即时砍价 / 路由费削减 / 匿名博弈[/dim]")
                    yield RichLog(id="trade_log", highlight=True, wrap=True, markup=True)
                with Vertical(id="right"):
                    yield MetricsPanel(id="metrics")
            yield StatusBar(id="statusbar")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "Project Claw Demo Dashboard"
        self.sub_title = "Dark Market Mesh / DePIN Compute Grid"
        self.query_one(RichLog).write("[bold bright_green]系统启动[/bold bright_green]  [dim]正在接入 A2A 暗网、Sandbox 与 DePIN 算力网…[/dim]")
        self.run_worker(self.scan_loop(), exclusive=False)
        self.run_worker(self.trade_loop(), exclusive=False)
        self.run_worker(self.metrics_loop(), exclusive=False)
        self.run_worker(self.showcase_event_loop(), exclusive=False)

    async def scan_loop(self) -> None:
        god = self.query_one(GodView)
        while True:
            self.metrics.scan_ratio = max(0.08, min(0.98, self.metrics.scan_ratio + random.uniform(-0.05, 0.07)))
            self.metrics.active_intents = max(5, self.metrics.active_intents + random.randint(-2, 3))
            self.metrics.matched_trades += random.randint(0, 3)
            god.frame += 1
            god.ratio = self.metrics.scan_ratio
            god.intents = self.metrics.active_intents
            god.matched = self.metrics.matched_trades
            await asyncio.sleep(0.18)

    async def metrics_loop(self) -> None:
        panel = self.query_one(MetricsPanel)
        status = self.query_one(StatusBar)
        phase = 0.0
        while True:
            phase += 0.23
            self.metrics.boxes_online = max(1200, self.metrics.boxes_online + random.randint(-6, 11))
            self.metrics.npu_pool = max(7.2, self.metrics.npu_pool + math.sin(phase) * 0.06 + random.uniform(-0.03, 0.04))
            self.metrics.passive_income += random.randint(8, 42)
            self.metrics.saved_fees += random.randint(5, 31)
            self.metrics.consumer_agents = max(8600, self.metrics.consumer_agents + random.randint(-18, 33))
            self.metrics.route_heat = max(28, min(99, self.metrics.route_heat + random.randint(-4, 5)))
            self.metrics.anonymous_links = max(4200, self.metrics.anonymous_links + random.randint(3, 21))
            snapshot = NetworkMetrics(
                boxes_online=self.metrics.boxes_online,
                npu_pool=self.metrics.npu_pool,
                passive_income=self.metrics.passive_income,
                scan_ratio=self.metrics.scan_ratio,
                active_intents=self.metrics.active_intents,
                matched_trades=self.metrics.matched_trades,
                saved_fees=self.metrics.saved_fees,
                route_heat=self.metrics.route_heat,
                consumer_agents=self.metrics.consumer_agents,
                sandbox_rounds=self.metrics.sandbox_rounds,
                anonymous_links=self.metrics.anonymous_links,
            )
            panel.metrics = snapshot
            status.metrics = snapshot
            await asyncio.sleep(0.42)

    def _format_showcase_event(self, payload: dict) -> str:
        event_type = str(payload.get("event_type", ""))
        if event_type == "vision_scan":
            snippet = str(payload.get("ocr_snippet") or payload.get("message") or "")[:140]
            self.metrics.active_intents = max(1, self.metrics.active_intents + 1)
            return (
                f"[bold bright_green][👁️ VISION-SCAN][/bold bright_green] "
                f"[white]{snippet}[/white]"
            )
        if event_type == "a2a_handshake":
            seed = str(payload.get("handshake_seed") or payload.get("message") or "")
            digest = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:18]
            self.metrics.anonymous_links += 1
            self.metrics.matched_trades += 1
            return (
                f"[bold bright_magenta][🔗 A2A-HANDSHAKE][/bold bright_magenta] "
                f"[white]Hash:[/white] [magenta]{digest}[/magenta]"
            )
        if event_type == "execute_rpa":
            coords = str(payload.get("coords") or payload.get("message") or "")
            self.metrics.route_heat = min(99, self.metrics.route_heat + 1)
            return (
                f"[bold bright_red][⚡ EXECUTE-RPA][/bold bright_red] "
                f"[white]{coords}[/white]"
            )
        return ""

    async def showcase_event_loop(self) -> None:
        log = self.query_one(RichLog)
        while True:
            try:
                if SHOWCASE_EVENT_FILE.exists():
                    with SHOWCASE_EVENT_FILE.open("r", encoding="utf-8") as f:
                        f.seek(self._showcase_offset)
                        for raw in f:
                            raw = raw.strip()
                            if not raw:
                                continue
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            line = self._format_showcase_event(payload)
                            if line:
                                log.write(line)
                        self._showcase_offset = f.tell()
            except Exception:
                pass
            await asyncio.sleep(0.25)

    async def trade_loop(self) -> None:
        log = self.query_one(RichLog)
        while True:
            if self.orchestrator and random.random() < 0.7:
                item = random.choice(["牛肉面", "麻辣烫", "水饺", "炒饭"])
                merchant = random.choice(MERCHANTS)
                client_id = f"consumer-{random.randint(100, 999)}"
                merchant_id = f"merchant-{random.randint(10, 99)}"
                target = random.choice([12, 13, 14, 15, 16, 17])
                result = await self.orchestrator.run_sandbox(client_id, merchant_id, {"item": item, "target": target})
                rounds = result.get("rounds", [])
                final = result.get("final") or {}
                buyer_alias = result.get("client_alias", "0x??")
                seller_alias = result.get("merchant_alias", "0x??")
                listed = float(rounds[0].get("seller", {}).get("counter", target + random.randint(2, 4))) if rounds else float(target + random.randint(2, 4))
                final_price = float(final.get("agreed_price", listed)) if final else listed
                saved = max(1, int(round(max(0.0, listed - final_price))))
                gift = str(final.get("gift", "") or (rounds[-1].get("seller", {}).get("gift", "") if rounds else ""))
                score = float(final.get("score", rounds[-1].get("score", 0.78) if rounds else 0.78))
                agreement = bool(final.get("agreement", False))
                badge = "AGREEMENT" if agreement else "SANDBOX"
                line = (
                    f"[bold bright_green][{badge}][/bold bright_green] "
                    f"[white]消费者([bright_magenta]{buyer_alias}[/bright_magenta]) 发布需求[/white] "
                    f"[dim]《{item}》[/dim] "
                    f"[cyan]→ 广播 3km[/cyan] "
                    f"[blue]→ 锁定匿名商户 {seller_alias}[/blue] "
                    f"[yellow]→ 映射档口[/yellow] '[bold]{merchant}[/bold]' "
                    f"[magenta]→ 砍价成功[/magenta]: [strike]¥{listed:.0f}[/strike] [bold yellow]→ ¥{final_price:.1f}[/bold yellow] "
                    f"[green](省去平台抽成 ¥{saved})[/green] "
                    f"[bright_cyan]gift={gift or '无'}[/bright_cyan] [dim]score={score:.2f} rounds={len(rounds)}[/dim]"
                )
                self.metrics.sandbox_rounds += len(rounds)
                if final:
                    self.metrics.matched_trades += 1
                log.write(line)
                if rounds:
                    last = rounds[-1]
                    seller = last.get("seller", {})
                    detail = (
                        f"[dim]└─ sandbox trace[/dim] "
                        f"[bright_magenta]{buyer_alias}[/bright_magenta] bid [yellow]¥{last.get('buyer', {}).get('offer', target)}[/yellow] / "
                        f"[bright_cyan]{seller_alias}[/bright_cyan] reply "
                        f"[bold]{'accept' if seller.get('accept') else 'counter'}[/bold] "
                        f"[cyan]¥{seller.get('counter', final_price)}[/cyan]"
                    )
                    log.write(detail)
                await asyncio.sleep(random.uniform(0.45, 0.95))
                continue

            consumer = f"0x{random.randint(16, 255):02X}"
            merchant = random.choice(MERCHANTS)
            item = random.choice(ITEMS)
            persona = random.choice(PERSONAS)
            radius = random.choice([1.5, 2, 3, 5])
            listed = random.choice([15, 16, 18, 19, 22, 24, 26])
            target = max(9, listed - random.randint(1, 5))
            final = max(target, listed - random.randint(2, 4))
            saved = max(1, listed - final)
            confidence = random.randint(84, 99)
            path = random.choice(["低延迟邻域广播", "语义相似链路", "夜间算力套利通道", "社交裂变推荐边"])
            event_type = random.choice(["MATCH", "LOCK", "ROUTE", "CLEAR", "BARGAIN"])

            line = (
                f"[bold bright_green][{event_type}][/bold bright_green] "
                f"[white]消费者([bright_magenta]{consumer}[/bright_magenta] / {persona}) 发布需求[/white] "
                f"[dim]《{item}》[/dim] "
                f"[cyan]→ 广播 {radius}km[/cyan] "
                f"[blue]→ {path}[/blue] "
                f"[yellow]→ 锁定商户[/yellow] '[bold]{merchant}[/bold]' "
                f"[magenta]→ 砍价成功[/magenta]: [strike]¥{listed}[/strike] [bold yellow]→ ¥{final}[/bold yellow] "
                f"[green](省去平台抽成 ¥{saved})[/green] "
                f"[dim]confidence={confidence}%[/dim]"
            )
            log.write(line)
            await asyncio.sleep(random.uniform(0.35, 0.95))


if __name__ == "__main__":
    DemoDashboard().run()
