# Stage 2 Testing Protocol
## Bedfordshire Lace Designer — Trail Tool

---

### 1. Launch

- [ ] Run `.venv/bin/python3 main.py` — no errors in terminal
- [ ] Window opens full screen
- [ ] White 8½ × 11 page visible on gray background

---

### 2. Toolbar

- [ ] Trail button is now active (not grayed out)
- [ ] Hovering over Trail button shows tooltip with shortcut key **T**
- [ ] Clicking Trail button checks it; Select and Pan buttons uncheck
- [ ] Pressing **T** on the keyboard activates the Trail tool
- [ ] Trail button becomes checked when T is pressed (toolbar stays in sync)
- [ ] Pressing **S** returns to Select tool; Select button becomes checked
- [ ] Pressing **Escape** returns to Select tool

---

### 3. Tool Options Bar

- [ ] When Trail tool is active, options bar shows:
      "Trail — click to add points, double-click to finish"
- [ ] **Starting pairs** spinner is visible, defaulting to **3**
- [ ] Spinner accepts values from **3** to 30 (values below 3 are clamped to 3)
- [ ] When Select or Pan is active, the normal label text reappears

---

### 4. Cursor

- [ ] Cursor changes to a crosshair when Trail tool is active
- [ ] Cursor returns to arrow when switching back to Select

---

### 5. Drawing a Basic Trail

- [ ] Activate Trail tool (T or toolbar button)
- [ ] Click three or four points across the canvas to lay down waypoints
- [ ] A semi-transparent live preview appears after the first click,
      showing two parallel edge lines and pinhole dots
- [ ] A dashed blue line extends from the last placed point to the cursor
      (rubber-band indicator of the next segment)
- [ ] The preview updates smoothly as the mouse moves
- [ ] Double-click to finish — the trail becomes fully opaque and permanent;
      the rubber-band line and preview disappear
- [ ] The finished trail remains on the canvas after switching to Select tool

---

### 6. Trail Geometry

Draw a roughly straight horizontal trail with the default **3 starting pairs** and examine it:

- [ ] Two parallel edge lines run the full length of the trail
- [ ] Pinholes appear as small filled black dots along both edges
- [ ] Pinholes on the left edge and right edge are **staggered** —
      the left-edge pins do not align vertically with the right-edge pins;
      they are offset by approximately half the pin spacing
- [ ] The trail is approximately **4.5 mm wide**
      (3 pairs × 1.5 mm pair-width = 4.5 mm; compare to the 3 mm default pin spacing)
- [ ] Pinholes on the same edge are spaced approximately **3 mm** apart
- [ ] All pinholes lie exactly on the edge lines, even around curves and tight corners
      (no pins floating inside the trail body)

---

### 7. Trail Width Responds to Pair Count

- [ ] Set Starting pairs to **3** (minimum), draw a short trail — narrow trail (~4.5 mm)
- [ ] Set Starting pairs to **8**, draw a short trail — trail is noticeably wider (~12 mm)
- [ ] Width scales roughly proportionally with pair count
- [ ] Try typing **1** or **2** in the spinner — value should clamp/snap back to **3**

---

### 7b. End-Snap (Pinhole Snap)

Draw a finished trail on the canvas, then activate the Trail tool and start a new trail:

- [ ] Move the cursor close to one of the **last few pinholes** on an existing trail's
      edge — an **amber circle** appears around the nearest end pinhole
- [ ] The rubber-band line snaps to that pinhole position (its endpoint jumps to the pin)
- [ ] Moving the cursor away from that area dismisses the amber circle
- [ ] The snap only activates near **end pinholes** (last ~4 pins on each edge side),
      not pinholes in the middle of the trail
- [ ] Clicking while the amber snap is active places the waypoint exactly at the
      snapped pinhole position

---

### 8. Curved Trail

Draw a curved trail (S-shape or arc):

- [ ] Edge lines follow the curve smoothly
- [ ] Pinholes remain evenly spaced along the curved edges
- [ ] Staggering is maintained around the curves
- [ ] No gaps or spikes in the edge lines at moderate curvature

---

### 9. Corner Detection

Draw a trail with a sharp turn (place waypoints to create an angle greater
than 30°):

- [ ] An extra corner pin appears on the outer edge at the bend
- [ ] The corner pin is on the correct side (outside of the turn)
- [ ] Gentle curves with less than a 30° turn do **not** produce extra corner pins

---

### 10. Multiple Trails

- [ ] Draw a second trail on the canvas — both trails are visible simultaneously
- [ ] Draw a third trail — all three remain visible
- [ ] Trails do not interfere with each other visually

---

### 11. Cancellation and Reset

- [ ] Start placing waypoints, then press **Escape** — the in-progress preview
      disappears cleanly; no ghost lines or dots remain on the canvas
- [ ] After cancelling, Trail tool can be activated again and a new trail drawn normally
- [ ] Start placing waypoints, then click **Select** in the toolbar — same clean cancellation

---

### 12. Zoom Interaction

- [ ] Draw a trail, then zoom in — edge lines and pinholes scale correctly;
      lines do not become excessively thick or thin
- [ ] Zoom out to fit page — full trail is visible and proportions look correct
- [ ] Draw a trail while zoomed in — geometry is correct at all zoom levels

---

### 13. Stage 1 Features Still Work

- [ ] Zoom in / out with scroll wheel still works
- [ ] Pan tool (H) still works
- [ ] Arrow keys still scroll the canvas
- [ ] Fit Page (0) still works
- [ ] Status bar still shows cursor coordinates in mm
- [ ] Menus still open; Quit still works

---

*Record any failures with a brief description of what you saw instead.*
