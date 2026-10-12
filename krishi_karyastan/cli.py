"""Rich terminal CLI runner and interactive dashboard for Krishi-Karyastan."""

from __future__ import annotations
import sys
import time
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

from krishi_karyastan.core.models import Coordinates
from krishi_karyastan.simulation.scenarios import build_case_study_scenario, build_multi_sector_contention_scenario


console = Console()


def render_farm_grid_table(env, agents, current_tick: int) -> Table:
    """Renders visual ASCII/color representation of the farm sectors and agent positions."""
    table = Table(
        title=f"🌾 Farm Grid (Tick: {current_tick}) - [green]Normal[/green] | [yellow]Moist Deficit[/yellow] | [red]Critical Deficit[/red]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Y \\ X", justify="center", style="bold")
    for x in range(env.width):
        table.add_column(f"X={x}", justify="center", min_width=8)

    agent_locs = {a.position.to_tuple(): a for a in agents.values()}

    agent_icons = {
        "SOIL_MONITOR": "🔍 SMA",
        "IRRIGATION": "💧 IRR",
        "FERTILIZER": "🌱 FRT",
        "PEST_DETECTOR": "🐛 PST",
        "HARVESTER": "🌾 HAR",
    }

    for y in range(env.height):
        row_cells = [f"[bold]{y}[/bold]"]
        for x in range(env.width):
            c = Coordinates(x=x, y=y)
            sector = env.get_sector(c)

            # Determine badge
            content_lines = []
            if (x, y) in agent_locs:
                ag = agent_locs[(x, y)]
                icon = agent_icons.get(ag.agent_type.value, "🤖")
                content_lines.append(f"[bold magenta]{icon}[/bold magenta]")

            # Color code based on moisture & nitrogen
            if sector.moisture_pct < 25.0 or sector.nutrients.nitrogen_ppm < 50.0:
                m_color = "bold red"
            elif sector.moisture_pct < 35.0 or sector.nutrients.nitrogen_ppm < 80.0:
                m_color = "yellow"
            else:
                m_color = "green"

            content_lines.append(f"[{m_color}]M:{sector.moisture_pct:.0f}% N:{sector.nutrients.nitrogen_ppm:.0f}[/{m_color}]")
            cell_str = "\n".join(content_lines)
            row_cells.append(cell_str)

        table.add_row(*row_cells)

    return table


