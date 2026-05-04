# Bedfordshire Lace Designer — Design Specification

## Status
**Spec reviewed five times by user. Updated v0.9.**

---

## Overview

A purpose-built desktop application for designing Bedfordshire bobbin lace pricking patterns.
The user draws lace elements directly using specialized tools — each tool produces the actual
finished lace shape with pinholes in real time. No conversion step. Output is a print-ready
pricking sheet at true physical scale.

---

## Platform

- **Python + PySide6 (Qt)** — decided
- Desktop, offline, self-contained
- Packageable as standalone app via PyInstaller
- Project location: `~/projects/bedfordshire-lace/`

## Dependencies

All third-party libraries must be genuinely open source (not fauxpen). Selection criteria:
project health, update frequency, documentation quality, vulnerability response time,
dependency currency, and contributor policies. This applies to any library added during
development.

| Library | Version | License | Purpose | Health |
|---------|---------|---------|---------|--------|
| PySide6 | 6.10+ | LGPL v3 / GPL v3 | UI framework, canvas, print/PDF output | Excellent — Qt Company backed |
| NumPy | 2.4+ | BSD | Geometric math, bezier sampling, pin spacing | Excellent — NumFOCUS / community |
| Shapely | 2.1+ | BSD (GEOS: LGPL) | Parallel curve offset for trails, polygon ops | Good — community maintained |

---

## Canvas

- Real-world units (mm) throughout
- Zoom, pan, rulers, optional grid overlay
- **Background image import** — locked background layer for tracing existing patterns
- Pin spacing derived from **thread selection** (brand and weight) or entered manually
  (holes/cm or mm between holes)

### Thread Selection and Pin Spacing

The designer selects a thread from a simplified built-in database. The software suggests
a range of appropriate pin spacings for that thread. The designer chooses a value within
that range, or enters a spacing manually. Additional threads can be added to the database
easily in the future.

Initial simplified thread set derived from Van Sciver Thread Selection Chart
(Holly Van Sciver, updated 7/14/19):

| Thread | Weight | Pin Spacing Range (mm) |
|--------|--------|----------------------|
| DMC Pearl 8 | Medium-heavy | 4.2 – 6.4 |
| DMC Pearl 12 | Medium | 3.2 – 4.2 |
| Bockens 35/2 Linen | Medium | 3.2 – 4.2 |
| Bockens 50/2 Linen | Medium-fine | 2.5 – 3.2 |
| Bockens 80/2 Linen | Fine | 2.0 – 2.5 |
| Egyptian Cotton 100 | Fine | 2.0 – 2.5 |
| Fil au Chinois 100 | Very fine | 1.5 – 2.0 |

*(Simplified set — more threads to be added later)*

---

## Layers

1. **Design layer** — lace elements and pinholes
2. **Thread Path layer** — thread simulation overlay (toggle on/off)
3. **Background layer** — imported reference image (locked, non-printing)

---

