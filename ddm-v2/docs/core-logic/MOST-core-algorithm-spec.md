# MOST Core Algorithm Specification

> **⚠️ IMMUTABLE REFERENCE DOCUMENT**  
> This document defines the canonical MOST work measurement algorithms based on  
> *MOST® Work Measurement Systems, Fourth Edition* by Kjell B. Zandin (CRC Press, 2021).  
> **No implementation decision may override the definitions, index value tables, or  
> calculation rules stated here.** All software that claims to implement MOST must  
> be validated against this document.

---

**Document Type:** Core Algorithm Canonical Reference  
**Version:** 1.0 — FINAL  
**Date:** 2026-04-17  
**Source:** MOST® Work Measurement Systems, 4th Edition, Kjell B. Zandin, CRC Press 2021  
**Status:** Accepted — Do Not Modify

---

## Table of Contents

1. [Foundational Concepts](#1-foundational-concepts)
2. [Time Units — TMU](#2-time-units--tmu)
3. [The MOST Systems Family](#3-the-most-systems-family)
4. [Universal Calculation Rule](#4-universal-calculation-rule)
5. [BasicMOST System](#5-basicmost-system)
6. [MiniMOST System](#6-minimost-system)
7. [MaxiMOST System](#7-maximost-system)
8. [Simultaneous Motions (SIMO)](#8-simultaneous-motions-simo)
9. [Standard Time vs. Normal Time](#9-standard-time-vs-normal-time)
10. [System Selection Rules](#10-system-selection-rules)
11. [Validation Criteria](#11-validation-criteria)
12. [Test Cases](#12-test-cases)

---

## 1. Foundational Concepts

### 1.1 What MOST Measures

MOST (Maynard Operation Sequence Technique) is a **Predetermined Motion Time System (PMTS)**. It measures **the displacement of objects** — the fundamental unit of manual work. All manual activities consist of objects being moved either:

1. **Freely through space** → analyzed with the General Move Sequence Model
2. **Along a controlled path or while in contact with a surface** → analyzed with the Controlled Move Sequence Model

The use of hand tools and equipment are combinations of the above two types.

### 1.2 Key Definitions

| Term | Definition |
|------|-----------|
| **MOST Analysis** | A complete study of a task consisting of method steps and corresponding sequence models |
| **Activity** | A series of logical events when an object is moved, observed, or treated; begins when operator reaches for object and concludes when object is released or operator returns |
| **Method Step** | A description of one activity; one sequence model per method step |
| **Sequence Model** | A string of parameter letters representing the ordered sub-activities in a method step |
| **Parameter** | A one-character representation of a sub-activity (e.g., A = Action Distance) |
| **Index Value** | A number assigned to each parameter representing the time for that sub-activity |
| **Normal Time** | Time at 100% performance level, no allowances. Result of a MOST analysis |
| **Standard Time** | Normal Time + Allowances. The total allowed time for an average skilled worker |

### 1.3 Performance Level

All MOST index values and times reflect the effort of an **average skilled, trained operator working at an average (100%) performance level** following a prescribed method under normal working conditions. No performance rating is applied when using MOST.

---

## 2. Time Units — TMU

**Time Measurement Units (TMU)** are the time units of MOST, identical to those used in MTM.

| Conversion | Value |
|-----------|-------|
| 1 TMU | = 0.00001 hour |
| 1 TMU | = 0.0006 minute |
| **1 TMU** | **= 0.036 second** |
| 1 hour | = 100,000 TMU |
| 1 minute | = 1,667 TMU |
| 1 second | = 27.8 TMU |

> **Implementation requirement:** The TMU-to-seconds conversion factor is exactly **0.036**. This value must not be changed without explicit business justification documented in an ADR.

---

## 3. The MOST Systems Family

Three systems exist within MOST, each designed for different cycle-time ranges:

| System | Applicable Cycle Time | Typical Applications |
|--------|----------------------|---------------------|
| **MiniMOST** | < 1 minute (highly repetitive) | Electronic assembly, short-cycle production |
| **BasicMOST** | 2–30 minutes (medium cycle) | General manufacturing, retail, distribution, assembly |
| **MaxiMOST** | > 30 minutes (long cycle) | Maintenance, heavy assembly, shipbuilding |

> **All three systems are compatible and produce results at the same 100% performance level. A properly established time standard using any MOST system, MTM, or stopwatch time study will give nearly identical results in TMU.**

---

## 4. Universal Calculation Rule

**This rule applies to ALL sequence models in ALL three MOST systems:**

```
TMU for one method step = (Σ all index values in the sequence model) × 10
```

**Example — General Move:**
```
A6  B6  G1  A1  B0  P3  A0
 6 + 6 + 1 + 1 + 0 + 3 + 0 = 17
17 × 10 = 170 TMU = 6.12 seconds
```

**Example — Controlled Move:**
```
A1  B0  G1  M1  X10  I0  A0
 1 + 0 + 1 + 1 + 10 + 0 + 0 = 13
13 × 10 = 130 TMU = 4.68 seconds
```

**Total analysis time:**
```
Total Normal Time (TMU) = Σ (TMU for each method step × frequency of step)
Total Normal Time (seconds) = Total Normal Time (TMU) × 0.036
```

---

## 5. BasicMOST System

BasicMOST has **four sequence models**:

### 5.1 General Move — A B G A B P A

**Definition:** Used for the spatial movement of an object freely through the air.

**Phases:**
1. **Get** (A-B-G): Reach to the object, perform body motions if needed, gain control
2. **Put** (A-B-P): Move object to destination, perform body motions if needed, place
3. **Return** (A): Return to original position

#### A — Action Distance (mainly horizontal motion)

| Index | Application Rule | Approximate Distance |
|-------|-----------------|---------------------|
| 0 | Within reach, no displacement of trunk | ≤ 5 cm (2 in.) |
| 1 | Within reach; may include short steps or trunk movements | ≤ 15 cm (6 in.) |
| 3 | 1–2 steps or trunk bending/turning | ≤ 60 cm (2 ft) |
| 6 | 3–4 steps | ≤ 120 cm (4 ft) |
| 10 | 5–7 steps | ≤ 210 cm (7 ft) |
| 16 | 8–10 steps | ≤ 300 cm (10 ft) |
| 24 | 11–16 steps | ≤ 480 cm (16 ft) |
| 32 | 17–23 steps | ≤ 690 cm (23 ft) |

> Extended A values (A42, A54, etc.) exist for longer distances and are defined in Figure 3.2 of the source text.

#### B — Body Motion (mainly vertical motion)

| Index | Application Rule |
|-------|-----------------|
| 0 | No body motion |
| 3 | Bend and arise, or sit down / stand up with no obstructions |
| 6 | Bend and arise, or sit down / stand up with obstructions |
| 18 | Climb on/off equipment or crawl through an opening |

#### G — Gain Control

| Index | Application Rule |
|-------|-----------------|
| 0 | Gain control of an object already in hand (touch only) |
| 1 | Simple grasp of one light object ≤ 2.5 kg (5 lb) |
| 3 | Collect, grasp in an obstructed location, or grasp a group of objects |
| 6 | Complex grasp: disengage, weight, orientation, awkward, or fragile |

#### P — Placement

| Index | Application Rule |
|-------|-----------------|
| 0 | Lay aside or toss, no specific target |
| 1 | Simple placement: one hand only, no visual adjustment |
| 3 | Place with adjustments: align to one point or two points within 10 cm |
| 6 | Place with care: align to two points > 10 cm apart or precise assembly |

### 5.2 Controlled Move — A B G M X I A

**Definition:** Used for the movement of an object when it remains in contact with a surface or is attached to another object during the movement (guided/restricted path).

**Phases:**
1. **Get** (A-B-G): Same as General Move
2. **Move/Actuate** (M-X-I): Controlled displacement, optional process time, optional alignment
3. **Return** (A): Return to position

#### M — Move Controlled

**Push/Pull/Turn:**

| Index | Application Rule |
|-------|-----------------|
| 1 | One stage ≤ 30 cm (12 in.), or button/switch/knob |
| 3 | One stage > 30 cm (12 in.), resistance, seat/unseat, high control, or two stages ≤ 60 cm total |
| 6 | Two stages > 60 cm total, or 1–2 steps while pushing |
| 10 | Three to four stages, or 3–5 steps while pushing |
| 16 | Six to nine steps while pushing |

**Crank (circular cranking motions > ½ revolution):**

| Index | Revolutions |
|-------|------------|
| 1 | — (not applicable to crank) |
| 3 | 1 revolution |
| 6 | 2–3 revolutions |
| 10 | 4–6 revolutions |
| 16 | 7–11 revolutions |

> Extended crank values: M24 (12–16 rev), M32 (17–21 rev), M42 (22–28 rev), M54 (29–36 rev). See Figure 3.14.

#### X — Process Time

Time controlled by electronic or mechanical devices, not manual actions.

| Index | Seconds | Minutes | Hours |
|-------|---------|---------|-------|
| 1 | 0.5 | 0.01 | 0.0001 |
| 3 | 1.5 | 0.02 | 0.0004 |
| 6 | 2.5 | 0.04 | 0.0007 |
| 10 | 4.5 | 0.07 | 0.0012 |
| 16 | 7.0 | 0.11 | 0.0019 |
| 24 | 9.5 | 0.16 | 0.0027 |
| 32 | 13.0 | 0.21 | 0.0036 |
| 42 | 17.0 | 0.28 | 0.0047 |
| 54 | 21.5 | 0.36 | 0.0060 |
| 67 | 26.0 | 0.44 | 0.0073 |
| 81 | 31.5 | 0.52 | 0.0088 |
| 96 | 37.0 | 0.62 | 0.0104 |
| 113 | 43.5 | 0.72 | 0.0121 |
| 131 | 50.5 | 0.84 | 0.0141 |
| 152 | 58.0 | 0.97 | 0.0162 |
| 173 | 66.0 | 1.10 | 0.0184 |
| 196 | 74.5 | 1.24 | 0.0207 |
| 220 | 83.5 | 1.39 | 0.0232 |
| 245 | 92.5 | 1.54 | 0.0257 |
| 270 | 102.0 | 1.70 | 0.0284 |
| 300 | 113.0 | 1.88 | 0.0314 |
| 330 | 124.0 | 2.06 | 0.0344 |

> **Implementation note:** X index values are selected by finding the row whose time value is ≥ the observed clock time. The actual clock time is **never** placed directly in the sequence model — only the index value is used.

#### I — Alignment

| Index | Application Rule |
|-------|-----------------|
| 0 | No alignment needed |
| 1 | Align to 1 point (single correcting action) |
| 3 | Align to 2 points ≤ 10 cm (4 in.) apart — both within area of normal vision |
| 6 | Align to 2 points > 10 cm (4 in.) apart — one point outside area of normal vision |

### 5.3 Tool Use — A B G A B P * A B P A

**Definition:** Used for the use of common hand tools (wrench, screwdriver, scissors, etc.) and cognitive processes (reading, inspecting). The `*` position is replaced by the tool action parameter.

**Tool action parameters (the `*` position):**

| Parameter | Activity |
|-----------|---------|
| F | Fasten (tighten a fastener) |
| L | Loosen |
| C | Cut (pliers, scissors, knife) |
| S | Surface Treat (wipe, air-clean, brush-clean) |
| M | Measure (ruler, caliper, micrometer, etc.) |
| R | Record (write, stamp, label) |
| T | Think (read, inspect, calculate) |

> **Tool Use Partial Frequency:** When the same tool action is repeated without releasing the tool, the notation is:  
> `A B G A B P (P A [tool]) A B P A (n)` where `(n)` is the frequency.

#### F/L — Fasten/Loosen (Wrenches, Powered Tools, etc.)

| Index | Application Rule |
|-------|-----------------|
| 3 | 1 wrist stroke (e.g., snap-action wrench) |
| 6 | 2–3 wrist strokes |
| 10 | 4–6 wrist strokes |
| 16 | 7–10 wrist strokes (e.g., box wrench 3–4 repositions) |
| 24 | 11–15 wrist strokes |
| 32 | 16–21 wrist strokes |

> Powered fasteners: Clutch type F3; stall type F6. See Figure 3.20.

#### T — Think (Inspect, Read, Calculate)

| Index | Application Rule |
|-------|-----------------|
| 1 | Read/inspect 1 point (glance) |
| 3 | Read/inspect 2 points or complex label read |
| 6 | Compare 1 dimension or read a complex sequence |
| 10 | Compare 2 dimensions or complex comparative inspection |
| 16 | Compare 3 dimensions or prolonged inspection |

### 5.4 Equipment Use — A B G A B P * A B P A

**Definition:** Used for common administrative activities such as typing, keypad entry, or filing.

| Parameter | Activity |
|-----------|---------|
| W | Keyboard (typing) |
| K | Keypad entry |
| H | Letter/Paper Handling |

---

## 6. MiniMOST System

MiniMOST applies to **short-cycle, highly repetitive operations (< 1 minute cycle time)**. It is the most detailed MOST system and uses the same sequence structure as BasicMOST General and Controlled Move, but with finer-grained index values.

### 6.1 General Move — A B G A B P A

**Key differences from BasicMOST:**

#### A — Action Distance (MiniMOST)

| Index | Application Rule |
|-------|-----------------|
| 0 | Within reach, no trunk displacement, ≤ 5 cm (2 in.) |
| 1 | Within reach, ≤ 15 cm (6 in.), or short step |
| 3 | 30–60 cm (1–2 ft), or 1–2 steps |
| 6 | 60–120 cm (2–4 ft), or 3–4 steps |
| 10 | 120–210 cm (4–7 ft), or 5–7 steps |
| 16 | 210–300 cm (7–10 ft), or 8–10 steps |
| 24 | 300–480 cm (10–16 ft), or 11–16 steps |

#### G — Gain Control (MiniMOST) — "Limiting" concept

MiniMOST introduces the concept of **Limiting or Limited**: when an object is moved, one hand's motion is typically more demanding than the other. Only the **limiting hand's** motion is analyzed.

| Index | Application Rule |
|-------|-----------------|
| 0 | Touch/contact only (no grasp required) |
| 1 | Simple grasp, 1 light object, unobstructed |
| 3 | Grasp with care: collect, obstructed, group, or careful weight/orientation |
| 6 | Disengage with care: peel, cut apart, or complex disengage |

#### Net Weight Consideration (MiniMOST only)

MiniMOST accounts for **Effective Net Weight (ENW)** — the weight that actually loads the operator's muscles. When ENW affects the motion:

| ENW | A or M adjustment |
|-----|-------------------|
| 0–2.25 kg (0–5 lb) | No adjustment |
| 2.25–9 kg (5–20 lb) | Add +1 to A or M index |
| 9–18 kg (20–40 lb) | Add +3 to A or M index |
| > 18 kg (> 40 lb) | Requires further analysis |

#### P — Placement (MiniMOST)

| Index | Application Rule |
|-------|-----------------|
| 0 | Lay aside or toss to general area |
| 1 | Simple placement, no visual guidance |
| 3 | Place with adjustment to 1 or 2 points ≤ 10 cm apart |
| 6 | Precise placement: tight tolerance, fragile, or critical assembly |

**Precise Placement (MiniMOST-specific):** When tolerance < 3 mm or special care is required, additional P values apply:

| Index | Application Rule |
|-------|-----------------|
| 10 | Precise placement to 1 point |
| 16 | Precise placement to 2 or more points, all within area of normal vision |
| 24 | Precise placement to 2 points > 10 cm apart |

### 6.2 Controlled Move — A B G M X I A

MiniMOST Controlled Move uses the same parameters as BasicMOST with identical index logic, but the same Net Weight adjustment for M applies:

| ENW added to grip | M index adjustment |
|-------------------|--------------------|
| 0–2.25 kg | No adjustment |
| 2.25–9 kg | +1 |
| 9–18 kg | +3 |

#### X — Process Time (MiniMOST)

Same index values as BasicMOST (see Section 5.2, X table).

#### I — Alignment (MiniMOST)

Same rules as BasicMOST (see Section 5.2, I table).

### 6.3 Motion Combinations (MiniMOST Simultaneous Guidance)

MiniMOST provides a **Simultaneous Motion Guide** to determine whether two concurrent hand motions can be performed simultaneously (and thus only the limiting one is counted) or must be analyzed sequentially.

**Rule:** If both motions are in the "Easy" category and both involve the same or simpler parameters, they are simultaneous — count only the limiting (more demanding) motion. If either motion is in the "Difficult" category, they are sequential — count both.

> The full Simultaneous Motion Guide table is in Figure 4.27 of the source text.

---

## 7. MaxiMOST System

MaxiMOST applies to **long-cycle operations (> 30 minutes cycle time)** such as maintenance, heavy assembly, and shipbuilding. It uses broader index ranges because small time differences are insignificant at this scale.

### 7.1 Common Parameters A and B

MaxiMOST A and B parameters span larger ranges than BasicMOST:

#### A — Action Distance (MaxiMOST)

| Index | Steps | Distance |
|-------|-------|---------|
| 0 | 0 steps | ≤ 1 m |
| 3 | 1–4 steps | 1–3 m |
| 6 | 5–10 steps | 3–7 m |
| 10 | 11–18 steps | 7–13 m |
| 16 | 19–30 steps | 13–21 m |
| 24 | 31–50 steps | 21–35 m |
| 32 | 51–75 steps | 35–53 m |

#### B — Body Motion (MaxiMOST)

| Index | Application Rule |
|-------|-----------------|
| 0 | No body motion |
| 3 | Bend and arise, or sit/stand (unobstructed) |
| 6 | Bend and arise or sit/stand (obstructed), or crawl |
| 18 | Climb on/off equipment, steps, or ladders (up to 5 rungs) |

### 7.2 Part Handling Sequence Model — A B P

MaxiMOST uses a compressed three-parameter model (not seven) for part handling:

**General Move:** `A B P` (get + put combined into P)  
**Controlled Move:** `A B P` (where P covers controlled moves)

#### P — Part Handling (MaxiMOST General Move)

| Index | Application Rule |
|-------|-----------------|
| 0 | No placement |
| 1 | Simple put aside |
| 3 | Place with minor adjustment |
| 6 | Place with adjustments to one point |
| 10 | Place with adjustments to two or more points |
| 16 | Place with precision (tight fit or heavy part) |

#### P — Part Handling (MaxiMOST Controlled Move)

| Index | Application Rule |
|-------|-----------------|
| 1 | Push/pull one stage ≤ 30 cm, or actuate button/switch |
| 3 | Push/pull one stage > 30 cm, or resistance |
| 6 | 2–9 steps while pushing |
| 10 | 10–18 steps while pushing |
| 16 | 19–30 steps while pushing |

### 7.3 Tool Use Sequence Model — A B T A B A

| Parameter | Activity |
|-----------|---------|
| T | All tool actions (fastener assembly/disassembly, tighten/loosen, cutting, measuring) |

> MaxiMOST T values cover a wide range of tool types. See Figures 5.14–5.41 in the source text for complete index tables by tool type.

### 7.4 Machine Handling Sequence Model — A B M A

| Parameter | Activity |
|-----------|---------|
| M | Operate machine controls or secure/release parts |

---

## 8. Simultaneous Motions (SIMO)

### 8.1 Definition

When two hands perform motions at the **same time** (simultaneously), the total time consumed is that of the **limiting (longer)** motion, not the sum of both.

### 8.2 Grouping Rule

SIMO adjustments are applied at the **method step group level**:
- Steps marked as simultaneous and sharing a `simo_group_id` form a SIMO group
- **Only the maximum TMU within each SIMO group contributes to the total time**
- Non-SIMO steps contribute their full TMU individually

**Formula:**
```
Total SIMO-Adjusted TMU = Σ(non-SIMO step TMU) + Σ(max TMU per SIMO group)
```

### 8.3 SIMO Analysis — BasicMOST Method Level

In BasicMOST, simultaneous motions are analyzed at the "method level" — the analyst identifies which hand is limiting and assigns index values to both hands but counts only the limiting one. The **Simultaneous Motion Guide** in the source text determines whether motions can be performed simultaneously.

**General rule:** Both hands performing simple motions (A, B, G of low index values) simultaneously is allowed. If either hand performs a complex motion (high G, P, or M values), simultaneous operation may not be possible.

---

## 9. Standard Time vs. Normal Time

### 9.1 Normal Time

The direct result of a MOST analysis. Represents the time at 100% performance with **no allowances**.

```
Normal Time (TMU) = Σ(step index sum × 10 × frequency)
Normal Time (seconds) = Normal Time (TMU) × 0.036
```

### 9.2 Allowances

Allowances account for time that cannot be captured in the MOST analysis:
- Personal time (restroom, water)
- Rest time (fatigue recovery)
- Minor unavoidable delays (machine setup, communication)

Allowances are expressed as a **percentage of normal time**. Typical industrial values: 10–20%.

### 9.3 Standard Time Calculation

```
Standard Time (seconds) = Normal Time (seconds) × (1 + Allowance%)
```

**Example:**
```
Normal Time = 28.8 seconds
Allowance = 15%
Standard Time = 28.8 × 1.15 = 33.12 seconds
```

> **The current DDM v2 system outputs Normal Time only. Standard Time is not yet implemented. Any feature claiming to produce "Standard Time" must apply allowances per this formula.**

---

## 10. System Selection Rules

### 10.1 Primary Decision Criterion: Cycle Time

```
Cycle Time < 1 minute   → Use MiniMOST
1 ≤ Cycle Time ≤ 30 min → Use BasicMOST
Cycle Time > 30 minutes  → Use MaxiMOST
```

### 10.2 Secondary Considerations

- **Repetition frequency:** Highly repetitive short-cycle operations benefit from MiniMOST's greater detail and accuracy
- **Measurement effort:** BasicMOST is ~40× faster to apply than MTM-1 (12,000 TMU output per analyst hour vs. 300 TMU/hour for MTM-1)
- **Industry:** Electronics/PCB assembly → MiniMOST; General manufacturing/retail → BasicMOST; Maintenance/shipbuilding → MaxiMOST

### 10.3 Compatibility

All three systems are compatible: a time standard established with MiniMOST, BasicMOST, or MaxiMOST for the same operation will produce **nearly identical TMU values**. System selection affects analyst effort, not result accuracy.

---

## 11. Validation Criteria

The following criteria must be met for any MOST calculation to be considered valid:

### 11.1 Index Value Permissibility

Parameter index values must be drawn from the data card of the selected MOST system. **Arbitrary integer values not appearing in the data card are invalid.**

**BasicMOST permissible index values per parameter:**

| Parameter | Permissible Values |
|-----------|------------------|
| A | 0, 1, 3, 6, 10, 16, 24, 32 (+ extended) |
| B | 0, 3, 6, 18 |
| G | 0, 1, 3, 6 |
| P | 0, 1, 3, 6 |
| M | 0, 1, 3, 6, 10, 16 (+ extended crank/step values) |
| X | 0, 1, 3, 6, 10, 16, 24, 32, 42, 54, 67, 81, 96, 113, 131, 152, 173, 196, 220, 245, 270, 300, 330 |
| I | 0, 1, 3, 6 |
| F/L | 3, 6, 10, 16, 24, 32 |
| T | 1, 3, 6, 10, 16 |

### 11.2 Sequence Model Structure

Each method step must conform to one of the defined sequence model structures. The parameter positions are fixed:

| System | Seq Model | Structure |
|--------|-----------|---------|
| BasicMOST | General Move | A B G A B P A (7 params) |
| BasicMOST | Controlled Move | A B G M X I A (7 params) |
| BasicMOST | Tool Use | A B G A B P [tool] A B P A (11 params) |
| MiniMOST | General Move | A B G A B P A (7 params) |
| MiniMOST | Controlled Move | A B G M X I A (7 params) |
| MaxiMOST | Part Handling | A B P (3 params) |
| MaxiMOST | Tool Use | A B T A B A (6 params) |
| MaxiMOST | Machine Handling | A B M A (4 params) |

### 11.3 Frequency Validation

- Frequency must be ≥ 1
- Fractional frequencies (< 1 occurrence per cycle) are valid MOST notation (e.g., `(0.5)` = once every 2 cycles) but require special handling in TMU calculation

### 11.4 TMU Calculation Correctness

The formula `TMU = (Σ index values) × 10` is invariant across all sequence models and all MOST systems. No deviation is permitted.

### 11.5 Time Conversion Correctness

`seconds = TMU × 0.036` exactly. Do not round this factor.

---

## 12. Test Cases

These test cases constitute the canonical acceptance tests for any MOST calculation engine. All implementations **must** produce these results.

### TC-01: BasicMOST General Move — Walk and Pick Up

**Description:** Walk 3–4 steps to pick up a cap from a low shelf, arise, place the cap on an assembly.

**Sequence:**
```
A6  B6  G1  A1  B0  P3  A0
```

**Calculation:**
```
6 + 6 + 1 + 1 + 0 + 3 + 0 = 17
17 × 10 = 170 TMU
170 × 0.036 = 6.12 seconds
```

**Expected:** `TMU = 170`, `seconds = 6.12`

---

### TC-02: BasicMOST Controlled Move — Press Button to Start Machine

**Description:** Reach within reach to press a button, no body motion, process time ~3.5 seconds.

**Sequence:**
```
A1  B0  G1  M1  X10  I0  A0
```

**Calculation:**
```
1 + 0 + 1 + 1 + 10 + 0 + 0 = 13
13 × 10 = 130 TMU
130 × 0.036 = 4.68 seconds
```

**Expected:** `TMU = 130`, `seconds = 4.68`

---

### TC-03: BasicMOST Tool Use — Use Wrench to Tighten Fastener (3 wrist strokes)

**Description:** Reach wrench, grasp, move to fastener, place, tighten 3 wrist strokes, move wrench, lay aside.

**Sequence:**
```
A1  B0  G1  A1  B0  P3  F10  A1  B0  P1  A0
```

**Calculation:**
```
1 + 0 + 1 + 1 + 0 + 3 + 10 + 1 + 0 + 1 + 0 = 18
18 × 10 = 180 TMU
180 × 0.036 = 6.48 seconds
```

**Expected:** `TMU = 180`, `seconds = 6.48`

---

### TC-04: BasicMOST Tool Use — Inspect Two Points

**Description:** Pick up part, bring to eyes, inspect 2 points, put back on conveyor.

**Sequence:**
```
A1  B0  G1  A1  B0  P0  T3  A1  B0  P1  A0
```

**Calculation:**
```
1 + 0 + 1 + 1 + 0 + 0 + 3 + 1 + 0 + 1 + 0 = 8
8 × 10 = 80 TMU
80 × 0.036 = 2.88 seconds
```

**Expected:** `TMU = 80`, `seconds = 2.88`

---

### TC-05: MiniMOST General Move — Simple Reach and Place (Frequency 3)

**Description:** Reach within reach, grasp one light object, place with minor adjustment. Performed 3 times per cycle.

**Sequence (× 3):**
```
A1  B0  G1  A1  B0  P3  A0
frequency = 3
```

**Calculation:**
```
1 + 0 + 1 + 1 + 0 + 3 + 0 = 6
6 × 10 = 60 TMU per occurrence
60 × 3 = 180 TMU total
180 × 0.036 = 6.48 seconds
```

**Expected:** `TMU per step = 60`, `total TMU = 180`, `total seconds = 6.48`

---

### TC-06: SIMO Adjustment — Two Simultaneous Steps

**Description:** Left hand and right hand simultaneously reach and place objects. Each hand TMU = 60. They share `simo_group_id = "G1"`.

**Calculation:**
```
Step A (Left Hand):  A1 B0 G1 A1 B0 P3 A0 = 6 × 10 = 60 TMU  [is_simo=true, simo_group_id="G1"]
Step B (Right Hand): A1 B0 G1 A1 B0 P3 A0 = 6 × 10 = 60 TMU  [is_simo=true, simo_group_id="G1"]

SIMO group "G1" max TMU = max(60, 60) = 60
Non-SIMO sum = 0
Total SIMO-adjusted TMU = 60
Total SIMO-adjusted seconds = 60 × 0.036 = 2.16
```

**Expected:** `simo_adjusted_total_tmu = 60`, `simo_adjusted_total_seconds = 2.16`

---

### TC-07: Process Time Lookup — X Parameter Conversion

**Description:** A machine process takes exactly 5 seconds. Determine the correct X index.

**Lookup rule:** Find the smallest X index value whose "Seconds" column value is ≥ the observed time.

```
X10 = 4.5 sec  ← less than 5.0, skip
X16 = 7.0 sec  ← 7.0 ≥ 5.0, select X16
```

**Expected X index:** `16`

**Sequence using this value:**
```
A1  B0  G1  M1  X16  I0  A0
1 + 0 + 1 + 1 + 16 + 0 + 0 = 19
19 × 10 = 190 TMU
190 × 0.036 = 6.84 seconds
```

**Expected:** `TMU = 190`, `seconds = 6.84`

---

### TC-08: Standard Time Calculation

**Description:** A MOST analysis produces 800 TMU normal time. Allowance is 15%.

```
Normal Time (TMU) = 800
Normal Time (seconds) = 800 × 0.036 = 28.8 seconds
Standard Time (seconds) = 28.8 × (1 + 0.15) = 28.8 × 1.15 = 33.12 seconds
```

**Expected:** `normal_time_seconds = 28.8`, `standard_time_seconds = 33.12`

---

## Appendix A: Quick Reference — Permitted Index Values by Parameter

```
BasicMOST / MiniMOST:
  A: 0, 1, 3, 6, 10, 16, 24, 32  (+extended for long distances)
  B: 0, 3, 6, 18
  G: 0, 1, 3, 6
  P: 0, 1, 3, 6  (MiniMOST also: 10, 16, 24 for precise placement)
  M: 0, 1, 3, 6, 10, 16  (+extended for steps/crank)
  X: 0, 1, 3, 6, 10, 16, 24, 32, 42, 54, 67, 81, 96, 113, 131, 152, 173, 196, 220, 245, 270, 300, 330
  I: 0, 1, 3, 6
  F/L: 3, 6, 10, 16, 24, 32  (+extended for powered tools)
  T: 1, 3, 6, 10, 16

MaxiMOST:
  A: 0, 3, 6, 10, 16, 24, 32  (+extended)
  B: 0, 3, 6, 18
  P (Part Handling-General): 0, 1, 3, 6, 10, 16
  P (Part Handling-Controlled): 0, 1, 3, 6, 10, 16
  T (Tool Use): varies by tool type — see source Figures 5.14–5.41
  M (Machine Handling): varies — see source Figures 5.43–5.47
```

## Appendix B: TMU Factor Reference

```
1 TMU = 0.036 seconds  (exact, do not round)
1 second = 27.8 TMU    (1 / 0.036)
1 minute = 1,667 TMU
1 hour = 100,000 TMU
```

---

*This document is derived from MOST® Work Measurement Systems, Fourth Edition by Kjell B. Zandin,  
edited by Therese M. Schmidt. CRC Press, 2021. ISBN 978-0-367-34531-0.*  
*MOST® is a registered trademark of Accenture LLP.*
