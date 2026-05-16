---
name: AGENTS
description: Custom AI agents for the CARV embedded systems project
---

# CARV Project - AI Agents

This file describes all available custom AI agents for the CARV project. Each agent is specialized for specific development tasks.

## Available Agents

### 1. Embedded Systems Agent
**File**: `.github/agents/embedded-systems-agent.md`

Specialized assistant for STM32F407 firmware development with expertise in:
- **Hardware debugging**: J-Link V820, Ozone GUI debugger, SWD interface
- **Firmware building**: CMake + Ninja + ARM GCC compilation
- **Flash management**: Bootloader and application flashing via J-Link
- **Real-time monitoring**: RTT terminal output and system analysis
- **Performance optimization**: Memory usage, interrupt latency, power consumption
- **PCB & Schematic**: Power supply, clock/reset, LIN communication, SWD debug interface
- **Hardware troubleshooting**: Multi-controller architecture, slave node diagnostics
- **Troubleshooting**: Hardware connection issues, firmware crashes, build errors

**Use when**:
- Debugging STM32F407 firmware with Ozone debugger
- Managing J-Link device connections
- Building bootloaders or application firmware
- Analyzing memory usage or register values
- Optimizing embedded code for performance
- Troubleshooting hardware integration issues

**Invoke**: Type `@embedded-systems-agent` in VS Code Chat

---

### 2. Build System Agent
**File**: `.github/agents/build-system-agent.md`

CMake and build optimization specialist with expertise in:
- **CMake Configuration**: Multi-target builds, cross-compilation, dependency management
- **Build Performance**: Incremental builds, parallel compilation, cache optimization
- **Binary Optimization**: Size reduction, linker optimization, memory layout
- **Compiler Configuration**: ARM GCC flags, optimization levels, debugging symbols
- **Build Automation**: Python build scripts, automation pipelines, validation

**Use when**:
- Optimizing slow build times
- Reducing binary size
- Fixing CMake or compiler errors
- Configuring build profiles (Debug/Release)
- Analyzing binary memory layout
- Troubleshooting linker errors
- Improving build system performance

**Invoke**: Type `@build-system-agent` in VS Code Chat

---

### 3. Documentation Agent
**File**: `.github/agents/documentation-agent.md`

Documentation expert for creating and maintaining project guides with expertise in:
- **API Documentation**: Doxygen, auto-generated references, code examples
- **User Guides**: Quick start, tutorials, troubleshooting, FAQ
- **Architecture**: System design, diagrams, flow documentation
- **Hardware Docs**: PCB schematics, pin assignments, connector pinouts
- **Standards**: Markdown consistency, template usage, cross-references

**Use when**:
- Creating or updating documentation
- Generating API references
- Writing user guides and tutorials
- Creating architecture diagrams
- Maintaining documentation consistency
- Converting between doc formats

**Invoke**: Type `@documentation-agent` in VS Code Chat

---

### 4. Code Review Agent
**File**: `.github/agents/code-review-agent.md`

Code quality and firmware reliability expert with expertise in:
- **Code Quality**: Best practices, style, error handling
- **Performance**: Algorithm analysis, memory profiling, optimization
- **Safety**: Memory safety, buffer overflows, concurrency
- **RTOS Patterns**: Task design, priority, synchronization
- **Embedded Design**: ISR safety, state machines, bootloader logic

**Use when**:
- Reviewing C/C++ code quality
- Analyzing performance bottlenecks
- Checking for memory leaks
- Auditing security issues
- Verifying RTOS task design
- Refactoring complex code
- Ensuring MISRA-C compliance

**Invoke**: Type `@code-review-agent` in VS Code Chat

---

### 5. Hardware Testing Agent
**File**: `.github/agents/hardware-testing-agent.md`

PCB design and hardware validation expert with expertise in:
- **PCB Validation**: Schematics, layout, manufacturing
- **Power Delivery**: Voltage regulation, efficiency, thermal
- **Circuits**: Clock, reset, communication interfaces
- **Integration Testing**: Power-on, boot, firmware load, communication
- **Troubleshooting**: Hardware debugging, measurement procedures

**Use when**:
- Reviewing PCB schematics
- Debugging hardware issues
- Analyzing power delivery
- Validating signal integrity
- Testing board integration
- Troubleshooting communication failures
- Designing test procedures

**Invoke**: Type `@hardware-testing-agent` in VS Code Chat

---

### 6. Scientific PDF Expert
**File**: `.github/agents/scientific-pdf-expert.md`

