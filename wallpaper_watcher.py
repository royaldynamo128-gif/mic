#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import logging

# Setup logging
log_path = "/home/rai/Scripts/wallpaper_watcher.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout)
    ]
)

WATCH_FILE = "/home/rai/Downloads/videoplayback.mp4"
PLAY_FILE = "/home/rai/Downloads/videoplayback_h264.mp4"

def get_video_info(filepath):
    """Returns (codec_name, width, height) of the video using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height",
            "-of", "csv=p=0",
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        parts = result.stdout.strip().split(",")
        if len(parts) >= 3:
            return parts[0], int(parts[1]), int(parts[2])
    except Exception as e:
        logging.error(f"Error checking video properties of {filepath}: {e}")
    return None, None, None

def transcode_video(src, dst):
    """Transcodes the source video to a standard, hardware-accelerated high-quality H.264 format."""
    logging.info(f"Analyzing source video: {src}")
    codec, width, height = get_video_info(src)
    logging.info(f"Video detected: Codec={codec}, Size={width}x{height}")

    # Build the ffmpeg command. If it's already H.264, we can copy it directly.
    # Otherwise, we transcode to H.264 preserving the native resolution for maximum quality.
    if codec == "h264":
        logging.info("Video is already H.264. Copying file directly.")
        try:
            subprocess.run(["cp", src, dst], check=True)
            return True
        except Exception as e:
            logging.error(f"Failed to copy file: {e}")
            return False
    else:
        logging.info("Transcoding to high-quality H.264 via NVENC...")
        # Use hardware-accelerated Nvidia encoder with visually lossless constant quality (cq=18)
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "h264_nvenc",
            "-rc:v", "vbr",
            "-cq:v", "18",
            "-b:v", "0",
            "-preset", "slow",
            "-an",
            dst
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                logging.info("Hardware transcoding succeeded.")
                return True
        except Exception:
            pass
        
        logging.warning("Hardware NVENC encoding failed or unavailable. Falling back to software encoding (libx264)...")
        cmd_sw = [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-an",
            dst
        ]
        try:
            subprocess.run(cmd_sw, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info("Software transcoding succeeded.")
            return True
        except Exception as e:
            logging.error(f"Transcoding failed: {e}")
            return False

def update_static_wallpaper(src, frame_path):
    """Extracts the first frame of the video and sets it as the GNOME desktop background."""
    logging.info(f"Extracting preview frame from {src} to {frame_path}...")
    cmd = ["ffmpeg", "-y", "-i", src, "-vframes", "1", frame_path]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("Preview frame extracted successfully.")
        
        # Update GNOME GSettings
        uri = f"file://{frame_path}"
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri], check=True)
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri], check=True)
        logging.info(f"GNOME static wallpaper updated to {uri} for perfect blending.")
        return True
    except Exception as e:
        logging.error(f"Failed to update static wallpaper: {e}")
        return False

def update_hanabi_wallpaper(video_path):
    """Sets the Hanabi extension's video path via GSettings and updates static background."""
    update_static_wallpaper(video_path, "/home/rai/Downloads/videoplayback_frame.png")
    logging.info(f"Updating Hanabi video path to {video_path}...")
    try:
        # Schema path
        schema_dir = "/home/rai/.local/share/glib-2.0/schemas/"
        cmd = [
            "gsettings",
            "--schemadir", schema_dir,
            "set", "io.github.jeffshee.hanabi-extension",
            "video-path", f"'{video_path}'"
        ]
        subprocess.run(cmd, check=True)
        logging.info("Hanabi video-path updated successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to update Hanabi video path: {e}")
        return False

def main():
    logging.info("Starting live wallpaper watcher daemon...")
    last_mtime = None

    # Initial run check on startup
    if os.path.exists(WATCH_FILE):
        try:
            last_mtime = os.path.getmtime(WATCH_FILE)
            logging.info(f"Target wallpaper file found. Initializing...")
            if transcode_video(WATCH_FILE, PLAY_FILE):
                update_hanabi_wallpaper(PLAY_FILE)
        except Exception as e:
            logging.error(f"Initial setup failed: {e}")
    else:
        logging.warning(f"Target file {WATCH_FILE} not found on startup. Waiting for it to be created...")

    # Watch loop
    while True:
        try:
            if os.path.exists(WATCH_FILE):
                current_mtime = os.path.getmtime(WATCH_FILE)
                if last_mtime is None or current_mtime != last_mtime:
                    logging.info(f"Change detected in {WATCH_FILE}. Waiting for file write to complete...")
                    # Poll file size to make sure the write operation has finished
                    last_size = -1
                    while True:
                        time.sleep(1)
                        if not os.path.exists(WATCH_FILE):
                            break
                        curr_size = os.path.getsize(WATCH_FILE)
                        if curr_size == last_size and curr_size > 0:
                            break
                        last_size = curr_size
                    
                    logging.info("File write complete. Processing wallpaper...")
                    last_mtime = os.path.getmtime(WATCH_FILE)
                    if transcode_video(WATCH_FILE, PLAY_FILE):
                        update_hanabi_wallpaper(PLAY_FILE)
            else:
                if last_mtime is not None:
                    logging.warning(f"Watch file {WATCH_FILE} was removed.")
                    last_mtime = None
        except Exception as e:
            logging.error(f"Error in watch loop: {e}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()
