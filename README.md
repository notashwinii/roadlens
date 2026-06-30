# Speedotector

Speedotector is a motion-triggered ALPR prototype. It selects useful frames from video, detects license plates using YOLO, reads plate text using PaddleOCR, and optionally saves detections.

The demo uses `test_video.mp4` (project root), a YOLO license-plate model at `models/license_plate.pt`, OpenCV for video processing, and PaddleOCR for text recognition.

- `main.py` runs the command-line ALPR pipeline.
- `app.py` runs a Streamlit web UI for uploading a video, selecting an optional region of interest, and viewing detections.

1. `main.py` opens `test_video.mp4` and saves video metadata to the local database.
2. `ingestion/video_feed.py` scans the video and selects useful frames with motion and sharpness checks.
3. `ocr/licensePlate.py` loads the YOLO model and finds the best license-plate bounding box in each selected frame.
4. The detected plate region is cropped and lightly preprocessed for OCR.
5. PaddleOCR reads the cropped plate image.
6. The detected plate text and confidence values are printed in the terminal and persisted to the local DB (`db/`).

Note: To change the CLI demo video, model paths, thresholds, or storage behavior, edit or pass a RoadLens YAML config (see Config-Based Run).

## Requirements

- Python 3.11.
- The YOLO license-plate model at `models/license_plate.pt`.
- Optional database settings in `.env` or `DATABASE_URL` when saving detections.

If **Save results to database** is disabled in the Streamlit UI, no database connection is required.

## Run Modes

| Mode | Command | Notes |
|---|---|---|
| CLI local | `python main.py --config configs/default.yaml` | Uses the validated YAML config. |
| Web local | `streamlit run app.py` | Upload a video through the browser. Opens on `http://localhost:8501` by default. |
| CLI Docker | `docker compose -f docker/docker-compose.yml up --build app` | Runs `main.py` in the container. |
| Web Docker | `docker compose -f docker/docker-compose.yml up --build web` | Runs Streamlit on port `8501`. |
| Jupyter Docker | `docker compose -f docker/docker-compose.yml --profile lab up --build lab` | Optional notebook/lab environment on port `8888`. |

Stop Docker services with:

```bash
docker compose -f docker/docker-compose.yml down
```

## Local Setup

Create and activate a virtual environment:

```bash
python3 -m venv venv_paddle
source venv_paddle/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv venv_paddle
.\venv_paddle\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run checks:

```bash
ruff check .
pytest
```

## Config-Based Run

RoadLens can be run from a YAML configuration file:

```bash
python main.py --config configs/default.yaml
```

or:

```bash
ROADLENS_CONFIG=configs/default.yaml python main.py
```

The config controls:

- camera/video source
- model paths
- semantic zones and detection ROI
- frame-selection thresholds
- detection confidence thresholds
- storage behavior

Admin UI support will be added later. For now, YAML is the source of truth.

## Scene Calibration Preview

RoadLens supports semantic zone configuration through YAML. To preview configured zones on the first frame of a video:

```bash
python scripts/preview_zones.py --config configs/sample_camera.yaml --output outputs/zone_preview.jpg
```

Zones use normalized coordinates so they can be saved independently of a specific frame resolution. At runtime, RoadLens converts normalized zones into pixel-space runtime zones using the actual video frame size.

Supported zone types:

- `detection_roi`
- `stop_line`
- `zebra_crossing`
- `restricted_zone`
- `no_entry`

The current ALPR pipeline still uses `detection_roi` for frame selection. Violation rules will be added in a later step.

## Project Pipeline

1. `main.py` loads a typed YAML config and calls `process_video_from_config()` from `pipeline.py`; `app.py` still calls `process_video()` for uploaded videos.
2. `ingestion/video_feed.py` selects useful frames with motion and sharpness checks.
3. `ocr/licensePlate.py` uses YOLO to find the best license-plate bounding box.
4. The plate crop is preprocessed and sent to PaddleOCR.
5. Results include plate text, full-frame coordinates, detector confidence, OCR confidence, OCR segments, selected-frame metadata, and optional database IDs.

By default, pipeline results do not include raw image arrays. Streamlit requests `include_images=True` so it can display plate crops.

## Streamlit UI

1. Upload a video file (`mp4`, `mov`, `avi`, or `mkv`).
2. Keep **Use full frame** checked to process the whole frame, or uncheck it to select a region of interest.
3. When selecting a region of interest, draw a rectangle on the first-frame canvas or enter exact `x`, `y`, `width`, and `height` values manually.
4. Choose whether to save detections to the database.
5. Click **Run detection**.

Uploaded videos are written to an app-managed temp directory. Replacing or clearing an upload deletes the previous temp file, and the app removes stale `speedotector_streamlit_*` temp directories older than 24 hours on startup.

## Database Notes

Detection rows store:

- plate text,
- full-frame bounding-box coordinates,
- crop size,
- detector confidence,
- OCR confidence,
- creation timestamp.

Alembic manages schema migrations:

```bash
alembic upgrade head
```

For an existing database created before Alembic was added, confirm it matches the baseline schema, then run:

Create and activate a virtual environment:

```bash
python3 -m venv venv311
source venv311/bin/activate
```

Install dependencies:

```bash
alembic stamp 20260531_0001
alembic upgrade head
```

This stamps the original tables as the baseline and applies later detection-column migrations.

## Privacy Notes

Uploaded videos and detected license-plate crops can contain sensitive personal data. Keep **Save results to database** disabled unless persistence is intentional, and delete old database rows or temp files when they are no longer needed.

OCR debug images are disabled by default. If `PaddleInference(debug=True)` is enabled during development, debug files are written with unique filenames.

## Project Structure

```text
.
|-- docker/
|   |-- Dockerfile
|   `-- docker-compose.yml
|-- configs/
|   |-- default.yaml
|   `-- sample_camera.yaml
|-- core/
|   |-- config_loader.py
|   |-- config_schema.py
|   |-- config_validation.py
|   `-- config_writer.py
|-- ingestion/
|   |-- cropping.py
|   |-- roi.py
|   `-- video_feed.py
|-- scene/
|   |-- geometry.py
|   |-- runtime_zone.py
|   |-- scene_builder.py
|   `-- zone_renderer.py
|-- scripts/
|   `-- preview_zones.py
|-- db/
|   |-- database.py
|   |-- models.py
|   `-- repository.py
|-- models/
|   `-- license_plate.pt
|-- migrations/
|   |-- env.py
|   `-- versions/
|-- ocr/
|   `-- licensePlate.py
|-- alembic.ini
|-- tests/
|-- app.py
|-- main.py
|-- pipeline.py
|-- requirements.txt
`-- test_video.mp4
```
