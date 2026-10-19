import os
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np
from backend.app.modules.video_processing.stabilizer import FrameTrack


class FaceTracker:
    def __init__(self, sample_fps: float = 6.0):
        self.sample_fps = sample_fps
        self._cascade: Optional[cv2.CascadeClassifier] = None

    def _get_cascade(self) -> Optional[cv2.CascadeClassifier]:
        if self._cascade is None:
            # Check bundled model file in this module's directory
            local_path = Path(__file__).parent / "haarcascade_frontalface_default.xml"
            if local_path.exists():
                self._cascade = cv2.CascadeClassifier(str(local_path))
                return self._cascade

            # Check cv2.data.haarcascades
            if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
                cv_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                if os.path.exists(cv_path):
                    self._cascade = cv2.CascadeClassifier(cv_path)
                    return self._cascade
        return self._cascade

    def track_clip(
        self,
        video_path: Path,
        start_sec: float,
        end_sec: float,
    ) -> List[FrameTrack]:
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_path}")

        try:
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
            default_center_x = float(width / 2.0)

            frame_step = max(1, int(round(native_fps / self.sample_fps)))
            start_frame = int(round(start_sec * native_fps))
            end_frame = int(round(end_sec * native_fps))

            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            cascade = self._get_cascade()

            tracks: List[FrameTrack] = []
            prev_hist: Optional[np.ndarray] = None
            last_known_x = default_center_x
            current_frame_idx = start_frame

            while current_frame_idx <= end_frame:
                ret, frame = cap.read()
                if not ret:
                    break

                if (current_frame_idx - start_frame) % frame_step == 0:
                    current_time = round(current_frame_idx / native_fps, 3)

                    # Compute scene cut metric via HSV histogram
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                    is_scene_cut = False
                    if prev_hist is not None:
                        similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                        if similarity < 0.35:
                            is_scene_cut = True
                    prev_hist = hist

                    # Face Detection on downscaled grayscale frame for speed
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    scale_factor = 0.5
                    small_gray = cv2.resize(gray, (0, 0), fx=scale_factor, fy=scale_factor)

                    faces = []
                    if cascade is not None:
                        faces = cascade.detectMultiScale(
                            small_gray,
                            scaleFactor=1.1,
                            minNeighbors=4,
                            minSize=(30, 30)
                        )

                    if len(faces) > 0:
                        # If multiple faces, pick the largest face (dominant speaker)
                        largest_face = max(faces, key=lambda b: b[2] * b[3])
                        fx, fy, fw, fh = largest_face
                        # Scale back to original coordinates
                        face_center_x = (fx + fw / 2.0) / scale_factor
                        last_known_x = face_center_x
                    else:
                        face_center_x = last_known_x

                    tracks.append(FrameTrack(
                        time_sec=current_time,
                        face_x=face_center_x,
                        is_scene_cut=is_scene_cut
                    ))

                current_frame_idx += 1

            return tracks
        finally:
            cap.release()
