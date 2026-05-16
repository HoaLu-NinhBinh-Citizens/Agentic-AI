"""
Hardware CLI Commands for AI Agent

Provides CLI commands for hardware-in-the-loop testing:
- hil-test: Run HIL test session
- hil-test-e2e: Run E2E test pipeline
- hil-monitor: Monitor UART/CAN in real-time
- hil-report: Generate HIL test report
- port-list: List available serial ports
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Callable, Optional

from src.infrastructure.hardware import (
    HilAgent,
    UartMonitor,
    UartConfig,
    CanAnalyzer,
    CanConfig,
    HilPhase,
    E2EHILPipeline,
    TestConfig,
    FlashConfig,
    FlashMode,
)


async def handle_hil_test(args) -> int:
    """Handle 'hil-test' command."""
    print("\n" + "=" * 60)
    print("HIL Test - Hardware-in-the-Loop Testing")
    print("=" * 60)

    mode_str = "MOCK" if args.mock else "REAL"
    print(f"Mode: {mode_str}")

    # Create HIL agent
    uart_config = UartConfig(
        port=args.port or "COM3",
        baudrate=args.baud or 115200,
    )

    hil = HilAgent(
        uart_config=uart_config,
        software_root=Path(args.software_root) if args.software_root else Path("main/software"),
        use_mock=args.mock,
        mock_uart=args.mock,
    )

    # Add custom validators from args
    if args.check_hardfault:
        def check_hardfault(msg) -> Optional[str]:
            if "hardfault" in msg.data.lower():
                return f"HARD FAULT: {msg.data[:100]}"
            return None
        hil.add_validator(check_hardfault)

    # Run test
    print(f"\nProject: {args.project}")
    print(f"Port: {uart_config.port} @ {uart_config.baudrate} baud")
    print(f"Duration: {args.duration}s")
    print(f"Flash: {'Yes' if args.flash else 'No (dry-run)'}")
    print()

    result = await hil.run_session(
        project=args.project,
        flash=args.flash,
        duration_seconds=args.duration,
        wait_for_pattern=args.wait_for,
        expected_patterns=args.expect or [],
    )

    # Print result
    print()
    print("=" * 60)
    print("TEST RESULT")
    print("=" * 60)
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Phase: {result.phase.value}")
    print(f"Message: {result.message}")
    print(f"Duration: {result.duration_ms / 1000:.1f}s")
    print(f"Messages: {result.messages_captured}")
    print(f"Errors: {result.errors_detected}")
    print(f"Warnings: {result.warnings_detected}")

    if result.details.get("errors"):
        print("\nErrors:")
        for err in result.details["errors"][:10]:
            print(f"  - {err}")

    if args.export:
        export_path = Path(args.export)
        success = await hil.export_report(result.details.get("session_id", "unknown"), export_path)
        if success:
            print(f"\nReport exported to: {export_path}")

    print("=" * 60)

    return 0 if result.success else 1


async def handle_hil_monitor(args) -> int:
    """Handle 'hil-monitor' command - interactive UART monitoring."""
    print("\n" + "=" * 60)
    print("HIL Monitor - Real-time UART Monitoring")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")

    # Create UART monitor
    config = UartConfig(
        port=args.port or "COM3",
        baudrate=args.baud or 115200,
    )

    monitor = UartMonitor(config)
    can = CanAnalyzer()

    # Setup handlers
    message_count = 0
    error_count = 0
    warning_count = 0

    def on_message(msg):
        nonlocal message_count, error_count, warning_count
        message_count += 1

        ts = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        prefix = f"[{ts}]"

        if msg.is_error:
            error_count += 1
            print(f"{prefix} [ERROR] {msg.data}")
        elif msg.is_warning:
            warning_count += 1
            print(f"{prefix} [WARN]  {msg.data}")
        else:
            print(f"{prefix} [INFO]  {msg.data}")

        # Check for CAN messages in UART output
        can_msg = can.parse_uart_can_line(msg.data)
        if can_msg:
            can.add_message(can_msg)
            if args.show_can:
                print(f"       [CAN] {can_msg.get_summary()}")

        # Status update
        if message_count % 100 == 0:
            print(f"\n[STATUS] Messages: {message_count} | Errors: {error_count} | Warnings: {warning_count}\n", end="")

    def on_error(msg):
        nonlocal error_count
        error_count += 1
        ts = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [ERROR] {msg.data}")

    monitor.on_message(on_message)
    monitor.on_error(on_error)

    # Connect and start
    if not await monitor.connect():
        print(f"ERROR: Failed to connect to {config.port}")
        return 1

    await monitor.start_monitoring()

    print(f"Monitoring {config.port} @ {config.baudrate} baud...")
    print()

    try:
        # Wait with status updates
        while True:
            await asyncio.sleep(1)

            stats = await monitor.get_stats()
            print(f"\r[STATUS] Bytes: {stats['bytes_received']} | Lines: {stats['lines_received']} | Errors: {stats['errors_detected']} | Warnings: {stats['warnings_detected']}", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\nStopping monitor...")

    finally:
        await monitor.stop_monitoring()
        await monitor.disconnect()

        # Print summary
        print()
        print("=" * 60)
        print("MONITOR SUMMARY")
        print("=" * 60)
        print(f"Total messages: {message_count}")
        print(f"Errors: {error_count}")
        print(f"Warnings: {warning_count}")
        print(f"CAN messages: {can._stats['total_messages']}")
        print("=" * 60)

        # Export if requested
        if args.export:
            export_path = Path(args.export)
            await monitor.export(export_path, format="txt")
            print(f"Log exported to: {export_path}")

            if args.export_can:
                can_export = Path(args.export_can)
                await can.export(can_export, format="csv")
                print(f"CAN log exported to: {can_export}")

    return 0


async def handle_hil_report(args) -> int:
    """Handle 'hil-report' command."""
    hil = HilAgent()

    report = await hil.generate_report(args.session)
    if "error" in report:
        print(f"ERROR: {report['error']}")
        return 1

    print("\n" + "=" * 60)
    print("HIL TEST REPORT")
    print("=" * 60)
    print(f"Session: {report.get('session_id')}")
    print(f"Project: {report.get('project')}")
    print(f"Status: {report.get('status')}")
    print(f"Duration: {report.get('duration_seconds', 0):.1f}s")

    uart = report.get('uart_stats', {})
    print(f"\nUART Stats:")
    print(f"  Messages: {uart.get('lines_received', 0)}")
    print(f"  Errors: {uart.get('errors_detected', 0)}")
    print(f"  Warnings: {uart.get('warnings_detected', 0)}")

    can = report.get('can_stats', {})
    print(f"\nCAN Stats:")
    print(f"  Messages: {can.get('total_messages', 0)}")
    print(f"  Unique IDs: {can.get('unique_ids', 0)}")

    if report.get('errors'):
        print(f"\nErrors ({len(report['errors'])}):")
        for e in report['errors'][:10]:
            print(f"  - {e}")

    if report.get('warnings'):
        print(f"\nWarnings ({len(report['warnings'])}):")
        for w in report['warnings'][:10]:
            print(f"  - {w}")

    print(f"\nRecent Messages ({len(report.get('recent_messages', []))}):")
    for m in report['recent_messages'][-20:]:
        print(f"  {m}")

    # Export if requested
    if args.export:
        export_path = Path(args.export)
        success = await hil.export_report(args.session, export_path, format=args.format)
        if success:
            print(f"\nReport exported to: {export_path}")

    print("=" * 60)
    return 0


async def handle_hil_test_e2e(args) -> int:
    """Handle 'hil-test-e2e' command - E2E test pipeline."""
    print("\n" + "=" * 60)
    print("E2E HIL Test Pipeline")
    print("=" * 60)

    # Configure flash mode
    flash_config = FlashConfig(
        mode=FlashMode(args.flash_mode),
        jlink_device=args.jlink_device,
        jlink_interface=args.jlink_interface,
        jlink_speed=args.jlink_speed,
    )

    # Create test config
    config = TestConfig(
        project_name=args.project,
        software_root=Path(args.software_root) if args.software_root else Path("main/software"),
        uart_port=args.port,
        uart_baudrate=args.baud,
        flash_config=flash_config,
        monitor_duration=args.duration,
        expected_patterns=args.expect or [],
        use_mock=args.mock,
        mock_uart=args.mock,
    )

    print(f"\nMode: {'MOCK' if args.mock else args.flash_mode.upper()}")
    print(f"Project: {args.project}")
    print(f"UART Port: {args.port}")
    print(f"Flash Mode: {args.flash_mode}")
    if args.flash_mode == "real":
        print(f"J-Link Device: {args.jlink_device}")
    print(f"Duration: {args.duration}s")
    print()

    # Run pipeline
    pipeline = E2EHILPipeline(config)
    result = await pipeline.run()

    # Print result
    print()
    print("=" * 60)
    print("TEST RESULT")
    print("=" * 60)
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Phase: {result.phase.value}")
    print(f"Message: {result.message}")
    print(f"Duration: {result.duration_ms / 1000:.1f}s")
    print(f"UART Lines: {len(result.uart_lines)}")
    print(f"Errors: {len(result.errors_detected)}")

    if result.errors_detected:
        print("\nErrors:")
        for err in result.errors_detected[:10]:
            print(f"  - {err}")

    if result.uart_lines:
        print(f"\nUART Output (last 20 lines):")
        for line in result.uart_lines[-20:]:
            print(f"  {line}")

    print("=" * 60)

    return 0 if result.success else 1


async def handle_port_list(args) -> int:
    """Handle 'port-list' command."""
    ports = UartMonitor.list_ports()

    print("\nAvailable Serial Ports:")
    print("=" * 60)

    if not ports:
        print("No ports found")
        return 1

    for p in ports:
        print(f"  {p['port']}: {p['description']}")
        if args.verbose and p.get('hwid'):
            print(f"         HWID: {p['hwid']}")

    print("=" * 60)
    print(f"Found {len(ports)} port(s)")

    # Auto-detect STM32
    auto = UartMonitor.auto_detect_port()
    if auto:
        print(f"\nAuto-detected STM32 on: {auto}")

    return 0


def run_cli():
    """Run hardware CLI."""
    parser = argparse.ArgumentParser(
        description="AI Agent - Hardware-in-the-Loop Testing",
        prog="python -m src.application.api.app.hardware_cli",
    )
    parser.add_argument("--project", default="EngineCar", help="Project name")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # hil-test command
    p_test = subparsers.add_parser("hil-test", help="Run HIL test session (uses HilAgent)")
    p_test.add_argument("--project", default="EngineCar", help="Project name")
    p_test.add_argument("--port", default="COM3", help="UART port")
    p_test.add_argument("--baud", type=int, default=115200, help="Baudrate")
    p_test.add_argument("--duration", type=int, default=10, help="Test duration (seconds)")
    p_test.add_argument("--flash", action="store_true", help="Flash firmware before test")
    p_test.add_argument("--no-flash", action="store_true", help="Skip flash (dry-run)")
    p_test.add_argument("--wait-for", default=None, help="Wait for pattern before timing")
    p_test.add_argument("--expect", action="append", help="Expected pattern (can repeat)")
    p_test.add_argument("--check-hardfault", action="store_true", help="Check for HardFault")
    p_test.add_argument("--export", default=None, help="Export report to file")
    p_test.add_argument("--software-root", default="main/software", help="Software root directory")
    p_test.add_argument("--mock", action="store_true", help="Use mock UART (no hardware)")
    p_test.set_defaults(func=handle_hil_test)

    # hil-monitor command
    p_mon = subparsers.add_parser("hil-monitor", help="Monitor UART in real-time")
    p_mon.add_argument("--port", default="COM3", help="UART port")
    p_mon.add_argument("--baud", type=int, default=115200, help="Baudrate")
    p_mon.add_argument("--show-can", action="store_true", help="Show parsed CAN messages")
    p_mon.add_argument("--export", default=None, help="Export log to file")
    p_mon.add_argument("--export-can", default=None, help="Export CAN messages to file")
    p_mon.set_defaults(func=handle_hil_monitor)

    # hil-report command
    p_rep = subparsers.add_parser("hil-report", help="Generate HIL test report")
    p_rep.add_argument("session", help="Session ID")
    p_rep.add_argument("--export", default=None, help="Export report to file")
    p_rep.add_argument("--format", default="txt", choices=["txt", "json"], help="Export format")
    p_rep.set_defaults(func=handle_hil_report)

    # hil-test-e2e command
    p_e2e = subparsers.add_parser("hil-test-e2e", help="Run E2E test pipeline (build + flash + monitor)")
    p_e2e.add_argument("--project", default="EngineCar", help="Project name")
    p_e2e.add_argument("--port", default="COM9", help="UART port")
    p_e2e.add_argument("--baud", type=int, default=115200, help="Baudrate")
    p_e2e.add_argument("--duration", type=float, default=10.0, help="Monitor duration (seconds)")
    p_e2e.add_argument("--flash-mode", default="dry_run", choices=["real", "dry_run", "mock"],
                        help="Flash mode")
    p_e2e.add_argument("--jlink-device", default="STM32F407VG", help="J-Link device name")
    p_e2e.add_argument("--jlink-interface", default="SWD", choices=["SWD", "JTAG"], help="J-Link interface")
    p_e2e.add_argument("--jlink-speed", type=int, default=4000, help="J-Link speed (kHz)")
    p_e2e.add_argument("--expect", action="append", help="Expected pattern (can repeat)")
    p_e2e.add_argument("--mock", action="store_true", help="Use mock mode (no hardware)")
    p_e2e.add_argument("--software-root", default="main/software", help="Software root directory")
    p_e2e.set_defaults(func=handle_hil_test_e2e)

    # port-list command
    p_port = subparsers.add_parser("port-list", help="List available serial ports")
    p_port.add_argument("-v", "--verbose", action="store_true", help="Show verbose info")
    p_port.set_defaults(func=handle_port_list)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run async command
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(run_cli())