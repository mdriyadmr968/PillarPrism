from pathlib import Path
import pytest
from backend.app.modules.video_processing.stabilizer import (
    FrameTrack,
    CameraStabilizer,
)
from backend.app.modules.video_processing.cropper import VideoCropper
from backend.app.modules.video_processing.face_tracker import FaceTracker


def test_camera_stabilizer_deadband_and_cuts():
    # 1920x1080, crop 608 wide -> max_x = 1312
    stabilizer = CameraStabilizer(
        frame_width=1920,
        frame_height=1080,
        crop_width=608,
        deadband_ratio=0.20,  # 121.6 pixels deadband
        ema_alpha=0.50
    )

    # Face starts at 960 (center)
    tracks = [
        FrameTrack(time_sec=0.0, face_x=960.0),
        # Small head movement within deadband (30 pixels)
        FrameTrack(time_sec=0.5, face_x=990.0),
        # Another small movement within deadband
        FrameTrack(time_sec=1.0, face_x=940.0),
        # Hard scene cut jumping to 300
        FrameTrack(time_sec=1.5, face_x=300.0, is_scene_cut=True),
    ]

    stabilized = stabilizer.stabilize(tracks)
    assert len(stabilized) == 4

    # Initial position: centered
    first_x = stabilized[0].crop_x
    assert first_x % 2 == 0  # Even number for FFmpeg

    # Small movement at 0.5s: within deadband so camera position stays exactly locked
    assert stabilized[1].crop_x == first_x
    assert stabilized[2].crop_x == first_x

    # Scene cut at 1.5s: instantly snapped to left side
    cut_x = stabilized[3].crop_x
    assert cut_x < first_x
    assert cut_x % 2 == 0


def test_video_cropper_dimensions_and_plan(tmp_path: Path):
    cropper = VideoCropper(target_aspect_ratio=9.0 / 16.0)

    # Test dimension calculation
    crop_w, crop_h = cropper.calculate_crop_dimensions(1920, 1080)
    assert crop_h == 1080
    assert crop_w == 608  # 1080 * 9/16 = 607.5 -> rounded to even 608
    assert crop_w % 2 == 0

    crop_w_720, crop_h_720 = cropper.calculate_crop_dimensions(1280, 720)
    assert crop_h_720 == 720
    assert crop_w_720 % 2 == 0

    # Test static plan for low variance
    stabilizer = CameraStabilizer(1920, 1080, 608)
    static_tracks = stabilizer.stabilize([
        FrameTrack(time_sec=0.0, face_x=960),
        FrameTrack(time_sec=1.0, face_x=962),
    ])
    plan = cropper.build_crop_plan(1920, 1080, static_tracks, output_dir=tmp_path)
    assert plan.is_dynamic is False
    assert "crop=608:1080:" in plan.filter_string

    # Test dynamic plan with sendcmd
    dynamic_tracks = [
        stabilizer.stabilize([FrameTrack(time_sec=0.0, face_x=500)])[0],
        stabilizer.stabilize([FrameTrack(time_sec=2.0, face_x=1200)])[0],
    ]
    dynamic_plan = cropper.build_crop_plan(1920, 1080, dynamic_tracks, output_dir=tmp_path, clip_id="c1")
    assert dynamic_plan.is_dynamic is True
    assert dynamic_plan.sendcmd_path is not None
    assert dynamic_plan.sendcmd_path.exists()
    assert "sendcmd=" in dynamic_plan.filter_string


def test_face_tracker_execution(synthetic_video: Path):
    tracker = FaceTracker(sample_fps=5.0)
    tracks = tracker.track_clip(synthetic_video, start_sec=0.0, end_sec=1.5)
    assert len(tracks) > 0
    # Coordinates must be within video width
    for t in tracks:
        assert 0.0 <= t.face_x <= 1280.0
