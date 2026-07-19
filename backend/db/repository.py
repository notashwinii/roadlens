import os

from db.models import Detection, EvidenceArtifact, Video, ViolationEvent


def save_video(db, video_path, camera_id=None):
    video_path = str(video_path)
    video = Video(
        file_name=os.path.basename(video_path),
        file_path=video_path,
        camera_id=camera_id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def save_detection(
    db,
    video_id,
    plate_text,
    coords,
    plate_img,
    detector_confidence=None,
    ocr_confidence=None,
    violation_event_id=None,
):
    x1, y1, x2, y2 = coords
    crop_height, crop_width = plate_img.shape[:2]

    detection = Detection(
        video_id=video_id,
        plate_text=plate_text,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        crop_width=crop_width,
        crop_height=crop_height,
        detector_confidence=detector_confidence,
        ocr_confidence=ocr_confidence,
        violation_event_id=violation_event_id,
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)
    return detection


def save_violation_event(
    db,
    video_id,
    rule_match,
    review_status="pending",
):
    event = rule_match.event
    x1, y1, x2, y2 = event.vehicle_bbox

    violation_event = ViolationEvent(
        video_id=video_id,
        rule_id=rule_match.rule_id,
        rule_name=rule_match.rule_name,
        zone_id=event.zone_id,
        zone_type=event.zone_type,
        zone_name=event.zone_name,
        event_type=event.event,
        source_frame_number=event.frame_number,
        timestamp_seconds=event.timestamp_seconds,
        vehicle_class=event.vehicle_class,
        vehicle_confidence=event.vehicle_confidence,
        vehicle_x1=x1,
        vehicle_y1=y1,
        vehicle_x2=x2,
        vehicle_y2=y2,
        review_status=review_status,
    )
    db.add(violation_event)
    db.commit()
    db.refresh(violation_event)
    return violation_event


def save_evidence_artifact(
    db,
    violation_event_id,
    artifact_type,
    path,
    width=None,
    height=None,
):
    artifact = EvidenceArtifact(
        violation_event_id=violation_event_id,
        artifact_type=artifact_type,
        path=path,
        width=width,
        height=height,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact
