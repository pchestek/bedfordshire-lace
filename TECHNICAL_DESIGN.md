# Bedfordshire Lace Designer — Technical Design Document

*Developer reference. Not for user review.*
*April 2026*

---

## 1. Project Structure

```
~/projects/bedfordshire-lace/
├── main.py                   # Entry point
├── requirements.txt          # PySide6, numpy, shapely
├── app/
│   ├── main_window.py        # MainWindow (QMainWindow)
│   ├── canvas.py             # LaceCanvas (QGraphicsView + QGraphicsScene)
│   ├── toolbar.py            # Left tool toolbar
│   ├── tool_options_bar.py   # Context-sensitive options bar
│   ├── properties_panel.py   # Right panel (properties / thread / layers)
│   ├── tools/                # One file per tool
│   │   ├── base_tool.py
│   │   ├── select_tool.py
│   │   ├── pan_tool.py
│   │   ├── start_point_tool.py
│   │   ├── trail_tool.py
│   │   ├── plait_tool.py
│   │   ├── leaf_tally_tool.py
│   │   ├── rect_tally_tool.py
│   │   ├── bud_tool.py
│   │   ├── cloth_figure_tool.py
│   │   └── ring_tool.py
│   ├── elements/             # Element data + graphics items
│   │   ├── base_element.py
│   │   ├── start_point.py
│   │   ├── trail.py
│   │   ├── plait.py
│   │   ├── leaf_tally.py
│   │   ├── rect_tally.py
│   │   ├── bud.py
│   │   └── cloth_figure.py
│   ├── model/
│   │   ├── document.py       # Document: top-level data container
│   │   ├── pinhole.py        # Pinhole data class
│   │   ├── connection.py     # Connection data class
│   │   └── pair_graph.py     # PairGraph: pair-flow network
│   ├── geometry/
│   │   ├── bezier.py         # Bezier sampling and tangent math
│   │   ├── offset.py         # Parallel curve offset (via Shapely)
│   │   └── pinholes.py       # Pinhole placement algorithms
│   ├── simulation/
│   │   └── simulator.py      # Thread path tracing
│   ├── io/
│   │   ├── project_file.py   # JSON save / load
│   │   ├── pdf_export.py     # PDF via QPrinter
│   │   └── svg_export.py     # SVG export
│   └── data/
│       └── threads.json      # Thread database
```

---

## 2. Coordinate System

- **Origin**: top-left of canvas
- **X axis**: increases rightward
- **Y axis**: increases downward (standard screen convention)
- **Internal units**: millimetres (float) throughout all data models
- **Screen units**: pixels, converted at render time

### mm ↔ px Conversion

```python
MM_PER_INCH = 25.4
SCREEN_DPI  = 96          # logical screen DPI
PX_PER_MM   = SCREEN_DPI / MM_PER_INCH   # ≈ 3.7795 px/mm
```

QGraphicsScene uses a transform that maps mm → px. All geometry stored in
the data model is in mm. The transform is applied by the QGraphicsView.

### Print Coordinates

QPrinter is configured with `setPageSize(QPageSize(QPageSize.A4))` and
`setFullPage(False)`. Page margins and element positions are passed in mm
via `QPrinter.setPageMargins()`. No scaling is applied — Qt maps mm → printer
dots internally using the printer's native DPI.

---

## 3. Data Model

### 3.1 Document

The top-level container. One per open file.

```python
@dataclass
class Document:
    version: str                        # "1.0"
    thread_brand: str                   # e.g. "Bockens 50/2 Linen"
    thread_diameter_mm: float | None    # from thread DB; None if unknown
    pin_spacing_mm: float               # user-set or derived
    canvas_width_mm: float
    canvas_height_mm: float
    elements: list[LaceElement]         # ordered; draw order = list order
    connections: list[Connection]
    annotations: list[Annotation]
    background_image_path: str | None
```

### 3.2 Elements

All elements inherit from `LaceElement`:

```python
@dataclass
class LaceElement:
    id: str                   # UUID4, assigned at creation
    element_type: str         # 'trail', 'plait', 'leaf_tally', etc.
    pinholes: list[Pinhole]   # generated; updated on reshape
```

#### Trail

```python
@dataclass
class Trail(LaceElement):
    center_path: list[BezierSegment]   # the drawn center line
    starting_pairs: int
    # Pair count is NOT stored directly; it is computed by PairGraph
    # from starting_pairs + all incoming/outgoing connections along the trail
```

