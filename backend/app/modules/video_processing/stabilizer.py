from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class FrameTrack:
    time_sec: float
    face_x: float  # pixel x center
    is_scene_cut: bool = False


@dataclass
class StabilizedTrack:
    time_sec: float
    crop_x: int


class CameraStabilizer:
    """
    Applies deadband hysteresis, exponential moving average (EMA),
    and instant scene-cut resets to eliminate camera jitter while reframing.
    """
    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        crop_width: int,
        deadband_ratio: float = 0.20,
        ema_alpha: float = 0.10,
    ):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.crop_width = crop_width
        self.max_x = max(0, frame_width - crop_width)
        self.deadband_pixels = crop_width * deadband_ratio
        self.ema_alpha = ema_alpha

    def stabilize(self, tracks: List[FrameTrack]) -> List[StabilizedTrack]:
        if not tracks:
            center_x = (self.max_x // 2) & ~1
            return [StabilizedTrack(time_sec=0.0, crop_x=center_x)]

        output: List[StabilizedTrack] = []
        
        # Initialize camera centered or at first face
        first_face = tracks[0].face_x
        current_x = self._target_crop_x(first_face)

        for track in tracks:
            ideal_target = self._target_crop_x(track.face_x)

            if track.is_scene_cut:
                # Instant snap on hard scene cut — no panning across cuts
                current_x = ideal_target
            else:
                # Check deadband
                delta = ideal_target - current_x
                if abs(delta) > self.deadband_pixels:
                    # Move towards target only when drifting outside deadband
                    current_x += self.ema_alpha * delta

            # Clamp and enforce even number for FFmpeg pixel formats
            clamped_x = max(0.0, min(float(self.max_x), current_x))
            even_x = int(round(clamped_x)) & ~1
            output.append(StabilizedTrack(time_sec=track.time_sec, crop_x=even_x))

        return output

    def _target_crop_x(self, face_x: float) -> float:
        """Calculate ideal crop left position centered on face_x."""
        raw_x = face_x - (self.crop_width / 2.0)
        return max(0.0, min(float(self.max_x), raw_x))