## User Interface

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  Menu bar  (File / Edit / View / Export)                │
├─────────────────────────────────────────────────────────┤
│  Tool options bar  (context-sensitive for active tool)  │
├──────────┬───────────────────────────┬──────────────────┤
│          │                           │                  │
│  Tool    │                           │  Properties      │
│  bar     │        Canvas             │  panel           │
│  (left)  │                           │  (right)         │
│          │                           │                  │
│          │                    │      │                  │
├──────────┴────────────────────┴──────┴──────────────────┤
│  Horizontal scrollbar                                   │
├─────────────────────────────────────────────────────────┤
│  Status bar  (cursor position in mm / zoom level)       │
└─────────────────────────────────────────────────────────┘
```

A vertical scrollbar runs along the right edge of the canvas.

### Theme and Canvas

- **Light theme** — neutral gray UI chrome, white canvas
- Canvas background: plain white (matches printed output)
- Optional grid overlay (toggle in View menu and properties panel)
- All design elements rendered in black/dark gray on white
- Pinholes: small filled black dots
- Thread path overlay: bright distinct colors per pair, toggled on/off

### Left Toolbar — Tools

Each tool has an icon and a text label beneath it. Tools in order:

| Tool | Label | Shortcut |
|------|-------|----------|
| Select / Move | Select | S |
| Pan / Hand | Pan | H |
| Start Point | Start | — |
| Trail | Trail | T |
| Plait | Plait | P |
| Leaf Tally | Leaf Tally | L |
| Rectangle Tally | Rect Tally | R |
| Bud | Bud | B |
| Cloth Figure (freeform) | Leaf/Circle | C |
| Cloth Figure (circle sub-tool) | Ring | G |

### Tool Options Bar

Appears below the menu bar. Shows options relevant to the currently active tool.
Examples:
- **Trail tool**: starting pair count
- **Bud tool**: connection count
- **Cloth Figure tool**: center treatment (Solid / Open / Ladder)
- **Plait tool**: picot toggle (left / right / none)

### Right Properties Panel

Fixed panel always visible on the right. Divided into three sections:

**1. Element Properties** (top section)
Shows properties of the currently selected element. Updates when selection changes.
- Trail: pair count at selected point, path length
- Bud: connection count (editable — triggers placement dialog)
- Cloth Figure: center treatment selector, density warning if applicable
- Plait: length, picot positions
- Tallies: dimensions

**2. Thread and Scale** (middle section)
- Thread dropdown (simplified Van Sciver database)
- Suggested pin spacing range for selected thread
- Pin spacing input field (mm or holes/cm) — editable manually
- These settings apply to the whole document

**3. Layers** (bottom section)
Three toggle checkboxes — each controls visibility of that layer:
- ☑ Design (elements and pinholes)
- ☑ Thread Paths
- ☑ Background image

### Canvas Navigation

| Action | Method |
|--------|--------|
| Zoom in / out | Scroll wheel |
| Pan | Scrollbars (right and bottom edges) |
| Pan | Pan tool (H) → click-drag canvas |
| Pan | Arrow keys (fine nudge) |
| Fit design to window | Ctrl+Shift+F |
| Zoom to 100% (actual mm) | Ctrl+1 |

### Right-Click Context Menu

Right-clicking on or near a connection point opens a dropdown with five options:
1. Terminate pair
2. Twist
3. Leaf tally in figure
4. Rectangle tally in figure
5. Ladder

---

## Design Elements

### 1. Start Point

**What it is**: An explicit marker indicating where the lace begins. Establishes the
starting position of the work. There is one start point per design.

**How to place**: Click to place on the canvas. Attach the first trail or element to it.

**Pair count**: The start point does not specify pair count — it is the skill of the
lace maker to determine how many pairs to begin with. The start point establishes
location only.

---

### 2. Trail

**What it is**: A ribbon of cloth stitch with one working pair and a variable number of
passive pairs. The working pair travels back and forth across the passives.

**How to draw**: Click and drag a bezier path defining the center line of the trail.

**Live render**: Two parallel offset lines follow the center path. Pinholes appear on
both edges at correct spacing. The pins on either side of the trail are offset from each
other to accommodate the back-and-forth movement of the working pair. Corner pins
generated at turns.

**Width**: Determined by pair count. Width = pair_count × pair_width. The trail's width
updates automatically as elements join or leave throughout the design process — it is
not fixed at the time of drawing. Changes are reflected live as connections are made.

**Starting state**: Designer specifies number of starting pairs when placing the trail.

**Pair management**:
- When a plait, tally, or other element joins the trail: default is to add pairs
  (trail widens)
- Designer right-clicks a connection point to mark it as a termination instead:
  a perpendicular short line symbol appears; pair count decreases; trail narrows
- Pass-through plaits or tallies (enter one side, exit the other) do not change pair
  count or width

**Trail split / join**:
- An explicit **split node** or **join node** is placed on the canvas
- At a split: designer specifies how many pairs go to each branch
- At a join: pair counts of the two incoming trails combine
- Visual: the parallel lines naturally diverge (split) or converge (join) — no extra
  symbol needed

**Path editing**: Drag bezier nodes; both edges and all pinholes update live.

**Future extension — Footside**: The footside is a trail variant with an extra passive
pair separated from the rest by a row of pins. It always appears at the outer edge of
the piece. The architecture will allow adding the footside as a trail subtype in the
future. Not implemented in the first version.

---

### 3. Plait

**What it is**: A braid made with exactly two pairs.

**How to draw**: Click a pinhole on one element, drag to a pinhole on another element.

**Live render**: A single line between connection points (the standard pricking symbol
for a plait). The two-pair structure is tracked internally and reflected in the Thread
Path layer.

**Snap**: Endpoint snaps to nearest compatible pinhole, which may be a pinhole in
another element such as a leaf or trail.

**Picots**: A plait can optionally have picots on one or both sides at any point along
its length. The designer places picot markers on the plait after drawing it. Each picot
adds a pinhole at that position. Picot pinholes are always perpendicular to the plait.

---

### 4. Leaf Tally

**What it is**: A woven leaf shape made with exactly two pairs. Both pairs enter the
tally at the same point (the tip) and exit at the other tip.

**How to draw**: Click-drag to define the center axis and length. The shape of a leaf
tally will be two arcs creating a lens shape.

**Live render**: Lens-shaped outline with a single entry pinhole at the top tip and
exit pinhole at the bottom tip.

**Handles**: Bezier control handles for width and taper.

**Connections**: Typically connects to a plait or trail at each tip.

---

### 5. Rectangle Tally

**What it is**: A woven rectangle made with exactly two pairs. The pairs enter at the
top two corners and exit at the bottom two corners.

**How to draw**: Click-drag to define bounds.

**Live render**: Rectangle with pinholes at the four corners.

**Connections**: Each corner connects to a plait or trail.

**Tally within a figure**: A tally (commonly square) can be incorporated inside a leaf
or cloth figure. This does not add or separate any pairs — it is worked with pairs
already in the figure. Indicated by an annotation symbol placed manually by the designer
(see Annotation Symbols).

---

### 6. Bud

**What it is**: A half-stitch figure, commonly circular. Pairs enter at the top and
the same number exit at the bottom.

**How to draw**: Click-drag to define the circle. When placing the bud, the designer
specifies the total number of connections (incoming + outgoing figures). For example,
three plaits in and three plaits out = 6 connections = 6 pinholes.

**Live render**: Circular outline with pinholes evenly spaced around the perimeter.
The number of pinholes is set by the connection count specified at placement.
Upper semicircle (by y-coordinate) = entry pinholes; lower semicircle = exit pinholes.

**Adjusting connection count**: When the designer changes the connection count in the
properties panel, a dialog prompts them to place each new connection point by clicking
on the bud's perimeter. Existing connections and their attached figures shift to their
new positions to accommodate the change.

**Connections**: Pairs arrive via the end of a tally or a plait. Pairs exit to plaits
or tallies at the bottom.

**Pair count**: Number of pairs entering equals number exiting — no pairs added or
removed inside the bud.

---

### 7. Cloth Figure (Circle and Leaf — single element type)

**What it is**: A cloth stitch figure of any closed shape. Typically leaf-shaped
(Bedfordshire lace is often floral) but can be any shape including a ring (circle).

**How to draw**: Bezier closed shape drawn freehand defining the outer boundary.
The figure defaults to Solid. At any later point the designer may draw a second
bezier closed shape inside the existing figure to define an inner opening. When
an inner boundary is added, the software asks whether the opening is Open or Ladder.
For a circle/ring, a dedicated circle sub-tool draws both the outer and inner
boundaries at once using inner and outer radius values.

**Live render**: Filled closed shape with pinholes around the outer perimeter.
If an inner boundary is present and the opening is Open, pinholes also appear
along the inner boundary.

**Center treatment** — determined by whether an inner boundary exists and whether
it has pinholes:
1. **Solid** — outer boundary only; pinholes on outer edge only (default)
2. **Open** — inner boundary present; pinholes on both outer and inner edges.
   Covers both the classic circle (ring with central hole) and a leaf with a
   central split opening that has interior pins.
3. **Ladder** — inner boundary present but no pinholes on inner edge; the designer
   places a single line annotation across the opening to indicate a working pair
   crosses it. Center treatment can be changed between Open and Ladder at any time
   in the properties panel.

**Adding an opening later**: The designer can start with a Solid figure and add
an inner boundary at any time. The figure updates live when the inner boundary
is drawn. The opening can also be removed later, reverting the figure to Solid.

**Note on implementation**: Solid, Open, and Ladder share the same outer bezier
shape drawing and editing model. Open and Ladder additionally have an inner bezier
boundary. The key distinction is that Open generates pinholes on the inner boundary
while Ladder does not.

**Handles**: Full bezier control handles on both outer and inner boundaries —
adjust length, width, and asymmetry by dragging nodes and tangent handles
independently.

**Pair management**:
- Pairs are added to the figure at entry pinholes as the shape widens
- Pairs are removed at exit pinholes as the shape narrows
- Default: connecting plait or trail adds pairs to the figure
- Designer right-clicks to mark a connection as a termination instead

**Density calculation**:
- As the figure's width changes along its length, the software calculates whether
  cloth stitch density remains consistent
- If the figure widens or narrows too quickly, the software flags the area and
  indicates that pairs should be added or removed to maintain even density
- This is a visual warning indicator, not an automatic change

---

## Annotation Symbols

Markers placed manually by the designer. They do not add pinholes or affect pair
counts — they are working instructions for the lace maker.

All annotation symbols and the "Terminate pair" action are accessed via a
**right-click context menu** with a single dropdown of five options:

| Option | Meaning | Visual | Placement |
|--------|---------|--------|-----------|
| Terminate pair | A pair ends here | Short line perpendicular to the thread | Placed anywhere within the cloth stitch body of a trail or cloth figure (not at a connection point) |
| Twist | A twist in the pair at this point | Line with slashes; one slash per twist | Placed on a plait or trail; a dialog prompts for the number of twists, which determines the number of slashes drawn |
| Leaf tally in figure | A leaf tally worked within a larger figure | Lens shape (two arcs) | Placed within a cloth figure |
| Rectangle tally in figure | A rectangle tally worked within a larger figure | Small rectangle | Placed within a cloth figure |
| Ladder | A split in a cloth figure crossed by a working pair | Single line across the opening | Placed across the inner opening of a cloth figure |

---

## Editing Operations

| Operation | Method |
|-----------|--------|
| Move element | Select tool → drag |
| Reshape trail or cloth figure | Drag bezier nodes; pinholes update live |
| Resize tally or bud | Drag corner/edge handles |
| Adjust leaf tally width/taper | Drag bezier control handles |
| Adjust leaf tally length | Drag endpoints |
| Duplicate element | Ctrl+D |
| Delete element | Delete key |
| Undo / Redo | Ctrl+Z / Ctrl+Y |
| Terminate pair / place annotation | Right-click → dropdown menu (5 options) |

---

## Snapping

- Plait endpoint snaps to nearest compatible pinhole (in any element type)
- Element-to-element snapping (e.g., align two trail edges)
- Optional snap-to-grid

---

## Thread Path Simulation

- Toggle on/off as a separate layer overlay
- Colored lines trace the path of each **pair** (one line per pair, not per thread)
- Shows where pairs are added (incoming plaits/tallies) and terminated (⊥ symbol)
- Each pair gets a distinct color
- Errors highlighted: broken paths, unconnected pinholes, pair count mismatches
- Does not obscure the pricking when overlaid

---

## Technical Definitions

### Pair Width and Trail Width

The physical width of one pair in a trail is determined as follows:

- **Primary**: if the selected thread has a known physical diameter derivable from the
  Van Sciver thread chart, `pair_width = 2 × thread_diameter` (a pair consists of two threads)
- **Fallback**: `pair_width = pin_spacing ÷ 2`

Trail width at any point = `pair_count × pair_width`. The current trail width is
displayed in the properties panel so the designer can see the effect of pair changes.

### Connection Points

A connection is formed when a plait endpoint snaps to a pinhole on another element.
Connections are directional — each has an entry side and an exit side, inferred from
the geometry of the elements involved. Multiple elements may share a single pinhole
(e.g., several plaits and a trail meeting at the same point).
Connections are the edges of the internal pair-flow graph that drives thread simulation
and width calculations.

### Corner Pin Threshold

A corner pin is generated on a trail when the path changes direction by more than
**30°** (measured as the change in tangent angle between adjacent path segments).
This value matches the threshold established and tested in the original Inkscape
extension. It is a fixed value and not user-adjustable.

### Selection Model

- Click an element to select it; its properties appear in the properties panel
- Shift+click to add elements to the selection
- Click-drag on empty canvas to box-select multiple elements
- Operations available on multiple selected elements: move, duplicate, delete
- Individual pinholes are not directly selectable; they move with their parent element

### Snapping Priority

When multiple snap targets are available simultaneously, priority is:

1. Pinhole (highest — always preferred)
2. Element edge
3. Grid (lowest)

The designer cannot override snapping priority, but snapping can be toggled off
entirely via the View menu.

### Error Surfacing

When the thread path simulation detects errors:

- The affected element is **highlighted in red** on the canvas
- The error is **listed in the properties panel** (even when no element is selected,
  a summary of all errors is shown)
- Export and print are **not blocked** by errors — the designer may export at any time
- Errors are re-evaluated automatically whenever the design changes

### Print Precision

Physical scale accuracy (1:1 mm) is achieved as follows:

- Qt's QPrinter is configured with the printer's native DPI and explicit mm-based
  page geometry — no scaling is applied by the print driver
- A **test print target** (a line of known length, e.g. 100mm) is included as an
  optional print option so the designer can verify calibration on their specific printer
- PDF export uses exact mm dimensions with no scaling flags

---

## Output

| Format | Details |
|--------|---------|
| Print | True physical scale (1:1 mm) |
| Export PDF | Print-ready pricking sheet |
| Export SVG | For further editing |
| Save project | JSON — all elements, positions, connections, pair counts |
| Load project | Restore full design from JSON |
