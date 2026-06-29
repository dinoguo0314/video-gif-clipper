"""
MCP Server for Video GIF Clipper
Exposes video-to-GIF conversion as an MCP tool for AI agents (e.g. Hermes).

Usage:
    python mcp_server.py

Then configure your AI agent to connect via stdio.
"""

import os
import sys
from pathlib import Path

# Allow importing core functions from the main module
sys.path.insert(0, str(Path(__file__).parent))
from video_gif_clipper import (
    setup_ffmpeg_path,
    get_video_duration,
    pick_non_overlapping_starts,
    clip_to_gif,
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("video-gif-clipper")
setup_ffmpeg_path()


@mcp.tool()
def convert_video_to_gifs(
    input_path: str,
    output_folder: str = "",
    count: int = 10,
    duration: int = 5,
    width: int = 480,
    fps: int = 15,
    colors: int = 256,
) -> str:
    """
    Randomly extract clips from a video and convert them to GIF files.

    Args:
        input_path:    Absolute path to the input video file.
        output_folder: Folder to save GIFs (default: same folder as input video).
        count:         Number of GIF clips to generate (default: 10).
        duration:      Duration of each clip in seconds (default: 5).
        width:         GIF width in pixels, height auto-scales (default: 480).
        fps:           Frames per second of the GIF (default: 15).
        colors:        Max colors in GIF palette, up to 256 (default: 256).

    Returns:
        Summary string listing output file paths and sizes.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Video file not found: {input_path}")

    out_dir = output_folder or str(Path(input_path).parent)
    os.makedirs(out_dir, exist_ok=True)

    total = get_video_duration(input_path)
    starts = pick_non_overlapping_starts(total, duration, count)
    stem = Path(input_path).stem
    saved = []

    for i, start in enumerate(starts, 1):
        out_file = os.path.join(out_dir, f"{stem}_clip{i:02d}_{int(start)}s.gif")
        clip_to_gif(input_path, start, duration, out_file, width, fps, colors)
        kb = os.path.getsize(out_file) // 1024
        saved.append(f"  [{i}] {os.path.basename(out_file)} ({kb} KB)")

    lines = [f"Done. {len(saved)} GIFs saved to: {out_dir}", ""] + saved
    return "\n".join(lines)


@mcp.tool()
def get_video_info(input_path: str) -> str:
    """
    Return the duration of a video file in seconds.

    Args:
        input_path: Absolute path to the video file.

    Returns:
        Duration string, e.g. "Duration: 120.5 seconds"
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Video file not found: {input_path}")
    duration = get_video_duration(input_path)
    return f"Duration: {duration:.2f} seconds"


if __name__ == "__main__":
    mcp.run()
