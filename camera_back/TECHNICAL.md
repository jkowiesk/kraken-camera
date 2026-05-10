# Info Finder - Technical Architecture

**Project goal:** Use the Luxonis **OAK4D Pro** (RVC4) to **audit and support the design of indoor navigation/wayfinding**. The system detects wayfinding cues (arrows, exits, restrooms, stairs, etc.), extracts signage text (OCR), estimates distance-to-sign, and produces a short "route/signage quality check" summary. This helps teams evaluate whether signage is **present, visible, consistent, and actionable** along a route.

**Core idea:** Combine **open-vocabulary sign detection** (YOLO-World + CLIP text embeddings) with OCR and a lightweight **arrow shape detector**. The system supports capturing structured **scan records** (JSONL) for post-walkthrough review and iteration. If enabled, we summarize the last scan to **Gemini** using _text only_ (no images).

## System overview

### Hardware

- **Camera:** Luxonis **OAK4D Pro**
- **Platform:** **RVC4** (required for the YOLO-World model archive used here)
- **Sensors used in this implementation:**
  - RGB camera (`CAM_A`) for preview + OCR frames
  - Stereo mono cameras (`CAM_B`, `CAM_C`) for depth (distance-to-sign estimation)

### Software building blocks

- **DepthAI (device graph):**
  - `dai.node.Camera` for RGB + stereo
  - `dai.node.StereoDepth` for depth
  - `dai.node.ImageAlign` to align depth to the RGB preview stream
  - `depthai_nodes.node.ParsingNeuralNetwork` to run YOLO-World on-device

- **Host-side CV/AI:**
  - **EasyOCR** for OCR
  - **OpenCV contour/PCA arrow detector**
  - **ONNXRuntime + HF tokenizer** to compute CLIP text embeddings for YOLO-World classes

- **Optional LLM evaluation:**
  - **Gemini REST API** for a brief route/signage "OK / NOT OK / UNSURE" summary based on the latest scan record

---

## Dataflow (end-to-end)

PDF-friendly diagram (plain text; no Mermaid renderer required):

```text
OAK4D Pro (RVC4)
  CAM_A (RGB)
    - Preview stream (1280x720) ------------------------------> Host UI (OpenCV overlays)
    - NN input (model WxH) -> YOLO-World (on-device) ---------> Detections (label/conf)

  CAM_B + CAM_C (mono stereo)
    -> StereoDepth -> ImageAlign (depth aligned to RGB) ------> Aligned depth map (mm)

Host (Python)
  - Compute CLIP text embeddings once; send to NN "texts" input (reused for all frames)
  - Continuous: draw sign detections (+ optional distance)
  - Scan capture: run OCR + arrow detector -> append scan record -> ocr_scans.jsonl
  - Audit summary request: send last scan (text only) to Gemini -> display short audit summary
```

**Key runtime behavior:**

- YOLO-World sign detections run continuously (when RVC4 is available).
- OCR and arrow results are recorded as part of a user-triggered **scan** (see controls).
- Depth is used to attach an approximate distance (meters) to detected signs.

---

## YOLO-World: open-vocabulary wayfinding detection

### Why YOLO-World?

Wayfinding is _open-vocabulary_: signs vary by language, style, pictograms, and venue. YOLO-World enables "detect what I describe" via CLIP text embeddings rather than a fixed closed-set label list.

### Class prompts

We use a curated list of prompts (e.g., _"exit sign"_, _"toilet sign"_, _"arrow sign pointing left"_, _"stairs"_). Multiple phrasing variants are intentionally included to better cover the CLIP embedding space.

### Text embedding pipeline (host-side)

1. Download/locate:
   - CLIP tokenizer (`tokenizer.json`)
   - CLIP textual encoder as ONNX (cached)
2. Tokenize all class names.
3. Run CLIP text encoder in ONNXRuntime to produce text features.
4. Quantize features to the exact uint8 format expected by the SNPE YOLO-World archive.
5. Send the `texts` tensor once into the DepthAI neural network input queue, with `reusePreviousMessage=True`.

### Confidence threshold

Open-vocabulary confidence scores are often lower than closed-set detectors, so the default threshold is intentionally low (configurable via `YOLO_CONF`).

### RVC4 dependency

The YOLO-World NNArchive used here is **RVC4-only**. If the detected device platform is not RVC4, the app disables sign detection and continues with OCR + arrow detection.

---

## Depth: estimating distance to detected signs

We compute a rough distance-to-sign by:

- Aligning the depth map to the RGB preview using `ImageAlign`.
- For each detection, converting the normalized rotated rectangle to pixel `x1,y1,x2,y2`.
- Sampling the aligned depth map at the bounding box center.

This is **fast and simple**, and good enough for live auditing ("that sign is ~2.3m away"), but can be improved by sampling a robust statistic (median depth over a small ROI) to reduce noise.

