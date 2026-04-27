# 01 — Overview

## The problem in one paragraph

A landlord recorded a walkthrough of a NYC apartment on a phone. The video is the only source of geometric information available — the renter is out of state, the landlord is unresponsive, and re-recording is not possible. The renter needs to decide whether a second person + their bed/desk can fit, which requires knowing approximate room dimensions and free floor area.

Off-the-shelf phone-scan apps (RoomPlan, Polycam, Magicplan, Scaniverse) all require the operator to be physically present, holding the phone. That tool category is ruled out.

Off-the-shelf feed-forward video → 3D models (VGGT, MASt3R, Fast3R, MonST3R) work on existing video but produce reconstructions that are correct in **shape** and **proportion** and unknown in **absolute size** — geometry is recovered up to a scaling factor. A 10 ft wall and a 20 ft wall look identical to the model.

The deliverable of this project is the layer that turns scale-ambiguous geometry into a measurement-ready metric reconstruction.

## Goals

### Track A — personal utility (must ship by end of week)

- Produce a labeled floor plan of the apartment with room-by-room dimensions in feet/inches.
- Identify the largest single piece of unobstructed floor (where a second bed can go).
- Tolerance: ±10% on linear dimensions is acceptable for the roommate decision.

### Track B — portfolio piece (3–4 weeks)

- Public hosted demo at `reconstruct3d.<domain>` accepting any user-uploaded video.
- Sub-2-minute end-to-end runtime for a 30-second input video.
- Three.js viewer with: orbit/pan, animated camera trajectory, click-two-points-to-measure, drag-and-drop IKEA GLB furniture, axis-aligned floor-plan top-down view.
- README + 90-second screen recording suitable for resume / portfolio links.

## Non-goals

- Real-time / streaming / SLAM — every input video is processed offline as a batch.
- Mobile capture app — the input is "any existing video," not a custom scanning experience.
- Sub-1% accuracy — we are not a metrology tool. The error budget below assumes furniture-planning use cases, not legal/structural ones.

## Accuracy budget

| Source of error | Expected magnitude | Notes |
|-----------------|--------------------|-------|
| VGGT geometry (relative) | ~1–3% on locally well-covered surfaces | Worse for poorly lit / textureless walls |
| Metric scaling via UniDepth v2 | ~5–10% | Indoor priors are strong; bedrooms easier than oddly shaped spaces |
| Metric scaling via door reference | ~2–5% | Limited by point-click precision in the viewer |
| Camera pose drift over a long pan | ~1–2% per 10 seconds of footage | Mitigated by chunked processing with overlap |
| **Total expected** | **~5–10% on linear dimensions** | Stack errors loosely — they don't compound multiplicatively |

A 12 ft wall reported by the system could be anywhere from 10.8 ft to 13.2 ft in reality. That margin is acceptable for "does a queen bed fit" and not acceptable for "I'm signing a lease based on this number."

## Success criteria

**Track A passes when:** the renter has written down room dimensions, drawn a furniture plan, and made the roommate go/no-go decision, with confidence that a queen bed + desk for both occupants will physically fit.

**Track B passes when:** a stranger can land on the demo page, upload their own apartment walkthrough, and get back a usable measured 3D scene without reading documentation.