#### Plait

```python
@dataclass
class Plait(LaceElement):
    start_pinhole_id: str
    end_pinhole_id: str
    pair_count: int = 2        # always 2
    picots: list[Picot]
```

#### Leaf Tally

```python
@dataclass
class LeafTally(LaceElement):
    tip_a: Point               # entry tip (mm)
    tip_b: Point               # exit tip (mm)
    width_mm: float            # max width at centre
    taper: float               # 0.0–1.0; controls arc curvature
    # pinholes: one at tip_a, one at tip_b
```

#### Rectangle Tally

```python
@dataclass
class RectTally(LaceElement):
    top_left: Point
    width_mm: float
    height_mm: float
    # pinholes: four corners
```

#### Bud

```python
@dataclass
class Bud(LaceElement):
    center: Point
    radius_mm: float
    connection_count: int      # total connections (in + out)
    # pinholes: connection_count evenly spaced; upper half = entry, lower = exit
```

#### Cloth Figure

```python
@dataclass
class ClothFigure(LaceElement):
    outer_path: list[BezierSegment]    # closed bezier
    inner_path: list[BezierSegment] | None   # None if Solid
    center_treatment: str              # 'solid', 'open', 'ladder'
    # pinholes on outer_path always; on inner_path only if center_treatment == 'open'
```

#### Start Point

```python
@dataclass
class StartPoint(LaceElement):
    position: Point
    # no pinholes; just a visual marker
```

### 3.3 Pinhole

```python
@dataclass
class Pinhole:
    id: str                    # UUID4
    parent_element_id: str
    position: Point            # mm, in document coordinates
    pinhole_type: str          # 'footside', 'headside', 'tip', 'corner',
                               # 'bud_entry', 'bud_exit', 'inner', 'outer'
    connection_ids: list[str]  # may have multiple connections
```

### 3.4 Connection

```python
@dataclass
class Connection:
    id: str
    from_pinhole_id: str
    to_pinhole_id: str
    is_passthrough: bool       # True = pairs don't join/terminate; just route through
    terminate: bool            # True = pair ends here (⊥ symbol shown)
```

### 3.5 Annotation

```python
@dataclass
class Annotation:
    id: str
    annotation_type: str       # 'twist', 'leaf_tally_in_fig', 'rect_tally_in_fig', 'ladder'
    position: Point
    parent_element_id: str
    twist_count: int | None    # for 'twist' only
```

---

## 4. Pair Flow Graph

`PairGraph` computes the pair count at every point in the design. It is
recomputed whenever the design changes (elements added/removed/reshaped,
connections changed). It does not store persistent state — it is derived
from Document on demand.

### 4.1 Graph Structure

- **Nodes**: pinholes where elements meet
- **Edges**: element segments carrying pairs between nodes

### 4.2 Flow Rules

- A plait always carries exactly 2 pairs
- A trail segment between two adjacent connection points carries N pairs,
  where N = starting_pairs + Σ(joining connections) − Σ(terminating/leaving connections)
- Conservation rule at each node: Σ(incoming pairs) = Σ(outgoing pairs),
  unless a pair is explicitly terminated (reduce by 1) or a fresh pair is added
- Violations are flagged as errors

### 4.3 Trail Width Computation

At each point along a trail, the current pair count is known from the graph.

```
pair_width = 2 × thread_diameter_mm          # if thread diameter known
           = pin_spacing_mm / 2              # fallback

trail_width_at_t = pair_count(t) × pair_width
```

The trail's two edge lines are computed as parallel offsets of the center path
at distance ±(trail_width_at_t / 2), which varies along the path.

---

## 5. Key Algorithms

### 5.1 Bezier Sampling (`geometry/bezier.py`)

Dense uniform sampling along a bezier path using arc-length parameterisation.
Returns list of (point, tangent) at each sample. Used for:
- Pinhole placement (sample at pin_spacing intervals)
- Parallel offset input

Ported and adapted from `bedfordshire_lace.py` (original Inkscape extension).

### 5.2 Parallel Curve Offset (`geometry/offset.py`)

Used to generate the two edge lines of a trail from its center path.

