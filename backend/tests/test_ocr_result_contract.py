from ocr.licensePlate import OCRResult


def test_ocr_result_exposes_text_confidence_and_segments():
    result = OCRResult(
        text="BA 12 PA 3456",
        confidence=0.86,
        segments=["BA", "12", "PA", "3456"],
        segment_confidences=[0.84, 0.88, 0.85, 0.87],
    )

    assert result.text == "BA 12 PA 3456"
    assert result.confidence == 0.86
    assert result.segments == ["BA", "12", "PA", "3456"]
    assert result.segment_confidences == [0.84, 0.88, 0.85, 0.87]
