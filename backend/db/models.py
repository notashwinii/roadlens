from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    date_processed: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="video",
        cascade="all, delete-orphan",
    )
    violation_events: Mapped[list["ViolationEvent"]] = relationship(
        "ViolationEvent",
        back_populates="video",
        cascade="all, delete-orphan",
    )


class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    zone_type: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_class: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_x1: Mapped[float] = mapped_column(Float, nullable=False)
    vehicle_y1: Mapped[float] = mapped_column(Float, nullable=False)
    vehicle_x2: Mapped[float] = mapped_column(Float, nullable=False)
    vehicle_y2: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    video: Mapped[Video] = relationship("Video", back_populates="violation_events")
    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="violation_event",
    )
    artifacts: Mapped[list["EvidenceArtifact"]] = relationship(
        "EvidenceArtifact",
        back_populates="violation_event",
        cascade="all, delete-orphan",
    )


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    violation_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("violation_events.id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    violation_event: Mapped[ViolationEvent] = relationship(
        "ViolationEvent",
        back_populates="artifacts",
    )


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id"), nullable=False, index=True
    )
    violation_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("violation_events.id"), nullable=True, index=True
    )
    plate_text: Mapped[str] = mapped_column(String(50), nullable=False)
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)
    x2: Mapped[float] = mapped_column(Float, nullable=False)
    y2: Mapped[float] = mapped_column(Float, nullable=False)
    crop_width: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_height: Mapped[int] = mapped_column(Integer, nullable=False)
    detector_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    video: Mapped[Video] = relationship("Video", back_populates="detections")
    violation_event: Mapped[ViolationEvent | None] = relationship(
        "ViolationEvent",
        back_populates="detections",
    )
