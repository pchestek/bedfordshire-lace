# Stage 1 Testing Protocol
## Bedfordshire Lace Designer

---

### 1. Launch

- [ ] Run `.venv/bin/python3 main.py` — no errors in terminal
- [ ] Window opens at roughly 1280×820
- [ ] White A4 rectangle visible on gray background
- [ ] Page is fully visible and centered (fit-page runs on startup)

---

### 2. Layout

- [ ] Left toolbar visible with labeled buttons (Select, Pan active; Trail, Plait, etc. grayed out)
- [ ] Tool options bar visible below the menu bar, showing "Select — click to select elements"
- [ ] Properties panel on the right with three tabs: Properties, Thread, Layers
- [ ] Status bar at bottom showing `x: — y: —` and a zoom percentage

---

### 3. Zoom

- [ ] Scroll wheel up → zooms in, centered on cursor position
- [ ] Scroll wheel down → zooms out
- [ ] `=` key (or View → Zoom In) → zooms in
- [ ] `-` key (or View → Zoom Out) → zooms out
- [ ] `0` key (or View → Fit Page) → page fits the window
- [ ] Zoom percentage in status bar updates with each zoom action
- [ ] Zoom does not go below ~10% or above ~5000% (limits enforced)

---

### 4. Pan

- [ ] Scrollbars appear when zoomed in past the window edges; dragging them scrolls
- [ ] Arrow keys scroll the canvas (left/right/up/down)
- [ ] Click Pan button in toolbar → cursor becomes open hand; tool options bar updates
- [ ] Drag canvas while Pan tool is active → canvas scrolls
- [ ] Hold `H` → cursor becomes open hand (temporary pan)
- [ ] Release `H` → cursor returns to arrow (previous tool restored)
- [ ] `Escape` key → returns to Select tool

---

### 5. Toolbar

- [ ] Clicking Select → Select button checked, Pan button unchecked
- [ ] Clicking Pan → Pan button checked, Select button unchecked
- [ ] Grayed-out buttons (Trail, Plait, etc.) cannot be clicked
- [ ] Hovering over active buttons shows tooltip with shortcut key
- [ ] Hovering over disabled buttons shows "coming soon" tooltip

---

### 6. Status bar

- [ ] Moving the cursor over the canvas updates `x:` and `y:` values in mm
- [ ] Coordinates read `0.0 mm, 0.0 mm` at the top-left corner of the white page
- [ ] Coordinates are negative when cursor is in the gray margin area

---

### 7. Menus

- [ ] File menu opens; New/Open/Save/Export items are grayed out; Quit works
- [ ] Edit menu opens; Undo/Redo/Select All are grayed out
- [ ] View → Zoom In / Zoom Out / Fit Page all work (same as keyboard shortcuts)
- [ ] View → Grid and Snap are visible but grayed out
- [ ] Help → About opens a dialog with the application name

---

### 8. Resize

- [ ] Drag window to a larger size → canvas expands, panels stay fixed width
- [ ] Drag window to a smaller size → canvas shrinks; minimum size (~800×600) is enforced
- [ ] After resize, View → Fit Page re-centers the page correctly

---

*Record any failures with a brief description of what you saw instead.*