```python
import shapely.geometry as sg
import shapely.ops as so

def parallel_offset(path_points, offset_mm, side):
    line = sg.LineString(path_points)
    return line.parallel_offset(offset_mm, side, join_style=2)
    # join_style=2 = mitre (preserves corners)
```

Because trail width varies along the path, the offset is computed in segments
between connection points, each with its own width.

### 5.3 Pinhole Generation (`geometry/pinholes.py`)

#### Trail pinholes
1. Sample center path at arc-length intervals of `pin_spacing_mm`
2. Alternate sample points between left and right offset lines (creates the
   staggered/offset pattern required for cloth stitch)
3. At corners (tangent change > 30°): compute angle bisector and place corner
   pin using bisector geometry (from original Inkscape extension)

#### Cloth figure pinholes (outer)
1. Sample outer bezier boundary at `pin_spacing_mm` intervals

#### Cloth figure pinholes (inner — Open treatment only)
1. Sample inner bezier boundary at `pin_spacing_mm` intervals

#### Leaf tally pinholes
One pinhole at each tip (tip_a, tip_b).

#### Rectangle tally pinholes
Four pinholes at corners (top-left, top-right, bottom-left, bottom-right).

#### Bud pinholes
`connection_count` pinholes evenly spaced around the circle. Angle of first
pinhole = −π/2 (12 o'clock). Pinholes in upper semicircle (y < center.y)
= entry; lower semicircle = exit.

### 5.4 Cloth Figure Density Warning

For each cross-section perpendicular to the figure's axis at interval steps:
1. Measure the figure's width at that cross-section
2. Compute expected pair count: `width / pair_width`
3. Compare to actual pair count from PairGraph
4. If deviation > 20%: flag with visual warning

### 5.5 Leaf Tally Shape (Lens)

Two circular arcs sharing the same two endpoints (tip_a, tip_b). The arc
radius is determined by `width_mm` and `taper`. For a taper value of 0.5:

```
chord = distance(tip_a, tip_b)
sagitta = width_mm / 2
radius = (chord² / (8 × sagitta)) + (sagitta / 2)
```

Both arcs are symmetric about the tip-to-tip axis.

---

## 6. Qt Architecture

### 6.1 Scene / View Setup

```python
scene = QGraphicsScene()
view  = LaceCanvas(scene)      # QGraphicsView subclass

# Set scene transform: 1mm = PX_PER_MM pixels
view.setTransform(QTransform().scale(PX_PER_MM, PX_PER_MM))
```

### 6.2 Graphics Items

Each element has a corresponding `QGraphicsItem` subclass that renders it:
- `TrailItem` — draws two offset edge lines + pinholes
- `PlaitItem` — draws single line
- `LeafTallyItem` — draws lens shape + 2 pinholes
- etc.

Items are re-created from element data whenever the element changes.
No persistent mutable state in graphics items — they are pure renderers.

### 6.3 Tool System

Each tool is a class with these methods:

```python
class BaseTool:
    def mouse_press(self, scene_pos: QPointF, event): ...
    def mouse_move(self, scene_pos: QPointF, event): ...
    def mouse_release(self, scene_pos: QPointF, event): ...
    def key_press(self, event): ...
    def activate(self): ...      # called when tool selected
    def deactivate(self): ...    # called when tool switched
```

During drawing, each tool maintains a temporary `preview_item` (QGraphicsItem)
that updates on every mouse_move. On mouse_release (or double-click for bezier
tools), the preview is converted to a permanent element added to the Document.

### 6.4 Undo / Redo

Implemented via Qt's `QUndoStack`. Each user action that modifies the Document
is wrapped in a `QUndoCommand`. Granularity: one command per logical operation
(e.g., "add trail", "move element", "change pair count"). Drag operations are
a single command (begin on press, finalise on release).

### 6.5 Snapping

On every mouse_move during a tool operation:
1. Check all pinholes within snap_radius (default 3mm): snap to nearest
2. Else check element edges within snap_radius: snap to closest point on edge
3. Else check grid intersections (if grid enabled): snap to nearest
4. Else use raw cursor position

`snap_radius` is fixed at 3mm. This is sufficient for the expected working scales.

---

## 7. Thread Database Schema (`data/threads.json`)

```json
{
  "version": "1.0",
  "threads": [
    {
      "id": "bockens-50-2",
      "brand": "Bockens",
      "name": "50/2 Linen",
      "weight": "medium-fine",
      "diameter_mm": 0.18,
      "pin_spacing_min_mm": 2.5,
      "pin_spacing_max_mm": 3.2
    }
  ]
}
```

Thread diameter values are estimated from standard thread specifications.
Where exact diameter is not known, `diameter_mm` is `null` and the fallback
formula (`pin_spacing / 2`) is used.

---

## 8. Project File Schema (JSON)

```json
{
  "version": "1.0",
  "thread_id": "bockens-50-2",
  "thread_diameter_mm": 0.18,
  "pin_spacing_mm": 3.0,
  "canvas_width_mm": 210,
  "canvas_height_mm": 297,
  "background_image_path": null,
  "elements": [
    {
      "id": "a1b2c3d4-...",
      "type": "trail",
      "starting_pairs": 4,
      "center_path": [
        {"type": "M", "x": 10.0, "y": 10.0},
        {"type": "C", "x1": 20.0, "y1": 10.0,
                      "x2": 30.0, "y2": 20.0,
                      "x": 40.0,  "y": 20.0}
      ],
      "pinholes": [
        {"id": "p1", "position": [10.5, 9.8],
         "type": "footside", "connection_ids": []}
      ]
    }
  ],
  "connections": [
    {
      "id": "c1",
      "from_pinhole_id": "p1",
      "to_pinhole_id": "p2",
      "is_passthrough": false,
      "terminate": false
    }
  ],
  "annotations": [
    {
      "id": "ann1",
      "type": "twist",
      "position": [25.0, 15.0],
      "parent_element_id": "a1b2c3d4-...",
      "twist_count": 2
    }
  ]
}
```

### Versioning

The `version` field enables forward migration. If a future version of the
software opens an older file, it migrates the data structure before loading.
Migration functions are stored in `io/project_file.py` keyed by version string.

---

## 9. Thread Simulation (`simulation/simulator.py`)

### Input
The Document and the computed PairGraph.

### Algorithm
1. Start at the StartPoint element
2. Traverse the pair-flow graph using DFS/BFS
3. For each pair tracked: follow its path through elements in sequence
4. Record the geometric path (sequence of mm coordinates) for each pair
5. Flag any disconnected sub-graphs (orphaned elements) as errors

### Output
A list of `PairPath` objects, each containing:
- A sequence of (Point, element_id) tuples
- A color (assigned sequentially from a fixed palette)

### Rendering
PairPath objects are rendered as polylines on the Thread Paths layer
(QGraphicsScene layer with separate Z-order). Rendered only when the
Thread Paths layer is visible.

---

## 10. Development Stages

### Stage 1 — Application shell
- MainWindow, LaceCanvas, toolbar, properties panel (empty)
- mm coordinate system, zoom (scroll wheel), pan (scrollbars + H tool + arrow keys)
- No elements yet

### Stage 2 — Trail tool
- Trail drawing (bezier path), parallel offset via Shapely, pinhole generation
- Corner detection (30° threshold), staggered pin pattern
- Dynamic width (static for now — pair management in Stage 6)
- Trail renders correctly at physical scale

### Stage 3 — Plait tool
- Single-line render
- Snap to pinholes
- Picot placement

### Stage 4 — Tallies and Bud
- Leaf tally (lens shape, 2 pinholes, bezier handles)
- Rectangle tally (4 corner pinholes)
- Bud (circle, evenly spaced pinholes, connection count dialog)

### Stage 5 — Cloth Figure
- Freeform bezier closed shape
- Outer pinholes
- Inner boundary (Open / Ladder treatment)
- Circle sub-tool (ring tool)

### Stage 6 — Pair management and PairGraph
- Trail split / join nodes
- Pair count tracking along trails
- Dynamic trail width updates
- Pair termination (right-click → terminate)
- Density warning for cloth figures

### Stage 7 — Thread simulation
- PairGraph build and traversal
- Thread path rendering (Thread Paths layer)
- Error highlighting (red canvas + properties panel list)

### Stage 8 — Annotations and remaining tools
- All right-click annotation symbols
- Twist dialog
- Start Point element

### Stage 9 — File I/O and output
- JSON project save / load
- PDF export (1:1 mm, test print target)
- SVG export
- Background image import

### Stage 10 — Polish
- Keyboard shortcuts
- Undo / redo throughout
- Properties panel fully wired
- Thread database dropdown
- Snap toggle
