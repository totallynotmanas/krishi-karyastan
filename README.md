# 🌾 Krishi-Karyastan
### Smart Farming Cooperative: Precision Agriculture & Distributed Sensing Multi-Agent System

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/Architecture-FIPA--ACL%20%7C%20MAS%20%7C%20BDI-green.svg)](#system-architecture)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Krishi-Karyastan** (from Sanskrit *Krishi* = Agriculture, *Karyasthan* = Workstation / Operational Seat) is an autonomous, cooperative Multi-Agent System (MAS) engineered for precision agriculture in distributed, partially observable environments.

---

## 🎯 Case Study & Problem Statement

### The Problem
A single centralized machine cannot simultaneously monitor, irrigate, fertilize, detect pests, and harvest an entire large-scale farm. Physical spatial constraints, localized micro-climates, and sensor ranges dictate that the agricultural environment is **partially observable**.

Instead, the ecosystem deploys multiple specialized, autonomous field agents:
1. **Soil Monitoring Agent**: Patrols sectors, senses localized moisture and NPK nutrient profiles, and detects anomalous conditions.
2. **Irrigation Agent**: Manages water discharge, moisture replenishment, and prevents root flooding.
3. **Fertilizer Agent**: Applies targeted liquid/granular NPK nutrients with carrier fluids.
4. **Pest Detection Agent**: Conducts optical/anomaly scans for early pathogen and weed infestation.
5. **Harvesting Agent**: Evaluates crop maturity and coordinates yields without trampling active fields.

### Course Connections
- **Partially Observable Environments (POMDPs & Local Observability)**: No single physical node has global visibility. Each agent possesses a localized sensor radius $R_{sensor}$. Global situational awareness is constructed collaboratively.
- **Dynamic Knowledge Representation & Belief Fusion**: Agents transmit localized observations using a formal communication protocol to update a dynamic, spatio-temporal Shared Knowledge Base with uncertainty decay ($\lambda$-staleness).
- **Communication Protocol**: Structured FIPA-ACL (Agent Communication Language) performatives (`INFORM`, `CFP`, `PROPOSE`, `ACCEPT_PROPOSAL`, `REJECT_PROPOSAL`, `CONFIRM`).
- **Negotiation Logic & Multi-Constraint Coordination**: When a dry, nutrient-poor patch is flagged, Irrigation and Fertilizer Agents coordinate a targeted, scheduled response:
  1. **Agronomic Saturation Constraint**: Joint moisture contribution must satisfy $M(t) + \Delta M_{irr} + \Delta M_{fert} \le M_{field\_capacity}$ to prevent root rot, anaerobic suffocation, and nutrient leaching.
  2. **Physical Hardware Collision Avoidance**: 4D Spatio-Temporal Reservation Grid $R(x, y, t)$ ensures no two rovers occupy overlapping sectors or conflicting transit corridors.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph PhysicalEnvironment ["🌾 Partially Observable Farm Environment (Sectors & Zones)"]
        S[Sector x, y: Moisture, NPK, Soil Type, Saturation Limit]
    end

    subgraph SensingPhase ["📡 Localized Sensing & Flagging"]
        SMA["🔍 Soil Monitoring Agent<br/>(Local View R_sensor)"] -->|1. Sample Sector| S
        SMA -->|2. INFORM: Update Belief| SKB[("🧠 Shared Knowledge Base<br/>(Dynamic Spatial Beliefs + Decay)")]
        SMA -->|3. SoilDeficiencyAlert<br/>(Moisture & NPK Deficit)| Bus[("📨 FIPA-ACL Message Bus")]
    end

    subgraph NegotiationPhase ["🤝 Bilateral Negotiation & Deconfliction"]
        Bus -->|4. CFP Fertigation| IA["💧 Irrigation Agent"]
        Bus -->|4. CFP Fertigation| FA["🌱 Fertilizer Agent"]
        
        IA <-->|5. Bilateral Negotiation / Joint Proposal| FA
        
        SG["⚖️ Agronomic Saturation Governor<br/>M_curr + ΔM_irr + ΔM_fert ≤ M_sat"] -->|Validate| IA
        SG -->|Validate| FA
        
        CA["🛡️ 4D Spatio-Temporal Grid<br/>Collision Avoidance R(x,y,t)"] -->|Deconflict Paths & Time Windows| IA
        CA -->|Deconflict Paths & Time Windows| FA
    end

    subgraph ActuationPhase ["🚜 Targeted Field Actuation"]
        IA -->|6. Execute Step 1: Pre/Post Irrigation| S
        FA -->|6. Execute Step 2: Precision Nutrient Dosing| S
        S -->|7. Restored Optimal Soil State| SKB
    end
```

---

## 🧩 Key Components

| Component | Module | Description |
| :--- | :--- | :--- |
| **Domain Models** | `krishi_karyastan.core.models` | Strongly typed representations of spatial coordinates, nutrient profiles (NPK), sector states, and agent telemetry. |
| **Farm Environment** | `krishi_karyastan.core.environment` | Discrete 2D grid farm simulator with evaporation, percolation, nutrient uptake, and micro-climates. |
| **Knowledge Base** | `krishi_karyastan.core.knowledge_base` | Spatial blackboard with confidence decay $c(t) = c_0 e^{-\lambda \Delta t}$, Bayesian fusion, and query API. |
| **Protocols & Schemas** | `krishi_karyastan.protocols` | FIPA-ACL messages and typed payloads (`SoilDeficiencyAlert`, `CFPFertigation`, `ReservationRequest`). |
| **Autonomous Agents** | `krishi_karyastan.agents` | BDI-inspired agents: Soil Monitor, Irrigation, Fertilizer, Pest Detector, Harvester. |
| **Saturation Governor** | `krishi_karyastan.negotiation.saturation_governor` | Agronomic constraint solver enforcing field capacity limits and anti-leaching ratios. |
| **Collision Avoidance** | `krishi_karyastan.negotiation.collision_avoidance` | 4D space-time reservation table preventing physical node collisions. |
| **Coordination Engine** | `krishi_karyastan.negotiation.coordination_engine` | Contract Net Protocol (CNP) & bilateral scheduler synchronizing multi-agent operations. |
| **Visual Interfaces** | `krishi_karyastan.ui` | Rich terminal live dashboard and FastAPI interactive web UI for real-time visualization. |

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- Recommended: [`uv`](https://github.com/astral-sh/uv) or standard `pip`

### 1. Installation
```bash
# Clone the repository
git clone https://github.com/totallynotmanas/krishi-karyastan.git
cd krishi-karyastan

# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies in editable mode
uv pip install -e ".[dev]"
```

### 2. Run the Benchmark Simulation (CLI)
Run the canonical case study where a Soil Monitoring Agent flags a dry, nutrient-poor patch, initiating negotiation between Irrigation and Fertilizer agents:
```bash
krishi-cli --scenario dry_nutrient_patch
```

### 3. Run the Web Dashboard
Launch the interactive web-based multi-agent farm monitor:
```bash
krishi-web --port 8000
```
Open your browser at `http://localhost:8000`.

### 4. Run Test Suite
```bash
pytest -v
```

---

## 📜 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
