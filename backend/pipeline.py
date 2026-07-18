import os

import cv2

from core.camera_source import capture_source_from_config
from ingestion.video_feed import selected_frames
from rules.action_runner import ActionRunner
from rules.conditions import ConditionProvider
from rules.events import generate_vehicle_zone_events
from rules.rule_engine import RuleEngine
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
    runtime_zones=None,
    rule_engine=None,
    action_runner=None,
    camera_id=None,
    camera_profile_id=None,
    save_evidence_images=False,
    output_dir="outputs/evidence",
    review_status_default="pending",
    save_selected_frame=True,
    save_vehicle_crop=True,
    save_plate_crop=True,
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
    action_runner = action_runner or ActionRunner()
    rules_enabled = (
        rule_engine is not None
        and getattr(rule_engine, "has_rules", False)
        and runtime_zones is not None
    )

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
            video = save_video(db, video_path, camera_id=camera_profile_id)

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

            rule_matches_by_vehicle = {}
            timestamp_seconds = frame_metadata.get("timestamp_seconds")

            if rules_enabled:
                vehicle_zone_events = generate_vehicle_zone_events(
                    vehicles,
                    runtime_zones,
                    frame_number=source_frame_number,
                    timestamp_seconds=timestamp_seconds,
                    bbox_offset=(roi_x, roi_y),
                )

                for vehicle_zone_event in vehicle_zone_events:
                    for rule in rule_engine.matching_rules(vehicle_zone_event):
                        rule_matches_by_vehicle.setdefault(
                            vehicle_zone_event.vehicle_index,
                            [],
                        ).append(
                            action_runner.build_match(
                                rule,
                                vehicle_zone_event,
                            )
                        )

            for vehicle_index, (
                vehicle_class,
                vehicle_confidence,
                vx1,
                vy1,
                vx2,
                vy2,
            ) in enumerate(vehicles, start=1):
                rule_matches = rule_matches_by_vehicle.get(vehicle_index, [])
                if rules_enabled and not rule_matches:
                    emit_status(
                        "rule_no_match",
                        (
                            f"Frame {index + 1}, vehicle {vehicle_index}: "
                            "no violation rule matched; skipping plate detection."
                        ),
                        frame_index=index,
                        source_frame_number=source_frame_number,
                        vehicle_index=vehicle_index,
                        vehicle_class=vehicle_class,
                        vehicle_confidence=vehicle_confidence,
                        vehicle_coords=(
                            roi_x + vx1,
                            roi_y + vy1,
                            roi_x + vx2,
                            roi_y + vy2,
                        ),
                    )
                    continue

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
                violation_event_id = None
                violation_event_ids = []
                evidence_artifacts = []

                if save_to_db and db is not None and video is not None:
                    from db.repository import (
                        save_detection,
                        save_evidence_artifact,
                        save_violation_event,
                    )

                    for rule_match in rule_matches:
                        violation_event = save_violation_event(
                            db,
                            video.id,
                            rule_match,
                            review_status=review_status_default,
                        )
                        violation_event_ids.append(violation_event.id)

                        if violation_event_id is None:
                            violation_event_id = violation_event.id

                        if save_evidence_images:
                            from evidence.artifact_writer import write_image_artifact

                            artifact_images = []
                            if save_selected_frame:
                                artifact_images.append(("selected_frame", frame_image))
                            if save_vehicle_crop:
                                artifact_images.append(("vehicle_crop", vehicle_crop))
                            if save_plate_crop:
                                artifact_images.append(("plate_crop", plate_img))

                            for artifact_type, artifact_image in artifact_images:
                                path, width, height = write_image_artifact(
                                    artifact_image,
                                    output_dir=output_dir,
                                    camera_id=camera_id or "unknown_camera",
                                    video_id=video.id,
                                    event_id=violation_event.id,
                                    artifact_type=artifact_type,
                                )
                                artifact = save_evidence_artifact(
                                    db,
                                    violation_event.id,
                                    artifact_type,
                                    path,
                                    width=width,
                                    height=height,
                                )
                                evidence_artifacts.append(
                                    {
                                        "id": artifact.id,
                                        "violation_event_id": violation_event.id,
                                        "type": artifact_type,
                                        "path": path,
                                        "width": width,
                                        "height": height,
                                    }
                                )

                    detection = save_detection(
                        db,
                        video.id,
                        plate_text,
                        full_frame_coords,
                        plate_img,
                        detector_confidence=detector_confidence,
                        ocr_confidence=ocr_result.confidence,
                        violation_event_id=violation_event_id,
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
                    "violation_event_id": violation_event_id,
                    "violation_event_ids": violation_event_ids,
                    "review_status": (
                        review_status_default
                        if violation_event_id is not None
                        else None
                    ),
                    "evidence_artifacts": evidence_artifacts,
                    "violation_candidate": bool(rule_matches),
                    "rule_matches": [
                        match.to_result_metadata() for match in rule_matches
                    ],
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
        "video_path": capture_source_from_config(config),
        "model_path": config.models.plate_detector,
        "vehicle_model_path": config.models.vehicle_detector,
        "roi": roi,
        "save_to_db": config.storage.save_to_db,
        "camera_id": config.camera.id,
        "save_evidence_images": config.storage.save_evidence_images,
        "output_dir": config.storage.output_dir,
        "review_status_default": config.storage.review_status_default,
        "save_selected_frame": config.storage.save_selected_frame,
        "save_vehicle_crop": config.storage.save_vehicle_crop,
        "save_plate_crop": config.storage.save_plate_crop,
        "min_detection_confidence": config.detection.plate_confidence,
        "motion_threshold": config.frame_selection.motion_threshold,
        "cooldown_frames": config.frame_selection.cooldown_frames,
        "vehicle_confidence": config.detection.vehicle_confidence,
    }

    if config.rules:
        from scene.scene_builder import build_scene_from_config

        scene = build_scene_from_config(config)
        process_kwargs.update(
            {
                "runtime_zones": scene.zones,
                "rule_engine": RuleEngine(
                    config.rules,
                    ConditionProvider(config.conditions),
                ),
                "action_runner": ActionRunner(),
            }
        )

    process_kwargs.update(overrides)

    return process_video(**process_kwargs)
