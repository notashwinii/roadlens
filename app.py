import os
import shutil
import tempfile
import time
from pathlib import Path

import cv2
import streamlit as st
import streamlit.elements.image as st_image
from streamlit.elements.lib import image_utils
from streamlit.elements.lib.layout_utils import LayoutConfig

import pipeline
from core.config_loader import load_config
from ingestion.roi import clamp_roi
from scene.scene_builder import build_scene_from_config
from scene.zone_renderer import draw_zones

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "speedotector_matplotlib"),
)


def image_to_url(
    image,
    width=None,
    clamp=True,
    channels="RGB",
    output_format="PNG",
    image_id="image",
):
    layout_config = (
        width if isinstance(width, LayoutConfig) else LayoutConfig(width=width)
    )
    return image_utils.image_to_url(
        image,
        layout_config,
        clamp,
        channels,
        output_format,
        image_id,
    )


st_image.image_to_url = image_to_url

import streamlit_image_annotation.Detection as detection_module  # noqa: E402

detection_module.image_to_url = image_to_url
detection = detection_module.detection

st.set_page_config(page_title="Speedotector", layout="wide")

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 1rem;
            max-width: 100rem;
        }

        h1 {
            margin-bottom: 0.25rem;
        }

        div[data-testid="stImage"] img,
        div[data-testid="stVideo"] video {
            max-height: 56vh;
            object-fit: contain;
        }

        div[data-testid="stFileUploader"] section {
            min-height: 4.25rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


TEMP_DIR_PREFIX = "speedotector_streamlit_"
STALE_TEMP_DIR_SECONDS = 24 * 60 * 60
MAX_LOG_LINES = 100
ROI_LABEL = "ROI"
ROI_SELECTOR_MAX_WIDTH = 760
ROI_SELECTOR_MAX_HEIGHT = 560
UPLOAD_STATE_KEYS = ("video_path", "video_temp_dir", "upload_signature")
DETECTION_STATE_KEYS = (
    "roi_x",
    "roi_y",
    "roi_w",
    "roi_h",
    "roi_selected",
    "results",
    "processing_logs",
    "run_summary",
    "last_status",
)


def cleanup_stale_temp_dirs():
    temp_root = Path(tempfile.gettempdir())
    now = time.time()
    for temp_dir in temp_root.glob(f"{TEMP_DIR_PREFIX}*"):
        if not temp_dir.is_dir():
            continue
        try:
            if now - temp_dir.stat().st_mtime > STALE_TEMP_DIR_SECONDS:
                shutil.rmtree(temp_dir, ignore_errors=True)
        except OSError:
            continue


def queue_temp_cleanup(video_path=None, temp_dir=None):
    if not video_path and not temp_dir:
        return

    pending = st.session_state.setdefault("pending_temp_cleanup", [])
    cleanup_item = {"video_path": video_path, "temp_dir": temp_dir}
    if cleanup_item not in pending:
        pending.append(cleanup_item)


def cleanup_pending_temp_dirs():
    pending = st.session_state.get("pending_temp_cleanup", [])
    if not pending:
        return

    active_video_path = st.session_state.get("video_path")
    active_temp_dir = st.session_state.get("video_temp_dir")
    remaining = []

    for cleanup_item in pending:
        video_path = cleanup_item.get("video_path")
        temp_dir = cleanup_item.get("temp_dir")

        if video_path == active_video_path or temp_dir == active_temp_dir:
            remaining.append(cleanup_item)
            continue

        try:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            elif video_path and os.path.exists(video_path):
                os.remove(video_path)
        except OSError:
            remaining.append(cleanup_item)

    if remaining:
        st.session_state["pending_temp_cleanup"] = remaining
    else:
        st.session_state.pop("pending_temp_cleanup", None)


def reset_detection_state():
    for key in DETECTION_STATE_KEYS:
        st.session_state.pop(key, None)


def reset_upload_state(queue_cleanup=True):
    video_path = st.session_state.get("video_path")
    temp_dir = st.session_state.get("video_temp_dir")

    if queue_cleanup:
        queue_temp_cleanup(video_path, temp_dir)

    for key in UPLOAD_STATE_KEYS:
        st.session_state.pop(key, None)

    reset_detection_state()
    st.session_state["uploader_key"] += 1


def write_uploaded_video(uploaded_file):
    queue_temp_cleanup(
        st.session_state.get("video_path"),
        st.session_state.get("video_temp_dir"),
    )
    reset_detection_state()

    suffix = Path(uploaded_file.name).suffix
    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    video_path = Path(temp_dir) / f"uploaded{suffix}"
    video_path.write_bytes(uploaded_file.getbuffer())

    st.session_state["video_temp_dir"] = temp_dir
    st.session_state["video_path"] = str(video_path)
    st.session_state["upload_signature"] = (uploaded_file.name, uploaded_file.size)
    return str(video_path)


def model_path():
    return str(Path(__file__).resolve().parent / "models" / "license_plate.pt")


def vehicle_model_path():
    return "yolo26n.pt"


@st.cache_resource(show_spinner=False)
def load_vehicle_detector(vehicle_model_path):
    from ocr.vehicleDetection import VehicleDetection

    return VehicleDetection(vehicle_model_path)


@st.cache_resource(show_spinner=False)
def load_plate_detector(model_path):
    from ocr.licensePlate import LicensePlateDetection

    return LicensePlateDetection(model_path)


@st.cache_resource(show_spinner=False)
def load_ocr():
    from ocr.licensePlate import PaddleInference

    return PaddleInference()


def empty_run_summary():
    return {
        "raw_frames_scanned": 0,
        "raw_frames_total": 0,
        "selected_frames_processed": 0,
        "vehicles_seen": 0,
        "plates_detected": 0,
        "ocr_attempts": 0,
        "ocr_successes": 0,
        "detections_found": 0,
    }


def append_processing_log(message):
    logs = st.session_state.setdefault("processing_logs", [])
    logs.append(message)
    del logs[:-MAX_LOG_LINES]
    st.session_state["last_status"] = message


def format_percent(value):
    if value is None:
        return "-"
    return f"{value:.1%}"


def format_coords(coords):
    if coords is None:
        return "-"
    return ", ".join(str(int(value)) for value in coords)


def default_roi(frame_width, frame_height):
    width = max(1, int(frame_width * 0.45))
    height = max(1, int(frame_height * 0.35))
    x = max(0, int((frame_width - width) / 2))
    y = max(0, int((frame_height - height) / 2))
    return (x, y, width, height)


def roi_area_percent(roi, frame_width, frame_height):
    _, _, roi_width, roi_height = roi
    frame_area = max(1, frame_width * frame_height)
    return (roi_width * roi_height / frame_area) * 100


def roi_crop(frame_rgb, roi):
    x, y, width, height = roi
    return frame_rgb[y : y + height, x : x + width]


def render_run_summary(target):
    summary = st.session_state.get("run_summary") or empty_run_summary()
    with target.container():
        cols = st.columns(7)
        raw_total = summary.get("raw_frames_total", 0)
        raw_value = summary.get("raw_frames_scanned", 0)
        raw_label = f"{raw_value}/{raw_total}" if raw_total else raw_value
        cols[0].metric("Raw frames", raw_label)
        cols[1].metric("Selected frames", summary["selected_frames_processed"])
        cols[2].metric("Vehicles", summary["vehicles_seen"])
        cols[3].metric("Plates", summary["plates_detected"])
        cols[4].metric("OCR runs", summary["ocr_attempts"])
        cols[5].metric("OCR OK", summary["ocr_successes"])
        cols[6].metric("Detections", summary["detections_found"])


def render_scan_progress(target):
    summary = st.session_state.get("run_summary") or empty_run_summary()
    raw_frames_scanned = int(summary.get("raw_frames_scanned", 0))
    raw_frames_total = int(summary.get("raw_frames_total", 0))

    if raw_frames_total > 0:
        progress = min(raw_frames_scanned / raw_frames_total, 1.0)
        target.progress(
            progress,
            text=(
                "Scanning video frames: "
                f"{raw_frames_scanned} / {raw_frames_total} raw frames"
            ),
        )
    elif raw_frames_scanned > 0:
        target.progress(
            0,
            text=f"Scanning video frames: {raw_frames_scanned} raw frames",
        )
    else:
        target.empty()


def render_processing_log(target):
    logs = st.session_state.get("processing_logs", [])
    if logs:
        target.text("\n".join(logs[-MAX_LOG_LINES:]))
    else:
        target.caption("No processing logs yet.")


def render_results(results):
    if not results:
        st.info("No detections found yet.")
        return

    for result_number, result in enumerate(results, start=1):
        with st.container(border=True):
            image_col, detail_col = st.columns([1, 2.4], vertical_alignment="top")

            with image_col:
                plate_img = result.get("plate_img")
                if plate_img is not None:
                    plate_img_rgb = cv2.cvtColor(plate_img, cv2.COLOR_BGR2RGB)
                    st.image(
                        plate_img_rgb, caption="Plate crop", use_container_width=True
                    )
                else:
                    st.caption("No plate crop available.")

            with detail_col:
                st.subheader(f"{result_number}. {result['plate_text']}")
                metric_cols = st.columns(4)
                metric_cols[0].metric("Vehicle", result["vehicle_class"])
                metric_cols[1].metric(
                    "Detector", format_percent(result.get("detector_confidence"))
                )
                metric_cols[2].metric(
                    "OCR", format_percent(result.get("ocr_confidence"))
                )
                metric_cols[3].metric("Frame", result.get("source_frame_number", "-"))

                st.write(
                    f"Vehicle confidence: {format_percent(result.get('vehicle_confidence'))}"
                )
                st.write(f"Plate coordinates: `{format_coords(result.get('coords'))}`")
                st.write(
                    f"Vehicle coordinates: `{format_coords(result.get('vehicle_coords'))}`"
                )


def render_config_preview(config):
    st.caption(config.camera.name)
    st.write(f"Source: `{config.camera.source_path}`")
    st.write(f"Vehicle model: `{config.models.vehicle_detector}`")
    st.write(f"Plate model: `{config.models.plate_detector}`")
    st.write(f"Zones: `{len(config.zones)}` configured")
    st.write(
        "Frame selection: "
        f"motion>{config.frame_selection.motion_threshold}, "
        f"cooldown={config.frame_selection.cooldown_frames}"
    )


def zone_table_rows(zones):
    return [
        {
            "id": zone.id,
            "name": zone.name,
            "type": zone.type,
            "shape": zone.shape,
            "enabled": zone.enabled,
            "points": len(zone.points_normalized),
            "description": zone.description or "",
        }
        for zone in zones
    ]


def render_scene_preview(config, scene):
    st.subheader("Scene config preview")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Camera", config.camera.id)
    metric_cols[1].metric("Frame width", scene.frame_width)
    metric_cols[2].metric("Frame height", scene.frame_height)
    metric_cols[3].metric("Enabled zones", len(scene.zones))

    preview = draw_zones(scene.first_frame, scene.zones)
    preview_rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
    st.image(
        preview_rgb,
        caption=f"Zones from {st.session_state.get('config_path', 'config')}",
        use_container_width=True,
    )
    st.dataframe(zone_table_rows(config.zones), use_container_width=True)


if not st.session_state.get("stale_temp_dirs_cleaned"):
    cleanup_stale_temp_dirs()
    st.session_state["stale_temp_dirs_cleaned"] = True

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

if "run_summary" not in st.session_state:
    st.session_state["run_summary"] = empty_run_summary()


def update_roi_state(roi):
    x, y, width, height = roi
    st.session_state["roi_x"] = x
    st.session_state["roi_y"] = y
    st.session_state["roi_w"] = width
    st.session_state["roi_h"] = height


def roi_state():
    return (
        st.session_state["roi_x"],
        st.session_state["roi_y"],
        st.session_state["roi_w"],
        st.session_state["roi_h"],
    )


st.title("Speedotector")
st.write(
    "Upload a video, choose an optional region of interest, and run license plate detection with live progress."
)

with st.container(border=True):
    st.subheader("Upload")
    uploaded_file = st.file_uploader(
        "Video file",
        type=["mp4", "mov", "avi", "mkv"],
        key=f"video_upload_{st.session_state['uploader_key']}",
    )

if uploaded_file is None and st.session_state.get("video_path"):
    reset_upload_state(queue_cleanup=True)
    st.rerun()

video_path = None
upload_signature = None
roi = None

if uploaded_file:
    upload_signature = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("upload_signature") != upload_signature:
        video_path = write_uploaded_video(uploaded_file)
    else:
        video_path = st.session_state["video_path"]

has_video = video_path is not None

with st.sidebar:
    st.header("Settings")
    config_path = st.text_input(
        "Config path",
        value=st.session_state.get("config_path", "configs/default.yaml"),
    )
    if st.button("Load config"):
        try:
            loaded_config = load_config(config_path)
            st.session_state["loaded_config"] = loaded_config
            st.session_state["config_path"] = config_path
        except Exception as e:
            st.session_state.pop("loaded_config", None)
            st.session_state.pop("loaded_scene", None)
            st.error(str(e))
        else:
            try:
                st.session_state["loaded_scene"] = build_scene_from_config(
                    loaded_config
                )
            except Exception as e:
                st.session_state.pop("loaded_scene", None)
                st.warning(f"Config loaded, but scene preview failed: {e}")

    loaded_config = st.session_state.get("loaded_config")
    if loaded_config is not None:
        render_config_preview(loaded_config)

    use_full_frame = st.checkbox(
        "Use full frame",
        value=False,
        help="CLI mode asks you to select an ROI. Leave this off to match that behavior.",
    )
    save_to_db = st.checkbox(
        "Save results to database",
        value=False,
        help="If unchecked, detections are shown only in this session and no database connection is required.",
    )
    run_detection = st.button("Run detection", disabled=not has_video, type="primary")
    clear_upload = st.button("Clear uploaded video", disabled=not has_video)

loaded_config = st.session_state.get("loaded_config")
loaded_scene = st.session_state.get("loaded_scene")
if loaded_config is not None and loaded_scene is not None:
    render_scene_preview(loaded_config, loaded_scene)

if clear_upload:
    reset_upload_state(queue_cleanup=True)
    st.rerun()

if has_video:
    cap = cv2.VideoCapture(video_path)
    ret, first_frame = cap.read()
    cap.release()

    if not ret:
        st.error("Could not read first frame from video.")
        st.stop()

    h, w = first_frame.shape[:2]
    first_frame_rgb = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)

    st.subheader("ROI preview and selection")

    if use_full_frame:
        roi = (0, 0, w, h)
        st.session_state["roi_selected"] = True
    else:
        if "roi_x" not in st.session_state:
            update_roi_state(default_roi(w, h))
            st.session_state["roi_selected"] = False
        else:
            update_roi_state(clamp_roi(*roi_state(), w, h))

        st.caption("Exact coordinates")
        x_col, y_col, width_col, height_col, action_col, status_col = st.columns(
            [1, 1, 1, 1, 0.8, 1.4],
            vertical_alignment="bottom",
        )

        with x_col:
            x = st.number_input(
                "X",
                min_value=0,
                max_value=w - 1,
                value=st.session_state["roi_x"],
            )

        with y_col:
            y = st.number_input(
                "Y",
                min_value=0,
                max_value=h - 1,
                value=st.session_state["roi_y"],
            )

        roi_w = min(st.session_state["roi_w"], w - int(x))
        roi_h = min(st.session_state["roi_h"], h - int(y))

        with width_col:
            roi_w = st.number_input(
                "Width",
                min_value=1,
                max_value=w - int(x),
                value=roi_w,
            )

        with height_col:
            roi_h = st.number_input(
                "Height",
                min_value=1,
                max_value=h - int(y),
                value=roi_h,
            )

        manual_roi = clamp_roi(x, y, roi_w, roi_h, w, h)
        if manual_roi != roi_state():
            update_roi_state(manual_roi)
            st.session_state["roi_selected"] = True

        with action_col:
            if st.button("Confirm ROI"):
                st.session_state["roi_selected"] = True

        current_area = roi_area_percent(roi_state(), w, h)
        with status_col:
            if st.session_state.get("roi_selected"):
                st.success(f"Selected ({current_area:.1f}% of frame).")
            else:
                st.warning("Select or confirm ROI.")

        roi = roi_state()
        selector_col, crop_col = st.columns([2.1, 1], vertical_alignment="top")

        with selector_col:
            annotated_boxes = detection(
                image_path=first_frame_rgb,
                label_list=[ROI_LABEL],
                bboxes=[list(roi)],
                labels=[0],
                width=ROI_SELECTOR_MAX_WIDTH,
                height=ROI_SELECTOR_MAX_HEIGHT,
                line_width=3,
                use_space=True,
                key=f"roi_annotation_{upload_signature[0]}_{upload_signature[1]}",
            )

            if isinstance(annotated_boxes, list) and annotated_boxes:
                latest_box = annotated_boxes[-1]["bbox"]
                annotation_roi = clamp_roi(
                    latest_box[0],
                    latest_box[1],
                    latest_box[2],
                    latest_box[3],
                    w,
                    h,
                )
                if annotation_roi != roi_state():
                    update_roi_state(annotation_roi)
                    st.session_state["roi_selected"] = True
                    roi = annotation_roi

            st.caption(f"ROI: x={roi[0]}, y={roi[1]}, width={roi[2]}, height={roi[3]}")

        with crop_col:
            st.image(
                roi_crop(first_frame_rgb, roi),
                caption="Selected ROI crop",
                use_container_width=True,
            )

    if use_full_frame:
        st.image(
            first_frame_rgb,
            caption=f"Full frame preview: width={w}, height={h}",
            use_container_width=True,
        )

    with st.expander("Playback", expanded=False):
        st.video(video_path)

    st.subheader("Processing status")
    status_placeholder = st.empty()
    scan_progress_placeholder = st.empty()
    summary_placeholder = st.empty()
    with st.expander("Detailed processing log", expanded=False):
        log_placeholder = st.empty()

    if st.session_state.get("last_status"):
        status_placeholder.info(st.session_state["last_status"])
    else:
        status_placeholder.caption("Ready to run detection.")
    render_scan_progress(scan_progress_placeholder)
    render_run_summary(summary_placeholder)
    render_processing_log(log_placeholder)

    if run_detection and not st.session_state.get("roi_selected"):
        st.error("Select or confirm an ROI first. This matches the CLI ROI step.")

    if run_detection and st.session_state.get("roi_selected"):
        st.session_state["results"] = []
        st.session_state["processing_logs"] = []
        st.session_state["run_summary"] = empty_run_summary()
        st.session_state["last_status"] = "Loading models..."
        st.session_state["last_ui_status_update"] = 0.0
        status_placeholder.info("Loading models...")
        render_scan_progress(scan_progress_placeholder)
        render_run_summary(summary_placeholder)
        render_processing_log(log_placeholder)

        def refresh_processing_ui(force=False):
            now = time.monotonic()
            last_update = st.session_state.get("last_ui_status_update", 0.0)
            if not force and now - last_update < 0.5:
                return

            st.session_state["last_ui_status_update"] = now
            status_placeholder.info(
                st.session_state.get("last_status", "Processing...")
            )
            render_scan_progress(scan_progress_placeholder)
            render_run_summary(summary_placeholder)
            render_processing_log(log_placeholder)

        def record_status(message, force=False):
            print(message, flush=True)
            append_processing_log(message)
            refresh_processing_ui(force=force)

        def record_raw_scan_progress(frames_scanned, total_frames, force=False):
            summary = st.session_state.setdefault("run_summary", empty_run_summary())
            summary["raw_frames_scanned"] = max(
                int(summary.get("raw_frames_scanned", 0)),
                int(frames_scanned),
            )
            summary["raw_frames_total"] = max(
                int(summary.get("raw_frames_total", 0)),
                int(total_frames or 0),
            )
            refresh_processing_ui(force=force)

        def wrap_selected_frames_with_raw_progress(original_selected_frames):
            def selected_frames_with_raw_progress(
                cap,
                roi=None,
                motion_threshold=100,
                cooldown_frames=10,
            ):
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

                class ProgressCapture:
                    def __init__(self, wrapped_cap):
                        self._wrapped_cap = wrapped_cap
                        self.frames_scanned = 0

                    def read(self):
                        ret, frame = self._wrapped_cap.read()
                        if ret:
                            self.frames_scanned += 1
                            if (
                                self.frames_scanned == 1
                                or self.frames_scanned % 15 == 0
                            ):
                                record_raw_scan_progress(
                                    self.frames_scanned,
                                    total_frames,
                                )
                        else:
                            record_raw_scan_progress(
                                self.frames_scanned,
                                total_frames,
                                force=True,
                            )
                        return ret, frame

                    def __getattr__(self, name):
                        return getattr(self._wrapped_cap, name)

                progress_cap = ProgressCapture(cap)
                try:
                    yield from original_selected_frames(
                        progress_cap,
                        roi=roi,
                        motion_threshold=motion_threshold,
                        cooldown_frames=cooldown_frames,
                    )
                finally:
                    record_raw_scan_progress(
                        progress_cap.frames_scanned,
                        total_frames,
                        force=True,
                    )

            return selected_frames_with_raw_progress

        record_status("Loading vehicle detector...", force=True)
        live_results = []

        def on_result(result):
            live_results.append(result)

        def on_status(payload):
            message = payload.get("message", "Processing video...")
            event = payload.get("event")
            summary = st.session_state.setdefault("run_summary", empty_run_summary())

            if event == "frame_started":
                summary["selected_frames_processed"] = max(
                    summary["selected_frames_processed"],
                    int(payload.get("frame_index", 0)) + 1,
                )
            elif event == "vehicles_detected":
                summary["vehicles_seen"] += int(payload.get("vehicle_count", 0))
            elif event == "plate_detected":
                summary["plates_detected"] += 1
            elif event == "ocr_started":
                summary["ocr_attempts"] += 1
            elif event == "detection_succeeded":
                summary["ocr_successes"] += 1
                summary["detections_found"] = int(
                    payload.get("detection_count", summary["detections_found"])
                )

            append_processing_log(message)
            refresh_processing_ui(force=event in {"detection_succeeded", "ocr_failed"})

        try:
            with st.status("Loading models...", expanded=True) as status:
                st.write("Loading vehicle detector...")
                vehicle_detector = load_vehicle_detector(vehicle_model_path())

                record_status("Loading license plate detector...", force=True)
                st.write("Loading license plate detector...")
                plate_detector = load_plate_detector(model_path())

                record_status("Loading OCR model...", force=True)
                st.write("Loading OCR model...")
                ocr = load_ocr()

                record_status("Models loaded", force=True)
                record_status("Preparing video scan...", force=True)
                status.update(label="Models loaded", state="complete")

            original_selected_frames = pipeline.selected_frames
            pipeline.selected_frames = wrap_selected_frames_with_raw_progress(
                original_selected_frames
            )
            try:
                results = pipeline.process_video(
                    video_path=video_path,
                    roi=roi,
                    save_to_db=save_to_db,
                    progress_callback=on_result,
                    include_images=True,
                    vehicle_detector=vehicle_detector,
                    plate_detector=plate_detector,
                    ocr=ocr,
                    status_callback=on_status,
                )
            finally:
                pipeline.selected_frames = original_selected_frames

            st.session_state["results"] = results
            st.session_state["run_summary"]["detections_found"] = len(results)
            st.session_state["last_status"] = (
                f"Finished. Found {len(results)} detection(s)."
            )
            st.success(f"Finished. Found {len(results)} detection(s).")
            status_placeholder.success(st.session_state["last_status"])
            render_run_summary(summary_placeholder)

        except Exception as e:
            st.error(str(e))
            st.exception(e)

    st.subheader("Results")
    render_results(st.session_state.get("results", []))
else:
    st.info("Upload a video to configure ROI and run detection.")

cleanup_pending_temp_dirs()