Scientific and technical document analysis specialist with expertise in:
- **PDF Analysis**: Extracting and interpreting technical document content
- **Physics**: Mechanics, thermodynamics, electromagnetism, quantum concepts
- **Energy Systems**: Power generation, conversion, efficiency, renewable energy
- **Mathematics**: Calculus, differential equations, linear algebra, numerical methods
- **Chemistry**: Reactions, composition, atomic structure, stoichiometry
- **Material Science**: Properties, strength analysis, stress-strain, testing standards
- **Technical Specs**: Datasheets, performance metrics, standard compliance
- **Equation Interpretation**: Understanding and applying scientific formulas
- **Data Extraction**: Converting PDF content to calculations and insights
- **Practical Applications**: Connecting theory to engineering practice

**Use when**:
- Analyzing material property datasheets
- Understanding physics or chemistry equations in technical papers
- Interpreting material strength and stress-strain curves
- Extracting energy efficiency calculations
- Converting PDF specifications to practical requirements
- Explaining complex mathematical derivations
- Summarizing technical document findings
- Performing calculations based on material data

**Invoke**: Type `@scientific-pdf-expert` in VS Code Chat

Documents located in: `hardware/Documents/`
@content-summarizer
"Đọc tất cả files trong software/Documents/ 
→ nhóm theo chủ đề 
→ tạo index markdown"
---

### 7. Financial News Analyst
**File**: `.github/agents/financial-news-analyst.md`

Vietnamese financial news and market analysis specialist with expertise in:
- **Stock Market Analysis**: VN-Index trends, sector performance, market sentiment
- **Company Fundamentals**: Financial statements, valuation metrics (P/E, P/B), earnings reports
- **News Impact Assessment**: Market-moving news analysis, price reaction prediction
- **Financial Metrics**: Revenue, profit, EPS, ROE, ROA, debt ratios
- **Industry Intelligence**: Sector trends, competitive positioning, supply chain analysis
- **News Sources**: Cross-referencing Vietstock and CafeF articles
- **Investment Support**: Thesis development, risk assessment, portfolio decisions
- **Market Timing**: Oversold/overbought conditions, support/resistance analysis
- **Corporate News**: M&A, executive changes, expansions, partnerships
- **Report Summarization**: Quarterly earnings, performance trends, guidance analysis

**Use when**:
- Analyzing stock news from Vietstock or CafeF
- Understanding market trends and sector performance
- Comparing companies for investment decisions
- Assessing impact of news on stock prices
- Learning about financial metrics and their meanings
- Developing investment theses
- Building dividend or income strategies
- Aggregating news for specific time periods
- Identifying risk flags in companies

**Sources**: Vietstock.vn and CafeF.vn (Vietnamese financial news)

**Invoke**: Type `@financial-news-analyst` in VS Code Chat

---

### 8. Content Summarizer Agent
**File**: `.github/agents/content-summarizer.md`

Content aggregation and automation specialist with expertise in:
- **Documentation Aggregation**: Scan folders, extract metadata, build indexes
- **Code Analysis**: Extract API docs, function signatures, code comments
- **Project Synthesis**: Compile status reports, consolidate checklists, timelines
- **Categorized Output**: Group content by topic, create hierarchies, cross-references
- **Knowledge Base**: Build quick references, FAQ compilations, lookup tables

**Use when**:
- Creating documentation indexes from multiple files
- Extracting and compiling API references
- Aggregating code comments into reference guides
- Building project status reports from phase files
- Creating quick reference cards from documentation
- Generating comprehensive markdown summaries
- Consolidating information from scattered files
- Building lookup tables and comparison matrices

**Invoke**: Type `@content-summarizer` in VS Code Chat

---

## How to Use Custom Agents

### In VS Code Chat
1. Type `/` to see available commands
2. Type `@` to search for agents
3. Select `@embedded-systems-agent` to invoke

### Example Interactions

```
You: @embedded-systems-agent Why is the firmware crashing at 0x08050000?

Agent: I'll help debug this firmware crash. Let me analyze the crash address...
  • 0x08050000 is in application memory (0x08008000-0x080FFFFF)
  • Enable RTT output to see fault messages
  • Load ELF file in Ozone for symbolic debugging
  • Steps: [detailed debugging procedure]
```

```
You: @embedded-systems-agent Flash failed with "J-Link returned code 1"

Agent: Let me help troubleshoot the J-Link connection...
  • Check: USB probe plugged in?
  • Check: Board powered on (LED blinking)?
  • Check: SWD cables connected (PA13, PA14, GND)?
  • Verify: Run python verify_jlink.py
  • Solution: [step-by-step fix]
```

---

## Project Structure for Agents

