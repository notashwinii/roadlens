import os

import cv2

from ingestion.video_feed import selected_frames
from scene.scene_builder import runtime_roi_for_video


def process_video(
    video_path,
    model_path=None,
    vehicle_model_path=None,
    roi=None,
    save_to_db=True,
    progress_callback=None,
    include_images=False,
    vehicle_detector=None,
    plate_detector=None,
    ocr=None,
    min_detection_confidence=0.0,
    motion_threshold=100,
    cooldown_frames=10,
    vehicle_confidence=0.35,
    status_callback=None,
):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    def emit_status(event, message, **data):
        payload = {"event": event, "message": message, **data}
        print(message, flush=True)
        if status_callback:
            status_callback(payload)

    if model_path is None:
        model_path = os.path.join(script_dir, "models", "license_plate.pt")

    if vehicle_model_path is None:
        vehicle_model_path = "yolo26n.pt"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    db = None
    video = None
    results = []

    try:
        if vehicle_detector is None:
            from ocr.vehicleDetection import VehicleDetection

            vehicle_detector = VehicleDetection(vehicle_model_path)

        if plate_detector is None or ocr is None:
            from ocr.licensePlate import LicensePlateDetection, PaddleInference

            plate_detector = plate_detector or LicensePlateDetection(model_path)
            ocr = ocr or PaddleInference()

        if save_to_db:
            from db.database import SessionLocal, create_tables
            from db.repository import save_video

            create_tables()
            db = SessionLocal()
            video = save_video(db, video_path)

        for index, selected_frame in enumerate(
            selected_frames(
                cap,
                roi=roi,
                motion_threshold=motion_threshold,
                cooldown_frames=cooldown_frames,
            )
        ):
            frame_image = selected_frame["image"]
            roi_x, roi_y, _, _ = selected_frame["roi"]
            source_frame_number = selected_frame["frame_number"]

            emit_status(
                "frame_started",
                (f"Frame {index + 1}: scanning source frame {source_frame_number}."),
                frame_index=index,
                source_frame_number=source_frame_number,
                roi=selected_frame["roi"],
            )

            frame_metadata = {
                key: value
                for key, value in selected_frame.items()
                if key not in {"image", "frame_number", "roi"}
            }

            vehicles = vehicle_detector.vehicle_coordinates(
                frame_image,
                conf_threshold=vehicle_confidence,
            )
            vehicle_count = len(vehicles)
            emit_status(
                "vehicles_detected",
                (
                    f"Frame {index + 1}: found {vehicle_count} vehicle"
                    f"{'' if vehicle_count == 1 else 's'}."
                ),
                frame_index=index,
                source_frame_number=source_frame_number,
                vehicle_count=vehicle_count,
            )

            if not vehicles:
                emit_status(
                    "no_vehicles",
                    f"Frame {index + 1}: no vehicles found; skipping plate detection.",
                    frame_index=index,
                    source_frame_number=source_frame_number,
                )
                continue

            for vehicle_index, (
                vehicle_class,
                vehicle_confidence,
                vx1,
                vy1,
                vx2,
                vy2,
            ) in enumerate(vehicles, start=1):
                vehicle_x_offset = max(0, int(vx1))
                vehicle_y_offset = max(0, int(vy1))

                emit_status(
                    "plate_detection_started",
                    (
                        f"Frame {index + 1}, vehicle {vehicle_index}: "
                        f"checking {vehicle_class} for a plate."
                    ),
                    frame_index=index,
                    source_frame_number=source_frame_number,
                    vehicle_index=vehicle_index,
                    vehicle_class=vehicle_class,
                    vehicle_confidence=vehicle_confidence,
                    vehicle_coords=(vx1, vy1, vx2, vy2),
                )

                vehicle_crop = vehicle_detector.crop_vehicle(
                    frame_image,
                    vx1,
                    vy1,
                    vx2,
                    vy2,
                )

                if vehicle_crop.size == 0:
                    emit_status(
                        "vehicle_crop_empty",
                        (
                            f"Frame {index + 1}, vehicle {vehicle_index}: "
                            "vehicle crop was empty; skipping."
                        ),
                        frame_index=index,
                        source_frame_number=source_frame_number,
                        vehicle_index=vehicle_index,
                    )
                    continue

                detection_result = plate_detector.license_coordinates(
                    vehicle_crop,
                    min_confidence=min_detection_confidence,
                )

                if detection_result is None:
                    emit_status(
                        "no_plate_detected",
                        (
                            f"Frame {index + 1}, vehicle {vehicle_index}: "
                            "no plate detected."
                        ),
                        frame_index=index,
                        source_frame_number=source_frame_number,
                        vehicle_index=vehicle_index,
                    )
                    continue

                roi_plate_coords = detection_result.coords
                detector_confidence = detection_result.confidence
                x1, y1, x2, y2 = roi_plate_coords
                emit_status(
                    "plate_detected",
                    (
                        f"Frame {index + 1}, vehicle {vehicle_index}: "
                        f"plate detected at {roi_plate_coords}."
                    ),
                    frame_index=index,
                    source_frame_number=source_frame_number,
                    vehicle_index=vehicle_index,
                    roi_plate_coords=roi_plate_coords,
                    detector_confidence=detector_confidence,
                )

                plate_img = plate_detector.crop_into_plate(
                    vehicle_crop,
                    x1,
                    y1,
                    x2,
                    y2,
                )

                emit_status(
                    "ocr_started",
                    f"Frame {index + 1}, vehicle {vehicle_index}: running OCR.",
                    frame_index=index,
                    source_frame_number=source_frame_number,
                    vehicle_index=vehicle_index,
                )
                ocr_result = ocr.ocr_inference(plate_img)

                if not ocr_result:
                    emit_status(
                        "ocr_failed",
                        (f"Frame {index + 1}, vehicle {vehicle_index}: OCR failed."),
                        frame_index=index,
                        source_frame_number=source_frame_number,
                        vehicle_index=vehicle_index,
                    )
                    continue

                plate_text = ocr_result.text

                # Main-branch equivalent coordinate math:
                # ROI offset + vehicle offset + plate offset inside vehicle.
                full_frame_coords = (
                    roi_x + vehicle_x_offset + x1,
                    roi_y + vehicle_y_offset + y1,
                    roi_x + vehicle_x_offset + x2,
                    roi_y + vehicle_y_offset + y2,
                )

                detection_id = None

                if save_to_db and db is not None and video is not None:
                    from db.repository import save_detection

                    detection = save_detection(
                        db,
                        video.id,
                        plate_text,
                        full_frame_coords,
                        plate_img,
                        detector_confidence=detector_confidence,
                        ocr_confidence=ocr_result.confidence,
                    )
                    detection_id = detection.id

                result = {
                    "frame_index": index,
                    "plate_text": plate_text,
                    "coords": full_frame_coords,
                    "roi_coords": roi_plate_coords,
                    "source_frame_number": selected_frame["frame_number"],
                    "roi": selected_frame["roi"],
                    "vehicle_class": vehicle_class,
                    "vehicle_confidence": vehicle_confidence,
                    "vehicle_coords": (
                        roi_x + vx1,
                        roi_y + vy1,
                        roi_x + vx2,
                        roi_y + vy2,
                    ),
                    "crop_shape": tuple(int(value) for value in plate_img.shape),
                    "detector_confidence": detector_confidence,
                    "ocr_confidence": ocr_result.confidence,
                    "ocr_segments": ocr_result.segments,
                    "frame_metadata": frame_metadata,
                    "detection_id": detection_id,
                }

                if include_images:
                    result["plate_img"] = plate_img
                    result["vehicle_img"] = vehicle_crop

                results.append(result)

                if progress_callback:
                    progress_callback(result)

                emit_status(
                    "detection_succeeded",
                    (
                        f"Frame {index + 1}, vehicle {vehicle_index}: "
                        f"detected plate {plate_text}."
                    ),
                    frame_index=index,
                    source_frame_number=source_frame_number,
                    vehicle_index=vehicle_index,
                    plate_text=plate_text,
                    detection_count=len(results),
                    detector_confidence=detector_confidence,
                    ocr_confidence=ocr_result.confidence,
                )

    finally:
        cap.release()
        if db is not None:
            db.close()

    return results


def process_video_from_config(config, **overrides):
    roi = runtime_roi_for_video(config)

    process_kwargs = {
        "video_path": config.camera.source_path,
        "model_path": config.models.plate_detector,
        "vehicle_model_path": config.models.vehicle_detector,
        "roi": roi,
        "save_to_db": config.storage.save_to_db,
        "min_detection_confidence": config.detection.plate_confidence,
        "motion_threshold": config.frame_selection.motion_threshold,
        "cooldown_frames": config.frame_selection.cooldown_frames,
        "vehicle_confidence": config.detection.vehicle_confidence,
    }
    process_kwargs.update(overrides)

    return process_video(**process_kwargs)
