#!/usr/bin/env python3
"""OCR + YOLO-World wayfinding detector using DepthAI camera and EasyOCR.

Detects wayfinding elements (arrows, exit signs, toilets, stairs …) in
real-time using YOLO-World, and runs on-demand OCR + Gemini route analysis.

Controls:
    - k: run OCR once (on-demand)
    - g: ask Gemini to evaluate signage/route based on the last scans
    - c: clear OCR/arrow overlays
    - q: quit
"""

import json
import os
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import cv2
import depthai as dai
import numpy as np
import onnxruntime
import requests
from arrow_detector import detect_arrows
from depthai_nodes.node import ParsingNeuralNetwork
from tokenizers import Tokenizer
from tqdm import tqdm

# Optional .env support
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(override=False)
except Exception:
    pass

try:
    import easyocr
except ImportError:
    print("EasyOCR not installed.  pip install easyocr")
    exit(1)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# ── YOLO-World constants ───────────────────────────────────────────────────────
QUANT_ZERO_POINT = 90.0
QUANT_SCALE = 0.003925696481
MAX_NUM_CLASSES = 80
CLIP_CACHE_DIR = Path(__file__).parent / ".yolo_world_cache"

# ── Wayfinding classes ─────────────────────────────────────────────────────────
# Many variations of the same concept help YOLO-World fire more reliably.
WAYFINDING_CLASSES = [
    # Arrows — many phrasings so CLIP embedding space is well covered
    "directional arrow sign",
    "arrow sign pointing left",
    "arrow sign pointing right",
    "arrow sign pointing straight ahead",
    "arrow sign pointing up",
    "exit arrow sign",
    "green arrow sign",
    "red arrow sign",
    "floor arrow marking",
    "wall arrow sign",
    "pointing arrow",
    "arrow",
    # Exit / emergency
    "exit sign",
    "emergency exit sign",
    "fire exit sign",
    "fire escape sign",
    # Restroom
    "toilet sign",
    "restroom sign",
    "WC sign",
    "bathroom sign",
    # Vertical circulation
    "stairs",
    "staircase",
    "escalator",
    "escalator sign",
    "stairs sign",
    "staircase sign",
    "elevator sign",
    "lift sign",
    "escalator sign",
    # Building services
    "reception sign",
    "information desk sign",
    "first aid sign",
    "help desk sign",
]

YOLO_CONF = float(
    os.getenv("YOLO_CONF", "0.05")
)  # low threshold — open-vocab scores are small


def _display_wayfinding_label(label: str) -> str:
    """Normalize YOLO-World wayfinding labels for on-screen display.

    Only labels that contain the substring 'sign' (case-insensitive) are
    displayed as the generic word 'sign'. Other labels (e.g. 'stairs') are
    displayed as-is.
    """

    if not label:
        return label
    return "sign" if "sign" in label.lower() else label


# ── CLIP / embedding helpers ───────────────────────────────────────────────────


def _download_file(url: str, dest: str) -> str:
    if os.path.exists(dest):
        return dest
    print(f"Downloading {Path(dest).name} …")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with (
            tqdm(total=total, unit="iB", unit_scale=True, desc=Path(dest).name) as bar,
            open(dest, "wb") as f,
        ):
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
    return dest


def _get_clip_onnx(cache_dir: Path) -> str:
    dest = str(cache_dir / "clip_textual_hf.onnx")
    if os.path.exists(dest):
        return dest
    base = "https://easyml.cloud.luxonis.com/models/api/v1"
    model_res = requests.get(
        f"{base}/models", params={"slug": "yolo-world-l", "is_public": True}
    )
    model_res.raise_for_status()
    model_id = model_res.json()[0]["id"]
    variant_res = requests.get(
        f"{base}/modelVersions",
        params={
            "model_id": model_id,
            "variant_slug": "clip-textual-hf",
            "is_public": True,
        },
    )
    variant_res.raise_for_status()
    variant_id = variant_res.json()[0]["id"]
    dl_res = requests.get(f"{base}/modelVersions/{variant_id}/download")
    dl_res.raise_for_status()
    _download_file(dl_res.json()[0]["download_link"], dest)
    return dest


