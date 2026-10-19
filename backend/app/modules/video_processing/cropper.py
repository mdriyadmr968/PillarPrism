from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from backend.app.modules.video_processing.stabilizer import StabilizedTrack


@dataclass
class CropPlan:
    crop_width: int
    crop_height: int
    is_dynamic: bool
    static_x: int
    sendcmd_path: Optional[Path] = None
    filter_string: str = ""


class VideoCropper:
    def __init__(self, target_aspect_ratio: float = 9.0 / 16.0):
        self.target_aspect_ratio = target_aspect_ratio

    def calculate_crop_dimensions(self, width: int, height: int) -> tuple[int, int]:
        if height <= 0 or width <= 0:
            return 1080, 1920

        current_ratio = width / height
        if current_ratio >= self.target_aspect_ratio:
            # Widescreen or square (e.g. 16:9, 4:3, 1:1) -> crop width, maintain full height
            crop_h = height & ~1
            raw_w = int(round(height * self.target_aspect_ratio))
            crop_w = min(width, raw_w) & ~1
        else:
            # Narrower than 9:16 -> maintain width, crop height
            crop_w = width & ~1
            raw_h = int(round(width / self.target_aspect_ratio))
            crop_h = min(height, raw_h) & ~1

        return max(2, crop_w), max(2, crop_h)

    def build_crop_plan(
        self,
        width: int,
        height: int,
        tracks: List[StabilizedTrack],
        output_dir: Optional[Path] = None,
        clip_id: str = "clip"
    ) -> CropPlan:
        crop_w, crop_h = self.calculate_crop_dimensions(width, height)
        max_x = max(0, width - crop_w)

        if not tracks:
            center_x = (max_x // 2) & ~1
            filter_str = f"crop={crop_w}:{crop_h}:{center_x}:0"
            return CropPlan(
                crop_width=crop_w,
                crop_height=crop_h,
                is_dynamic=False,
                static_x=center_x,
                filter_string=filter_str
            )

        # Check coordinate variance: if variation is <= 10 pixels, keep static
        x_values = [t.crop_x for t in tracks]
        min_x = min(x_values)
        max_val_x = max(x_values)

        if max_val_x - min_x <= 12 or len(tracks) <= 1:
            avg_x = (int(round(sum(x_values) / len(x_values))) & ~1)
            avg_x = max(0, min(max_x, avg_x))
            filter_str = f"crop={crop_w}:{crop_h}:{avg_x}:0"
            return CropPlan(
                crop_width=crop_w,
                crop_height=crop_h,
                is_dynamic=False,
                static_x=avg_x,
                filter_string=filter_str
            )

        # Dynamic tracking via FFmpeg sendcmd script
        if output_dir:
            output_dir = Path(output_dir).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            sendcmd_file = output_dir / f"{clip_id}_crop.cmd"
        else:
            sendcmd_file = Path(f"{clip_id}_crop.cmd").resolve()

        initial_x = tracks[0].crop_x
        # Build sendcmd commands formatted for FFmpeg
        # Format: <time> [enter] crop@c1 x <val>;
        first_time = tracks[0].time_sec
        cmd_lines = []
        for t in tracks:
            rel_t = max(0.0, round(t.time_sec - first_time, 3))
            cmd_lines.append(f"{rel_t:.3f} [enter] crop@c1 x {t.crop_x};")

        with open(sendcmd_file, "w", encoding="utf-8") as f:
            f.write("\n".join(cmd_lines) + "\n")

        # Format relative path for FFmpeg filter on Windows without drive colons
        import os
        try:
            rel_sendcmd = os.path.relpath(sendcmd_file).replace(os.sep, "/")
        except Exception:
            rel_sendcmd = str(sendcmd_file).replace("\\", "/").replace(":", "\\:")

        filter_str = f"sendcmd=f={rel_sendcmd},crop@c1=w={crop_w}:h={crop_h}:x={initial_x}:y=0"

        return CropPlan(
            crop_width=crop_w,
            crop_height=crop_h,
            is_dynamic=True,
            static_x=initial_x,
            sendcmd_path=sendcmd_file,
            filter_string=filter_str
        )
