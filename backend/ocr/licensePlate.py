import os
import uuid
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PlateDetectionResult:
    coords: tuple[float, float, float, float]
    confidence: float


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    segments: list[str]
    segment_confidences: list[float]


class LicensePlateDetection:
    def __init__(self, yolo_path):
        from ultralytics import YOLO

        self.model = YOLO(yolo_path)

    def license_coordinates(self, frame, min_confidence=0.0):
        results = self.model([frame], stream=True)

        best_box = None
        best_conf = 0.0

        for result in results:
            for box in result.boxes:
                conf = float(box.conf)
                x1, y1, x2, y2 = box.xyxy.numpy()[0]
                print(
                    f"Detection | conf: {conf:.2%} | size: {int(x2 - x1)}x{int(y2 - y1)}px"
                )

                # No threshold — take the highest confidence box
                if conf > best_conf:
                    best_conf = conf
                    best_box = (x1, y1, x2, y2)

        if best_box is not None and best_conf >= min_confidence:
            print(f"Best detection chosen: conf {best_conf:.2%}")
            return PlateDetectionResult(coords=best_box, confidence=best_conf)

        if best_box is not None:
            print(
                f"Best detection below threshold: conf {best_conf:.2%}, "
                f"threshold {min_confidence:.2%}"
            )
        else:
            print("No detections at all")
        return None

    def crop_into_plate(self, frame, x1, y1, x2, y2):
        plate_img = frame[int(y1) : int(y2), int(x1) : int(x2)]
        # Upscaling
        h, w = plate_img.shape[:2]
        min_width = 100
        if w < min_width:
            scale = min_width / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            plate_img = cv2.resize(
                plate_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC
            )
        return plate_img


class PaddleInference:
    def __init__(self, debug=False, debug_dir=None):
        from paddleocr import PaddleOCR

        self.debug = debug
        self.debug_dir = debug_dir
        self.pipeline = PaddleOCR(use_angle_cls=False, lang="en")

    def preprocess_for_ocr(self, plate_img):

        # Convert to grayscale
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)

        # Boost contrast
        gray = cv2.equalizeHist(gray)

        # Sharpen
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        gray = cv2.filter2D(gray, -1, kernel)

        # Convert back to BGR
        processed = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        if self.debug:
            debug_dir = self.debug_dir or "."
            os.makedirs(debug_dir, exist_ok=True)
            debug_id = uuid.uuid4().hex
            cv2.imwrite(
                os.path.join(debug_dir, f"debug_plate_{debug_id}_upscaled.jpg"),
                plate_img,
            )
            cv2.imwrite(
                os.path.join(debug_dir, f"debug_plate_{debug_id}_processed.jpg"),
                processed,
            )

        return processed

    def ocr_inference(self, plate_img):
        processed = self.preprocess_for_ocr(plate_img)
        output = self.pipeline.ocr(processed)

        all_texts = []
        all_scores = []
        if output and output[0]:
            for line in output[0]:
                text = line[1][0]
                score = line[1][1]
                all_texts.append(text)
                all_scores.append(score)

        if all_texts:
            text = " ".join(all_texts)
            confidence = sum(all_scores) / len(all_scores)
            print(f"PLATE TEXT : {text}")
            for text, score in zip(all_texts, all_scores, strict=False):
                print(f"  '{text}' — confidence: {score:.2%}")
            return OCRResult(
                text=" ".join(all_texts),
                confidence=confidence,
                segments=all_texts,
                segment_confidences=all_scores,
            )
        else:
            print("Could not read plate text")

        return None