def compute_text_embeddings(class_names: list, cache_dir: Path) -> np.ndarray:
    """Return uint8 [1, 512, 80] tensor — identical to official Luxonis helper."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tok_path = _download_file(
        "https://huggingface.co/openai/clip-vit-base-patch32/resolve/main/tokenizer.json",
        str(cache_dir / "tokenizer.json"),
    )
    tokenizer = Tokenizer.from_file(tok_path)
    tokenizer.enable_padding(
        pad_id=tokenizer.token_to_id("<|endoftext|>"), pad_token="<|endoftext|>"
    )
    encodings = tokenizer.encode_batch(class_names)
    text_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attn_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

    onnx_path = _get_clip_onnx(cache_dir)
    session = onnxruntime.InferenceSession(
        onnx_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    text_features = session.run(
        None, {input_name: text_ids, "attention_mask": attn_mask}
    )[0]

    num_pad = MAX_NUM_CLASSES - len(class_names)
    text_features = np.pad(text_features, ((0, num_pad), (0, 0)), mode="constant")
    text_features = text_features.T.reshape(1, 512, MAX_NUM_CLASSES)
    text_features = (
        np.clip(text_features / QUANT_SCALE + QUANT_ZERO_POINT, 0, 255)
        .round()
        .astype(np.uint8)
    )
    return text_features


def _det_to_bbox(det, frame_shape):
    """Convert ImgDetectionExtended rotated_rect → integer pixel (x1,y1,x2,y2)."""
    h, w = frame_shape[:2]
    rr = det.rotated_rect
    cx, cy = rr.center.x, rr.center.y
    dw, dh = rr.size.width, rr.size.height
    x1 = int(max(0.0, min(1.0, cx - dw / 2)) * w)
    y1 = int(max(0.0, min(1.0, cy - dh / 2)) * h)
    x2 = int(max(0.0, min(1.0, cx + dw / 2)) * w)
    y2 = int(max(0.0, min(1.0, cy + dh / 2)) * h)
    return x1, y1, x2, y2


# ── OCR helpers ───────────────────────────────────────────────────────────────


def _extract_texts(results, min_confidence: float = 0.3):
    texts = []
    if not results:
        return texts
    for item in results:
        try:
            _bbox, text, confidence = item
        except Exception:
            continue
        if not text:
            continue
        try:
            conf = float(confidence)
        except Exception:
            conf = 0.0
        if conf < min_confidence:
            continue
        texts.append(str(text).strip())
    return texts


def _extract_text_items(results, min_confidence: float = 0.3):
    items = []
    if not results:
        return items
    for item in results:
        try:
            _bbox, text, confidence = item
        except Exception:
            continue
        if not text:
            continue
        try:
            conf = float(confidence)
        except Exception:
            conf = 0.0
        if conf < min_confidence:
            continue
        items.append({"text": str(text).strip(), "confidence": conf})
    return items


def frameNorm(frame, bbox):
    normVals = np.full(len(bbox), frame.shape[0])
    normVals[::2] = frame.shape[1]
    return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)


# ── Gemini helpers ────────────────────────────────────────────────────────────


def _gemini_list_models(timeout_s: int = 10):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY is not set"
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, f"Failed to list models: {e}"
    models = data.get("models", []) if isinstance(data, dict) else []
    out = []
    for m in models:
        name = m.get("name")
        methods = m.get("supportedGenerationMethods", [])
        if not name:
            continue
        if isinstance(methods, list) and "generateContent" in methods:
            out.append(name)
    return out, None


def _normalize_gemini_model(model: str) -> str:
    if not model:
        return model
    return model[len("models/") :] if model.startswith("models/") else model


def _gemini_generate_text_only(prompt: str, model=None, timeout_s: int = 25):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY is not set"
    selected_model = _normalize_gemini_model(
        model or os.getenv("GEMINI_MODEL") or "gemini-1.5-flash-latest"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except Exception:
            err = str(e)
        return None, f"Gemini HTTP error (model={selected_model}): {e.code} {err}"
    except Exception as e:
        return None, f"Gemini request failed: {e}"
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip(), None
    except Exception:
        return None, f"Unexpected Gemini response: {data}"


def _build_gemini_prompt(scan_history):
    last_item = scan_history[-1] if scan_history else None
    if not last_item:
        history_text = "(no scans yet)"
    else:
        when_s = time.strftime("%H:%M:%S", time.localtime(last_item["ts"]))
        texts = last_item.get("texts", [])
        joined = "; ".join(texts) if texts else "(no text)"
        signs = last_item.get("signs", [])
        sign_str = (
            ", ".join(
                f"{s.get('label', '?')}:{s.get('confidence', 0):.2f}"
                + (f"@{s['distance_m']}m" if "distance_m" in s else "")
                for s in signs[:6]
            )
            if signs
            else "(no signs)"
        )
        arrows = last_item.get("arrows", [])
        arrow_str = (
            ", ".join(f"arrow-{a['direction']}" for a in arrows)
            if arrows
            else "(no arrows)"
        )
        history_text = (
            f"{when_s}: OCR={joined} | SIGNS={sign_str} | ARROWS={arrow_str}"
        )
    return (
        "You are helping validate indoor wayfinding signage (directional signs in a building).\n"
        "You have OCR text, detected sign labels, and detected arrow directions (no images). Based on the last scan below, answer:\n"
        "1) Is the route/signage guidance OK? (OK / NOT OK / UNSURE)\n"
        "2) One sentence why\n"
        "3) One concrete suggestion (e.g., 'scan again closer', 'look for EXIT sign').\n\n"
        "Last scan:\n"
        f"{history_text}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    debug = _env_flag("DEBUG", False)
    # ── 1. Compute CLIP embeddings (downloads ~254 MB once, then cached) ──────
    print(
        f"Preparing YOLO-World embeddings for {len(WAYFINDING_CLASSES)} wayfinding classes …"
    )
    texts_u8 = compute_text_embeddings(WAYFINDING_CLASSES, CLIP_CACHE_DIR)
    print(f"Embeddings ready: {texts_u8.shape}")

    # ── 2. Connect to device ──────────────────────────────────────────────────
    device = dai.Device()
    platform = device.getPlatformAsString()
    print(f"Platform: {platform}")

    if platform != "RVC4":
        print(
            f"WARNING: YOLO-World requires RVC4, got {platform}. Sign detection will be disabled."
        )
        yolo_enabled = False
    else:
        yolo_enabled = True

    # ── 3. Download YOLO-World model ──────────────────────────────────────────
    if yolo_enabled:
        print("Fetching luxonis/yolo-world-l from model zoo …")
        model_desc = dai.NNModelDescription(
            model="luxonis/yolo-world-l", platform="RVC4"
        )
        model_path = dai.getModelFromZoo(
            model_desc, useCached=True, progressFormat="pretty"
        )
        archive = dai.NNArchive(str(model_path))
        model_w, model_h = archive.getInputSize()
        print(f"YOLO-World input size: {model_w}x{model_h}")

    # ── 4. EasyOCR ────────────────────────────────────────────────────────────
    print("Initializing EasyOCR …")
    reader = easyocr.Reader(["en"])
    print("EasyOCR ready.")

    # ── 5. Pipeline ───────────────────────────────────────────────────────────
    DISPLAY_W, DISPLAY_H = 1280, 720
    frame_type = dai.ImgFrame.Type.BGR888i

    with dai.Pipeline(device) as pipeline:
        cam = pipeline.create(dai.node.Camera).build(
            boardSocket=dai.CameraBoardSocket.CAM_A
        )

        # Display / OCR stream (full res)
        cam_view = cam.requestOutput(
            size=(DISPLAY_W, DISPLAY_H), type=frame_type, fps=15.0
        )
        view_q = cam_view.createOutputQueue()

        # YOLO-World stream
        if yolo_enabled:
            cam_nn = cam.requestOutput(
                size=(model_w, model_h), type=frame_type, fps=15.0
            )
            nn = pipeline.create(ParsingNeuralNetwork)
            nn.setNNArchive(archive)
            nn.setBackend("snpe")
            nn.setBackendProperties(
                {"runtime": "dsp", "performance_profile": "default"}
            )
            nn.setNumInferenceThreads(1)
            nn.getParser(0).setConfidenceThreshold(YOLO_CONF)
            nn.getParser(0).setIouThreshold(0.4)
            cam_nn.link(nn.inputs["images"])

            text_q = nn.inputs["texts"].createInputQueue()
            nn.inputs["texts"].setReusePreviousMessage(True)
            det_q = nn.out.createOutputQueue()

            # ── Stereo depth (RVC4 path) ───────────────────────────────────
            mono_left = pipeline.create(dai.node.Camera).build(
                dai.CameraBoardSocket.CAM_B
            )
            mono_right = pipeline.create(dai.node.Camera).build(
                dai.CameraBoardSocket.CAM_C
            )
            stereo = pipeline.create(dai.node.StereoDepth)
            stereo.setLeftRightCheck(True)
            stereo.setExtendedDisparity(True)
            mono_left.requestOutput(size=(640, 400), fps=15.0).link(stereo.left)
            mono_right.requestOutput(size=(640, 400), fps=15.0).link(stereo.right)

            # Align depth to the display RGB frame
            depth_align = pipeline.create(dai.node.ImageAlign)
            stereo.depth.link(depth_align.input)
            cam_view.link(depth_align.inputAlignTo)
            depth_q = depth_align.outputAligned.createOutputQueue()

        pipeline.start()

        # Send embeddings once (reused for every subsequent frame)
        if yolo_enabled:
            nn_data = dai.NNData()
            nn_data.addTensor("texts", texts_u8, dataType=dai.TensorInfo.DataType.U8F)
            text_q.send(nn_data)

        # ── State ─────────────────────────────────────────────────────────────
        fps_counter = 0
        fps_time = time.time()
        frame_count = 0
        fps = 0.0
        last_ocr_results = []
        scan_history = deque(maxlen=10)
        current_sign_detections: list = []
        last_arrow_detections: list = []
        depth_map: np.ndarray | None = None
        scan_requested = False
        gemini_requested = False
        last_gemini_text = ""
        last_gemini_ts = 0.0
        scans_log_path = os.path.join(os.path.dirname(__file__), "ocr_scans.jsonl")

        print("Ready.  k=scan OCR | g=Gemini check | q=quit")
        print(
            f"YOLO classes ({len(WAYFINDING_CLASSES)}): {', '.join(WAYFINDING_CLASSES)}"
        )

        def run_ocr_once(frame_bgr):
            nonlocal last_arrow_detections
            results_local = reader.readtext(frame_bgr)
            texts_local = _extract_texts(results_local)
            items_local = _extract_text_items(results_local)
            arrows_local = detect_arrows(frame_bgr)
            last_arrow_detections = arrows_local
            entry = {
                "ts": time.time(),
                "items": items_local,
                "texts": texts_local,
                "signs": list(current_sign_detections),
                "arrows": [{"direction": a["direction"]} for a in arrows_local],
                "count": len(results_local) if results_local else 0,
            }
            arrow_str = (
                ", ".join(f"arrow-{a['direction']}" for a in arrows_local) or "none"
            )
            print(
                f"OCR scan: {entry['count']} items | signs: {entry['signs']} | arrows: {arrow_str} | texts: {texts_local}"
            )
            scan_history.append(entry)
            try:
                with open(scans_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"Failed to write scan log: {e}")
            return results_local or []

        # ── Main loop ─────────────────────────────────────────────────────────
        while pipeline.isRunning():
            # Frame
            frame_msg = view_q.get()
            if frame_msg is None:
                continue
            frame = frame_msg.getCvFrame()
            frame_count += 1

            # YOLO-World detections + depth
            if yolo_enabled:
                det_msg = det_q.tryGet()
                depth_msg = depth_q.tryGet()
                if depth_msg is not None:
                    depth_map = depth_msg.getFrame()  # uint16, millimetres

                if det_msg is not None:
                    new_dets = []
                    for d in det_msg.detections:
                        label_idx = int(d.label)
                        if label_idx >= len(WAYFINDING_CLASSES):
                            continue
                        entry = {
                            "label": WAYFINDING_CLASSES[label_idx],
                            "confidence": float(d.confidence),
                        }
                        if depth_map is not None:
                            x1, y1, x2, y2 = _det_to_bbox(d, frame.shape)
                            cx_px = min((x1 + x2) // 2, depth_map.shape[1] - 1)
                            cy_px = min((y1 + y2) // 2, depth_map.shape[0] - 1)
                            dist_mm = int(depth_map[cy_px, cx_px])
                            if dist_mm > 0:
                                entry["distance_m"] = round(dist_mm / 1000.0, 2)
                        new_dets.append(entry)
                    current_sign_detections = new_dets

                # Draw sign boxes
                for d in det_msg.detections if det_msg else []:
                    label_idx = int(d.label)
                    if label_idx >= len(WAYFINDING_CLASSES):
                        continue
                    label = WAYFINDING_CLASSES[label_idx]
                    display_label = _display_wayfinding_label(label)
                    conf = float(d.confidence)
                    x1, y1, x2, y2 = _det_to_bbox(d, frame.shape)
                    dist_str = ""
                    for e in current_sign_detections:
                        if e["label"] == label and "distance_m" in e:
                            dist_str = f" {e['distance_m']:.1f}m"
                            break
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 165, 255), 2)
                    cv2.putText(
                        frame,
                        f"{display_label} {conf:.2f}{dist_str}",
                        (x1 + 4, max(0, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 165, 255),
                        2,
                    )

            # OCR (on demand)
            results = last_ocr_results
            if scan_requested:
                if debug:
                    cv2.putText(
                        frame,
                        "SCANNING…",
                        (frame.shape[1] - 220, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.1,
                        (0, 255, 255),
                        2,
                    )
                results = run_ocr_once(frame)
                last_ocr_results = results
                scan_requested = False

            # Gemini (on demand)
            if gemini_requested:
                if not scan_history:
                    results = run_ocr_once(frame)
                    last_ocr_results = results
                if debug:
                    cv2.putText(
                        frame,
                        "GEMINI CHECK…",
                        (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (255, 255, 0),
                        2,
                    )
                prompt = _build_gemini_prompt(scan_history)
                text, err = _gemini_generate_text_only(prompt)
                last_gemini_text = text if text else f"Gemini unavailable: {err}"
                last_gemini_ts = time.time()

                if (
                    not text
                    and err
                    and any(
                        k in err.lower() for k in ("not found", "listmodels", "models/")
                    )
                ):
                    models, lerr = _gemini_list_models()
                    if models:
                        print("Available Gemini models:")
                        for m in models[:20]:
                            print(f"  {m}")
                    elif lerr:
                        print(f"Could not list models: {lerr}")

                print("\n=== Gemini route check ===")
                print(last_gemini_text)
                print("========================\n")
                gemini_requested = False

            # Draw arrow detections (persisted from last scan)
            ARROW_SYMBOLS = {"left": "<", "right": ">", "up": "^", "down": "v"}
            for arr in last_arrow_detections:
                ax1, ay1, ax2, ay2 = arr["bbox"]
                sym = ARROW_SYMBOLS.get(arr["direction"], "?")
                cv2.rectangle(frame, (ax1, ay1), (ax2, ay2), (0, 255, 255), 3)
                cv2.putText(
                    frame,
                    f"{sym} {arr['direction']}",
                    (ax1 + 4, max(0, ay1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 255),
                    2,
                )

            # Draw OCR results
            if results:
                for bbox, text, confidence in results:
                    try:
                        bbox_int = [[int(x), int(y)] for x, y in bbox]
                    except (ValueError, TypeError):
                        continue
                    pts = np.array(bbox_int, np.int32)
                    cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
                    x, y = int(bbox_int[0][0]), int(bbox_int[0][1]) - 10
                    cv2.putText(
                        frame,
                        f"{text} ({confidence:.2f})",
                        (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0),
                        2,
                    )

            # FPS
            fps_counter += 1
            now = time.time()
            if now - fps_time >= 1.0:
                fps = fps_counter / (now - fps_time)
                fps_counter = 0
                fps_time = now

            # HUD
            sign_str = (
                f"Signs: {len(current_sign_detections)}"
                if yolo_enabled
                else "Signs: OFF"
            )
            if debug:
                cv2.putText(
                    frame,
                    f"FPS: {fps:.1f} | k=scan | g=check | OCR: {len(results)} | {sign_str}",
                    (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (255, 255, 255),
                    2,
                )

                if scan_history:
                    age_s = time.time() - scan_history[-1]["ts"]
                    cv2.putText(
                        frame,
                        f"Last scan: {age_s:.1f}s ago | History: {len(scan_history)}/10",
                        (10, 75),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )
                    signs = scan_history[-1].get("signs", [])
                    if signs:
                        cv2.putText(
                            frame,
                            "Signs: "
                            + ", ".join(
                                _display_wayfinding_label(s.get("label", ""))
                                for s in signs[:4]
                            ),
                            (10, 105),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (0, 200, 255),
                            2,
                        )

                if last_gemini_text and (time.time() - last_gemini_ts) < 30:
                    first_line = last_gemini_text.splitlines()[0][:90]
                    cv2.putText(
                        frame,
                        f"Gemini: {first_line}",
                        (10, 140),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 0),
                        2,
                    )

            cv2.imshow("OCR + Wayfinding", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("k"):
                scan_requested = True
            elif key == ord("g"):
                gemini_requested = True
            elif key == ord("c"):
                last_ocr_results = []
                last_arrow_detections = []

    cv2.destroyAllWindows()
    print("Pipeline stopped.")


if __name__ == "__main__":
    main()