def render_agent_status_table(agents) -> Table:
    """Renders table detailing active agent statuses and payloads."""
    table = Table(title="🤖 Active Cooperative Agents", box=box.SIMPLE_HEAVY)
    table.add_column("Agent ID", style="bold cyan")
    table.add_column("Role", style="bold")
    table.add_column("Position", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Battery", justify="right")

    status_styles = {
        "IDLE": "dim",
        "NAVIGATING": "cyan",
        "SENSING": "blue",
        "ACTUATING": "bold green",
        "NEGOTIATING": "bold yellow",
        "CHARGING": "bold red",
    }

    for a in agents.values():
        st_style = status_styles.get(a.status.value, "white")
        table.add_row(
            a.agent_id,
            a.agent_type.value,
            str(a.position),
            f"[{st_style}]{a.status.value}[/{st_style}]",
            f"{a.battery_pct:.1f}%",
        )
    return table


def render_message_log_table(message_bus, limit: int = 6) -> Table:
    """Renders recent FIPA-ACL inter-agent communications."""
    table = Table(title="📨 Live FIPA-ACL Message Trace", box=box.SIMPLE_HEAVY)
    table.add_column("Tick", justify="right", style="dim")
    table.add_column("Performative", style="bold yellow")
    table.add_column("Sender", style="cyan")
    table.add_column("Receiver", style="magenta")
    table.add_column("Conversation ID", style="dim")

    history = message_bus.get_history(limit=limit)
    if not history:
        table.add_row("-", "NO MESSAGES YET", "-", "-", "-")
    else:
        for m in reversed(history):
            table.add_row(
                str(m.timestamp),
                m.performative.value,
                m.sender,
                m.receiver,
                m.conversation_id[:25],
            )
    return table


def run_simulation(scenario_name: str = "dry_nutrient_patch", max_ticks: int = 30, delay: float = 0.3) -> None:
    """Executes the live terminal simulation runner."""
    console.print("\n🌾 [bold green]KRISHI-KARYASTAN: SMART FARMING MULTI-AGENT COOPERATIVE[/bold green]")
    console.print("[dim]Precision Agriculture & Distributed Sensing Simulation[/dim]\n")

    if scenario_name == "contention":
        engine = build_multi_sector_contention_scenario()
        console.print("[yellow]Loaded Scenario: Multi-Sector Contention[/yellow]")
    else:
        engine = build_case_study_scenario()
        console.print("[yellow]Loaded Scenario: Dry & Nutrient-Poor Patch Case Study (Target: (3, 4))[/yellow]")

    target_c = Coordinates(x=3, y=4)
    init_sector = engine.env.get_sector(target_c)
    baseline_moisture = float(init_sector.moisture_pct)
    baseline_nitrogen = float(init_sector.nutrients.nitrogen_ppm)
    console.print(f"[bold]Initial Target Sector (3, 4) State:[/bold] Moisture={baseline_moisture:.1f}%, Nitrogen={baseline_nitrogen:.1f} ppm\n")

    for tick in range(1, max_ticks + 1):
        engine.step()

        console.clear()
        console.print(f"[bold cyan]Tick {engine.current_tick} / {max_ticks}[/bold cyan]")
        console.print(render_farm_grid_table(engine.env, engine.agents, engine.current_tick))
        console.print(render_agent_status_table(engine.agents))
        console.print(render_message_log_table(engine.message_bus, limit=5))

        if engine.negotiated_schedules:
            sched = engine.negotiated_schedules[-1]
            console.print(Panel(
                f"[bold green]Negotiated Fertigation Agreement Active:[/bold green]\n"
                f"• Target: {sched.target_coords} | Safe Non-Saturated: [bold]{sched.is_safe_non_saturated}[/bold] | Collision-Free: [bold]{sched.is_collision_free}[/bold]\n"
                f"• {sched.fertilizer_agent_id}: Slot [{sched.fertilizer_slot.start_tick}, {sched.fertilizer_slot.end_tick}] (Dose: {sched.nitrogen_dose_g:.1f}g, Carrier: {sched.carrier_fluid_liters:.1f}L)\n"
                f"• {sched.irrigation_agent_id}: Slot [{sched.irrigation_slot.start_tick}, {sched.irrigation_slot.end_tick}] (Net Water: {sched.irrigation_volume_liters:.1f}L)\n"
                f"• Projected Final Moisture: [cyan]{sched.projected_final_moisture_pct:.1f}%[/cyan] (Field Capacity: {sched.saturation_threshold_pct:.1f}%)",
                title="🤝 Coordination Engine Status",
                border_style="green",
            ))

        time.sleep(delay)

        # Check if target patch has been restored
        current_state = engine.env.get_sector(target_c)
        if current_state.moisture_pct >= 45.0 and current_state.nutrients.nitrogen_ppm >= 90.0 and engine.current_tick >= 15:
            console.print("\n✨ [bold green]Target Patch (3, 4) Successfully Remediated![/bold green]")
            break

    final_state = engine.env.get_sector(target_c)
    console.print("\n[bold cyan]═══════════════════════ FINAL CASE STUDY AUDIT ═══════════════════════[/bold cyan]")
    console.print(f"Target Sector (3, 4) Baseline: Moisture={baseline_moisture:.1f}%, Nitrogen={baseline_nitrogen:.1f} ppm")
    console.print(f"Target Sector (3, 4) Final:    Moisture=[bold green]{final_state.moisture_pct:.1f}%[/bold green], Nitrogen=[bold green]{final_state.nutrients.nitrogen_ppm:.1f} ppm[/bold green]")
    console.print(f"Total FIPA-ACL Messages Dispatched: {len(engine.message_bus._history)}")
    console.print(f"Knowledge Base Mapped Sectors: {len(engine.knowledge_base.beliefs)} / {engine.env.width * engine.env.height}")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════════════[/bold cyan]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Krishi-Karyastan Multi-Agent Simulation CLI")
    parser.add_argument("--scenario", choices=["dry_nutrient_patch", "contention"], default="dry_nutrient_patch")
    parser.add_argument("--ticks", type=int, default=22, help="Number of simulation ticks to run")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between ticks in seconds")
    args = parser.parse_args()

    run_simulation(scenario_name=args.scenario, max_ticks=args.ticks, delay=args.delay)


if __name__ == "__main__":
    main()
