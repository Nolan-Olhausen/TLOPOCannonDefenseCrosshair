# Cannon Defense Crosshair Overlay

This tool adds a transparent, click-through aiming overlay for Cannon Defense in TLOPO.

It tracks vertical cannon movement while RMB is held and draws:
- a center reticle (red circle)
- optional section-zone overlays (colored rectangles)
- optional right-side drop-line attachment (horizontal + 3 vertical markers)

The system uses two branch profiles (`Top Start` and `Bottom Start`) because camera priming/state changes can alter where shots land.

## Quick Start

1. Start Cannon Defense.
2. Run the script.
3. Click **Find game window**.
4. Move cannon all the way up or all the way down once to **prime** camera angle.

If crosshair alignment drifts (while stationary aim no longer matches splash location), re-prime camera angle again.

## Recommended Usage Notes

- The included `crosshair_settings.json` values are a recommended baseline.
- You can tune live, then click:
  - **Apply to running overlay** (immediate runtime update)
  - **Save settings.json** (persist changes)
- Optional right-side drop line is available, but has not been thoroughly built/configured, more of an idea I tried, but did not like afterall.

## Overlay Components

- **Reticle (red circle)**: current predicted cannon vertical aim point.
- **Section overlays (colored rectangles)**:
  - Show active vertical sensitivity zones.
  - Colors change by active branch so you can tell which profile is in effect.
  - Drawn as a narrowed center band (not full-screen width).
- **Right-side drop line (optional)**:
  - A horizontal line extending from the reticle’s right side.
  - Three vertical crossing lines for holdover/travel-time references.
  - Entire assembly can be rotated around reticle center.

## Why the Branch System Exists

A single profile was not enough because aim behavior differs depending on camera state/priming direction.

So there are two independently tunable profiles:
- **Bottom Start branch**
- **Top Start branch**

Each branch has:
- its own section sensitivities
- its own section splits
- its own trigger range

When aim ratio moves from outside into a branch trigger range, that branch becomes active.

## Controls and Field Reference

### Core / global

- **Starting point (`vertical_anchor_ratio`)**  
  Anchor ratio used for initializing/resetting vertical aim.

- **Clamp endpoint min/max ratio (`vertical_aim_min_ratio`, `vertical_aim_max_ratio`)**  
  Vertical operating limits of the crosshair system.

- **`vertical_raw_scale`**  
  Base movement gain from raw mouse input.

- **Baseline client height (`vertical_baseline_client_height`)**  
  Reference client height used for normalization so movement scales across window sizes.

- **Show section rectangles on overlay (`vertical_section_overlay`)**  
  Enables/disables colored section zone drawing.

### Bottom Start branch fields

- **Bottom branch sensitivity (top/middle/bottom)**  
  Section sensitivities used when Bottom Start branch is active.

- **Bottom branch split (top|middle), split (middle|bottom)**  
  Boundaries between the three bottom-branch sections (0.0 to 1.0).

- **Bottom branch trigger min/max**  
  Ratio range that activates Bottom Start branch when entered from outside.

### Top Start branch fields

- **Top branch sensitivity (top/middle/bottom/4th lower bottom)**  
  Top branch has 4 sections (extra lower section).

- **Top branch split (top|middle), split (middle|bottom), split (bottom|4th lower)**  
  Boundaries for top branch’s four sections.

- **Top branch trigger min/max**  
  Ratio range that activates Top Start branch when entered from outside.

### Right-side reticle drop-line fields

- **Show right-side reticle line attachment (`reticle_right_line_enabled`)**  
  Toggle for drawing the drop-line assembly.

- **Right line length (`reticle_right_line_length`)**  
  Horizontal line length in pixels.

- **Right line Y offset from center (`reticle_right_line_y_offset`)**  
  Vertical offset of the horizontal line relative to reticle center.

- **Right line start gap from circle (`reticle_right_line_start_gap`)**  
  Gap from reticle circle edge to line start.

- **Right line rotation around circle (`reticle_right_line_rotation_deg`)**  
  Rotates the entire right-side line assembly around reticle center.

- **Vertical line 1/2/3 position (`reticle_vline*_pos`)**  
  Position of each vertical crossing line along the horizontal line.

- **Vertical line 1/2/3 length (`reticle_vline*_len`)**  
  Length of each vertical crossing line.

## Buttons

- **Find game window**  
  Locates the TLOPO game window and logs window/client rectangle details.

- **Start overlay**  
  Starts the transparent overlay and begins tracking.

- **Stop overlay**  
  Stops overlay rendering/tracking.

- **Apply to running overlay**  
  Applies current panel values immediately without restart.

- **Save settings.json**  
  Saves current panel values to disk.

- **Reset vertical to anchor**  
  Resets current vertical aim state to `vertical_anchor_ratio`.  
  Use this when you want to re-center internal tracking state after adjustments.

- **View full logs**  
  Opens a log viewer popup for all collected session logs.

## Troubleshooting

- If overlay is visually aligned but shot landing is off after camera transitions:
  - re-prime the cannon all the way up or down
  - verify active branch triggers and sensitivities
- If behavior changes with window size:
  - verify `vertical_baseline_client_height` matches your known-good reference
  - re-run **Find game window** and compare logged client height
