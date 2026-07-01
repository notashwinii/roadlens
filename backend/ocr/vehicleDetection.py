from ultralytics import YOLO


class VehicleDetection:
    def __init__(self, yolo_model):
        self.model = YOLO(yolo_model)

    def vehicle_coordinates(self, frame, conf_threshold=0.35):
        results = self.model([frame], stream=False)
        detections = []
        vehicle_classes = {"car", "motorcycle", "bus", "truck"}

        for result in results:
            for box in result.boxes:
                cls = int(box.cls)
                conf = float(box.conf)
                class_name = self.model.names[cls]

                if class_name not in vehicle_classes or conf < conf_threshold:
                    continue

                x1, y1, x2, y2 = box.xyxy.cpu().numpy()[0]
                detections.append((class_name, conf, x1, y1, x2, y2))

        return detections

    def crop_vehicle(self, frame, x1, y1, x2, y2):
        height, width = frame.shape[:2]
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(width, int(x2))
        y2 = min(height, int(y2))

        return frame[y1:y2, x1:x2]
