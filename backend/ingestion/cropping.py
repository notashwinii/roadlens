import cv2

from ingestion.roi import clamp_roi


def cropping_selection(cap):
    window_name = "Select Static Zones"
    ret, first_frame = cap.read()
    if not ret:
        print("Failed to read video")
        return None

    rects = cv2.selectROIs(window_name, first_frame, fromCenter=False)
    cv2.destroyWindow(window_name)

    if rects is None or len(rects) == 0:
        print(
            "No ROI selected. Select a region with Space/Enter, then press Escape to continue."
        )
        return None

    return rects


def ROI_cropping_all_frames(frame, rects):
    # Loop over the selected bounding boxes and crop them
    crops = []
    h_frame, w_frame = frame.shape[:2]
    for rect in rects:
        x, y, w, h = clamp_roi(*rect, w_frame, h_frame)
        crops.append(frame[y : y + h, x : x + w])
    return crops