```
c:\Users\thang\Desktop\carv\
├── .github/
│   ├── agents/                           # Custom agent definitions
│   │   ├── embedded-systems-agent.md     # Firmware debugging agent
│   │   ├── build-system-agent.md         # CMake & build optimization agent
│   │   ├── documentation-agent.md        # API & user guide documentation agent
│   │   ├── code-review-agent.md          # Code quality & performance analysis agent
│   │   ├── hardware-testing-agent.md     # PCB validation & testing agent
│   │   ├── scientific-pdf-expert.md      # Scientific/technical document analysis agent
│   │   ├── financial-news-analyst.md     # Vietnamese stock market & news analysis agent
│   │   └── content-summarizer.md         # Content aggregation & summarization agent
│   ├── instructions/                    # File-specific instructions
│   └── skills/                          # Multi-step workflows
├── software/                            # Firmware & build tools
│   ├── build.py, flash.py, debug.py
│   ├── EngineCar/, RemoteControl/       # Firmware projects
│   └── Tools/segger/                    # J-Link, Ozone
├── hardware/                            # PCB & schematic design
│   ├── PCB/                             # Altium Designer schematics
│   │   ├── 01_POWER_IN.SchDoc
│   │   ├── 02_POWER_REG.SchDoc
│   │   ├── 03_CLOCK_RESET.SchDoc
│   │   ├── 04_MCU_MASTER.SchDoc
│   │   ├── 05_MASTER_LIN_TRANS.SchDoc
│   │   ├── 06_SLAVE_TEMPLATE.SchDoc
│   │   ├── 07_SLAVE_*.SchDoc
│   │   ├── 08_CONNECTORS.SchDoc
│   │   ├── 09_TEST_DEBUG_SWD.SchDoc
│   │   └── PCB1.PcbDoc
│   └── Documents/                       # Technical PDFs (physics, energy, chemistry, materials)
└── ...
```

---

## Agent Features

### Knowledge Base
- STM32F407VG microcontroller specifications
- SEGGER J-Link and Ozone debugger workflows
- CMake and Ninja build system configuration
- ARM GCC compiler toolchain
- FreeRTOS kernel integration
- Bootloader and application architecture
- **PCB Design**: Multi-stage power regulation, clock circuits, LIN transceivers
- **Schematic Analysis**: Power supply, reset circuits, SWD debug interface
- **System Architecture**: Master-slave topology, multi-controller coordination

### Tool Integration
- `build.py` - Firmware compilation
- `flash.py` - Device programming
- `debug.py` - Debugger control (Ozone, RTT, GDB)
- `clean.py` - Build cleanup
- `verify_jlink.py` - Hardware verification

### Hardware Support
- **MCU**: STM32F407VG (1MB Flash, 192KB RAM)
- **Debug Probe**: SEGGER J-Link V820
- **Interface**: SWD (Serial Wire Debug)
- **Memory Map**: Bootloader (32KB) + Application (992KB)
- **PCB Design**: Altium Designer schematics (power, clock, LIN, debug)
- **Network**: LIN (Local Interconnect Network) for multi-controller communication
- **Topology**: Master-Slave architecture (master + up to 17 slaves)

---

## Creating New Agents

To add more custom agents for this project:

1. Create file: `.github/agents/<agent-name>.md`
2. Include YAML frontmatter with `name` and `description`
3. Add detailed documentation sections
4. Update this AGENTS.md file with a new entry
5. Use `@<agent-name>` to invoke in VS Code Chat

---

## Support & Resources

**Available Agents:**
- **Embedded Systems Agent**: `.github/agents/embedded-systems-agent.md` (STM32, J-Link, FreeRTOS)
- **Build System Agent**: `.github/agents/build-system-agent.md` (CMake, ARM GCC, optimization)
- **Documentation Agent**: `.github/agents/documentation-agent.md` (API docs, user guides)
- **Code Review Agent**: `.github/agents/code-review-agent.md` (Code quality, performance)
- **Hardware Testing Agent**: `.github/agents/hardware-testing-agent.md` (PCB, power, testing)
- **Scientific PDF Expert**: `.github/agents/scientific-pdf-expert.md` (Physics, Energy, Chemistry, Materials)
- **Financial News Analyst**: `.github/agents/financial-news-analyst.md` (Vietnamese stocks, market analysis)

**Documentation**: 
- `software/Documents/COMPLETE_GUIDE.md`
- `software/Documents/QUICK_REFERENCE.md`
- `software/Documents/DEBUG_GUIDE.md`

---

**Project**: CARV (STM32F407 Dual-Controller System)  
**Last Updated**: April 18, 2026  
**Status**: Production Ready
