"""CLI commands for hardware layer operations.

Phase 6.1: Click-based CLI for target detection, snapshot management,
and hardware layer inspection.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# Initialize console
console = Console()


# ============================================================================
# CLI Group
# ============================================================================


@click.group()
@click.option("--config", type=click.Path(exists=True), help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """AI_SUPPORT Hardware Layer CLI.

    Commands for target detection, snapshot management, and hardware inspection.
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose


# ============================================================================
# Target Commands
# ============================================================================


@cli.group()
def target():
    """Target management commands."""
    pass


@target.command("detect")
@click.option("--probe-serial", help="Probe serial number")
@click.option("--methods", help="Detection methods (comma-separated)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def target_detect(
    ctx: click.Context,
    probe_serial: Optional[str],
    methods: Optional[str],
    output_json: bool,
) -> None:
    """Detect connected targets."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        # Initialize hardware layer
        config_path = ctx.obj.get("config")
        config = None
        if config_path:
            from .bootstrap import BootstrapConfig
            config = BootstrapConfig(config_file=Path(config_path))

        await init_hardware_layer(config)
        context = get_hardware_context()

        # Parse methods
        method_list = None
        if methods:
            from .auto_detector import DetectionMethod
            method_map = {
                "idcode": DetectionMethod.IDCODE,
                "vid_pid": DetectionMethod.VID_PID,
                "chip_id": DetectionMethod.CHIP_ID,
                "fallback": DetectionMethod.FALLBACK,
            }
            method_list = [method_map[m.strip()] for m in methods.split(",") if m.strip() in method_map]

        # Run detection
        console.print("[yellow]Detecting targets...[/yellow]")
        result = await context.target_detector.detect(
            probe_serial=probe_serial,
            fallback_methods=method_list,
        )

        # Output
        if output_json:
            click.echo(json.dumps({
                "success": result.success,
                "method": result.method.value,
                "confidence": result.confidence,
                "probe_serial": result.probe_serial,
                "probe_type": result.probe_type.value if result.probe_type else None,
                "chip_family": result.chip_description.family.value if result.chip_description else None,
                "part_number": result.chip_description.part_number if result.chip_description else None,
                "detection_time_ms": result.detection_time_ms,
                "warnings": result.warnings,
            }, indent=2))
        else:
            if result.success:
                console.print(f"[green]✓[/green] Target detected!")
                console.print(f"  Method: {result.method.value}")
                console.print(f"  Confidence: {result.confidence:.0%}")
                if result.chip_description:
                    console.print(f"  Chip: {result.chip_description.part_number}")
                    console.print(f"  Family: {result.chip_description.family.value}")
                console.print(f"  Probe: {result.probe_serial or 'unknown'}")
                console.print(f"  Time: {result.detection_time_ms:.1f}ms")
            else:
                console.print("[red]✗[/red] No target detected")
                for warning in result.warnings:
                    console.print(f"  [yellow]Warning:[/yellow] {warning}")

    asyncio.run(run())


@target.command("list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--chip-family", help="Filter by chip family")
@click.pass_context
def target_list(
    ctx: click.Context,
    output_json: bool,
    chip_family: Optional[str],
) -> None:
    """List all registered targets."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        # For now, just show loaded plugins
        plugins = context.plugin_loader.get_loaded_plugins()

        if output_json:
            click.echo(json.dumps({
                "loaded_plugins": plugins,
                "available_plugins": list(context.plugin_loader.list_available_plugins().keys()),
            }, indent=2))
        else:
            table = Table(title="Target Plugins")
            table.add_column("Name", style="cyan")
            table.add_column("Version", style="green")
            table.add_column("Families", style="yellow")

            for plugin_name in plugins:
                plugin = context.plugin_loader.get_plugin(plugin_name)
                if plugin:
                    table.add_row(
                        plugin_name,
                        plugin.metadata.version,
                        ", ".join(plugin.metadata.supported_families[:3]),
                    )

            console.print(table)

    asyncio.run(run())


