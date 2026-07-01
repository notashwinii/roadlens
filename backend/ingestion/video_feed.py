import cv2

from ingestion.cropping import cropping_selection
from ingestion.roi import clamp_roi_to_shape


def calculate_sharpness(img):
    # Calculates the Laplacian variance to measure blurriness
    return cv2.Laplacian(img, cv2.CV_64F).var()


def _clip_rect(rect, frame_shape):
    return clamp_roi_to_shape(rect, frame_shape)


def _crop_with_rect(frame, rect):
    x, y, w, h = _clip_rect(rect, frame.shape)
    return frame[y : y + h, x : x + w], (x, y, w, h)


def selected_frames(cap, roi=None, motion_threshold=100, cooldown_frames=10):
    best_frame = None
    best_frame_number = None
    best_roi = None
    best_metadata = None
    max_score = -1
    frames_since_motion = 0
    frame_number = -1
    fps = cap.get(cv2.CAP_PROP_FPS) or 0

    rects = cropping_selection(cap) if roi is None else [roi]

    if rects is None:
        return
    object_detectors = [
        cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=16) for _ in rects
    ]

    while cap.isOpened():
        ret, current_frame = cap.read()
        if not ret:
            if best_frame is not None:
                yield {
                    "image": best_frame,
                    "frame_number": best_frame_number,
                    "roi": best_roi,
                    **best_metadata,
                    "selection_reason": "end_of_video",
                }
            return

        frame_number += 1
        active_motion = False

        for rect, object_detector in zip(rects, object_detectors, strict=False):
            cropped_frame, clipped_roi = _crop_with_rect(current_frame, rect)
            mask = object_detector.apply(cropped_frame)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > motion_threshold:
                    active_motion = True
                    score = calculate_sharpness(cropped_frame)
                    final_score = score * area

                    if final_score > max_score:
                        max_score = final_score
                        best_frame = cropped_frame.copy()
                        best_frame_number = frame_number
                        best_roi = clipped_roi
                        timestamp_seconds = (
                            frame_number / fps if fps and fps > 0 else None
                        )
                        best_metadata = {
                            "motion_area": area,
                            "sharpness": score,
                            "score": final_score,
                            "timestamp_seconds": timestamp_seconds,
                        }

        if active_motion:
            frames_since_motion = 0
            continue

        frames_since_motion += 1
        if best_frame is not None and frames_since_motion > cooldown_frames:
            yield {
                "image": best_frame,
                "frame_number": best_frame_number,
                "roi": best_roi,
                **best_metadata,
                "selection_reason": "motion_cooldown",
            }
            best_frame = None
            best_frame_number = None
            best_roi = None
            best_metadata = None
            max_score = -1


def frame(cap, roi=None):
    for selected_frame in selected_frames(cap, roi=roi):
        yield selected_frame["image"]