---

## OCR: signage text extraction

### When it runs

OCR is executed as part of a **scan capture** step (triggered from the UI). This produces a stable, reviewable record of what the camera saw at a specific moment.

### Output

Each OCR scan produces:

- raw EasyOCR detections (bbox + text + confidence)
- a filtered list of texts above a minimum confidence
- a structured `items` list (`{"text", "confidence"}`)

The scan is added to a rolling in-memory history and appended to a local JSONL log.

---

## Arrow detection (no ML)

Arrows are common wayfinding cues and often appear as simple shapes (stickers, painted arrows, pictograms). We detect arrows using a pure OpenCV pipeline:

- adaptive thresholding (both inverted and non-inverted)
- contour filtering by area, solidity, elongation
- convexity defects to identify notches
- PCA to infer the dominant direction axis
- geometric checks to avoid false positives

This gives a fast "left/right/up/down" direction result without requiring training data.

---

## Gemini route check (text-only)

When an audit summary is requested:

- If no scan exists yet, we run one OCR scan first.
- We build a short prompt summarizing the **last scan only**:
  - OCR text snippets
  - detected sign labels + confidences (+ optional distance)
  - arrow directions
- We send that prompt to Gemini and display the first line in the HUD.

**Important privacy property:** this system sends **no camera frames** to Gemini - only derived text/detections.

---

## Controls and environment configuration

### Controls

- Capture scan (keyboard shortcut: `k`)
- Request audit summary using the last scan (keyboard shortcut: `g`)
- Clear OCR and arrow overlays (keyboard shortcut: `c`)
- Quit (keyboard shortcut: `q`)

### Environment variables

- `DEBUG` (`true/false`): enables HUD overlays and debug text
- `YOLO_CONF` (float): YOLO-World confidence threshold (default `0.05`)
- `GEMINI_API_KEY`: required for Gemini
- `GEMINI_MODEL`: optional (defaults to `gemini-1.5-flash-latest`)

### Caching and artifacts

- `.yolo_world_cache/`: caches CLIP ONNX + tokenizer downloads
- `.depthai_cached_models/`: caches DepthAI model zoo downloads
- `ocr_scans.jsonl`: append-only scan log for later analysis

---

## Design decisions (and why)

1. **Device-first inference for detection:** run YOLO-World on the OAK4D Pro (RVC4) so the host stays lightweight.
2. **Scan-based OCR:** capture OCR as part of a discrete scan record so it can be reviewed, compared across walkthroughs, and used for downstream auditing.
3. **Open-vocabulary prompts instead of a fixed label set:** prompt lists are easy to iterate without collecting labeled training data.
4. **Depth-aligned distance as extra context:** distance helps decide whether a sign is actionable (e.g., "scan closer").
5. **Text-only LLM request:** reduces bandwidth/cost and avoids uploading images.

---

## What we tried / what we learned

- **Prompt engineering is _class list engineering_:** adding multiple prompt variants ("exit sign", "emergency exit sign", etc.) improves coverage.
- **Depth alignment is crucial:** sampling depth without aligning to the RGB stream produces nonsense distances.
- **Scan capture works well for audits:** storing structured scan records makes it easy to review what was detected, compare locations, and iterate on prompt lists and heuristics.
- **Arrow detection can be done without ML:** contour/PCA-based heuristics are surprisingly effective for high-contrast arrows.

---

## Future work: signage placement recommendations (navigation design layer)

Add a layer that turns detections + OCR + depth into **actionable navigation design guidance**: _where_ to place signs and directional information so routes are unambiguous for people trying to reach a destination.

High-level approach:

- **Geotag observations:** attach approximate locations to each scan (e.g., via visual-inertial odometry / SLAM, AprilTags, or a known floorplan + checkpoints) so detected signs become map points, not just per-frame overlays.
- **Model the route as a graph:** represent corridors/intersections/decision points and link each scan to the nearest node/edge.
- **Score wayfinding clarity:** measure "coverage" of essential info (EXIT, WC, stairs/elevator, arrows) at decision points; flag gaps such as _missing confirmation signs_, _contradictory arrows_, or _low-visibility signage_ (too far / too small / low confidence OCR).
- **Recommend placements:** suggest specific **candidate locations** for new or improved signs (e.g., "add a left arrow before the T-junction", "add a confirmation sign after turning"), prioritized by predicted impact.

This would shift the system from _detecting wayfinding_ to **auditing and designing wayfinding**.

---

## How to run

From this folder:

```bash
python3 ocr.py
```

If Gemini is desired, create a `.env` (or set env vars in your shell) with:

```bash
export GEMINI_API_KEY="..."
# optional
export GEMINI_MODEL="gemini-1.5-flash-latest"
```