@target.command("show")
@click.argument("target_name")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def target_show(
    ctx: click.Context,
    target_name: str,
    output_json: bool,
) -> None:
    """Show detailed information about a target."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        # Find plugin for target
        from .extended_models import ChipFamily
        try:
            family = ChipFamily(target_name.upper())
        except ValueError:
            family = None

        plugin = None
        if family:
            plugin = context.plugin_loader.find_plugin_for_chip(family)

        if output_json:
            click.echo(json.dumps({
                "target_name": target_name,
                "plugin": plugin.metadata.to_dict() if plugin else None,
                "capabilities": context.capability_registry.to_dict(),
            }, indent=2))
        else:
            if plugin:
                console.print(f"[green]✓[/green] Plugin found for {target_name}")
                console.print(f"  Name: {plugin.metadata.name}")
                console.print(f"  Vendor: {plugin.metadata.vendor}")
                console.print(f"  Families: {', '.join(plugin.metadata.supported_families)}")
            else:
                console.print(f"[yellow]?[/yellow] No plugin found for {target_name}")

    asyncio.run(run())


# ============================================================================
# Snapshot Commands
# ============================================================================


@cli.group()
def snapshot():
    """Snapshot management commands."""
    pass


@snapshot.command("capture")
@click.argument("target_name")
@click.option("--name", help="Snapshot name")
@click.option("--incremental-from", help="Parent snapshot ID for incremental")
@click.pass_context
def snapshot_capture(
    ctx: click.Context,
    target_name: str,
    name: Optional[str],
    incremental_from: Optional[str],
) -> None:
    """Capture a snapshot of target state."""
    from .bootstrap import init_hardware_layer, get_hardware_context
    from .snapshot_manager import RegisterSnapshot

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        console.print(f"[yellow]Capturing snapshot for '{target_name}'...[/yellow]")

        # Create a mock register snapshot for demo
        registers = RegisterSnapshot(
            r0=0, r1=0, r2=0, r3=0,
            sp=0x20001000,
            lr=0x08001234,
            pc=0x08000500,
        )

        # Capture snapshot
        snap = await context.snapshot_manager.capture(
            target_name=target_name,
            target_id=target_name,
            registers=registers,
            memory_regions=[],
            name=name or f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            incremental_from=incremental_from,
        )

        console.print(f"[green]✓[/green] Snapshot captured!")
        console.print(f"  ID: {snap.snapshot_id}")
        console.print(f"  Name: {snap.name}")
        console.print(f"  Size: {snap.get_total_data_size()} bytes")
        console.print(f"  Time: {snap.capture_time.strftime('%Y-%m-%d %H:%M:%S')}")

    asyncio.run(run())


@snapshot.command("list")
@click.option("--target-id", help="Filter by target ID")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def snapshot_list(
    ctx: click.Context,
    target_id: Optional[str],
    output_json: bool,
) -> None:
    """List all snapshots."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        snapshots = await context.snapshot_manager.list(target_id=target_id)

        if output_json:
            click.echo(json.dumps(snapshots, indent=2, default=str))
        else:
            if not snapshots:
                console.print("[yellow]No snapshots found[/yellow]")
                return

            table = Table(title="Snapshots")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Target", style="green")
            table.add_column("Name", style="yellow")
            table.add_column("Time", style="white")
            table.add_column("Size", style="magenta")

            for snap in snapshots:
                table.add_row(
                    snap["snapshot_id"][:16],
                    snap.get("target_name", "unknown"),
                    snap.get("name", ""),
                    snap.get("capture_time", "")[:19],
                    str(snap.get("file_size", 0)),
                )

            console.print(table)

    asyncio.run(run())


@snapshot.command("restore")
@click.argument("snapshot_id")
@click.argument("target_name")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def snapshot_restore(
    ctx: click.Context,
    snapshot_id: str,
    target_name: str,
    yes: bool,
) -> None:
    """Restore target to snapshot state."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        if not yes:
            if not click.confirm(f"Restore '{target_name}' to snapshot '{snapshot_id}'?"):
                console.print("Aborted.")
                return

        console.print(f"[yellow]Restoring '{target_name}' to snapshot...[/yellow]")

        try:
            success = await context.snapshot_manager.restore(snapshot_id, target_name)
            if success:
                console.print(f"[green]✓[/green] Target restored successfully!")
            else:
                console.print("[red]✗[/red] Restore failed")
        except Exception as e:
            console.print(f"[red]✗[/red] Error: {e}")

    asyncio.run(run())


@snapshot.command("delete")
@click.argument("snapshot_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def snapshot_delete(
    ctx: click.Context,
    snapshot_id: str,
    yes: bool,
) -> None:
    """Delete a snapshot."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        if not yes:
            if not click.confirm(f"Delete snapshot '{snapshot_id}'?"):
                console.print("Aborted.")
                return

        console.print(f"[yellow]Deleting snapshot...[/yellow]")

        deleted = await context.snapshot_manager.delete(snapshot_id)
        if deleted:
            console.print(f"[green]✓[/green] Snapshot deleted!")
        else:
            console.print("[red]✗[/red] Snapshot not found")

    asyncio.run(run())


# ============================================================================
# System Commands
# ============================================================================


@cli.group()
def system():
    """System commands."""
    pass


@system.command("status")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def system_status(
    ctx: click.Context,
    output_json: bool,
) -> None:
    """Show system status."""
    from .bootstrap import init_hardware_layer, get_hardware_context, health_check

    async def run() -> None:
        try:
            await init_hardware_layer()
            context = get_hardware_context()
            health = await health_check()
        except Exception as e:
            health = {"status": "error", "error": str(e)}

        if output_json:
            click.echo(json.dumps(health, indent=2, default=str))
        else:
            status_color = {
                "healthy": "green",
                "degraded": "yellow",
                "error": "red",
            }.get(health.get("status", "unknown"), "white")

            console.print(f"Status: [{status_color}]{health.get('status', 'unknown')}[/{status_color}]")

            if "components" in health:
                table = Table(title="Components")
                table.add_column("Component", style="cyan")
                table.add_column("Status", style="green")

                for name, info in health["components"].items():
                    comp_status = info.get("status", "unknown")
                    status_str = comp_status.upper()
                    table.add_row(name, f"[green]{status_str}[/green]" if comp_status == "healthy" else f"[red]{status_str}[/red]")

                console.print(table)

    asyncio.run(run())


@system.command("plugins")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def system_plugins(
    ctx: click.Context,
    output_json: bool,
) -> None:
    """List available plugins."""
    from .bootstrap import init_hardware_layer, get_hardware_context

    async def run() -> None:
        await init_hardware_layer()
        context = get_hardware_context()

        available = context.plugin_loader.list_available_plugins()
        loaded = context.plugin_loader.get_loaded_plugins()

        if output_json:
            click.echo(json.dumps({
                "available": [m.to_dict() for m in available.values()],
                "loaded": loaded,
            }, indent=2))
        else:
            console.print(f"[green]Loaded plugins ({len(loaded)}):[/green]")
            for name in loaded:
                console.print(f"  • {name}")

            console.print(f"\n[yellow]Available plugins ({len(available)}):[/yellow]")
            for name, metadata in available.items():
                status = "[green]loaded[/green]" if name in loaded else "[dim]available[/dim]"
                console.print(f"  • {name} ({status})")

    asyncio.run(run())


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point."""
    try:
        cli(obj={})
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if ctx := click.get_current_context():
            if ctx.obj.get("verbose"):
                import traceback
                traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
