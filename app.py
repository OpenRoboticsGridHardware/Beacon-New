import cv2
import numpy as np
import time
import logging
from threading import Thread, Event
from flask import Flask, Response
from redis import ConnectionPool, Redis
import os
import redis

# Configuration for connecting to Redis
redis_config = {
    "server": os.getenv('REDIS_HOST', 'localhost'),
    "passwd": os.getenv('REDIS_PASSWORD', ''),
    "port": int(os.getenv('REDIS_PORT', 6379)),
    "db": 0
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class CamStream:
    def __init__(self, cam_addr_list, image_size=(640,480), fps=30, use_cache=False):
        self._cams = [cv2.VideoCapture(addr) for addr in cam_addr_list]
        self.fps = fps
        self._image_size = image_size
        self._use_cache = use_cache
        self.latest_frame = None
        self._cache_running = False
        if self._use_cache:
            self._redis_db = self._get_redis_conn(host=redis_config["server"],
                                                  passwd=redis_config["passwd"],
                                                  port=redis_config["port"],
                                                  db=redis_config["db"])
            self._queue_name = "video"
            self._queue_length = 1000000 # Adjust based on calculated value

    def _get_redis_conn(self, host, passwd, port, db):
        pool = ConnectionPool(host=host, password=passwd, port=port, db=db)
        redis_db = Redis(connection_pool=pool)
        return redis_db

    def start_cache(self):
        """Start capturing frames and caching them."""
        self._start_caching = Event()
        self._cache_running = True
        self.p = Thread(target=self._cache_image, args=(self._cams,))
        self.p.start()
        return self

    def _cache_image(self, cams):
        """Capture and cache frames asynchronously."""
        while not self._start_caching.is_set():
            try:
                frames = [self._capture_frame(cam) for cam in cams]
                if frames:
                    self.latest_frame = frames[0]  # Keep the latest frame for immediate use
                    if self._use_cache:
                        frames = np.stack(frames)
                        info = frames.tobytes()
                        self._redis_db.rpush(self._queue_name, info)
                        self._redis_db.ltrim(self._queue_name, 0, self._queue_length)
                        logger.info("Frame cached successfully")
                else:
                    logger.warning("No frames captured for caching")
            except Exception as e:
                logger.error(f"Error in caching frames: {e}")
            time.sleep(1 / self.fps)

    def _capture_frame(self, cam):
        """Capture a frame from the camera and resize it."""
        ret, frame = cam.read()
        if ret:
            if self._image_size:
                frame = cv2.resize(frame, self._image_size)
            return frame
        logger.warning("Failed to capture frame from camera")
        return np.zeros((self._image_size[1], self._image_size[0], 3), dtype=np.uint8)

    def stop_cache(self):
        """Stop caching and release cameras."""
        self._start_caching.set()
        self.p.join(timeout=0.5)
        self._cache_running = False
        for cam in self._cams:
            cam.release()
        return self

    def capture(self):
        """Capture the latest frame either from live feed or cache."""
        if not self._cache_running:
            frames = [self._capture_frame(cam) for cam in self._cams]
            if frames:
                return frames[0]
            else:
                logger.error("Failed to capture frame from all cameras")
                return np.zeros((self._image_size[1], self._image_size[0], 3), dtype=np.uint8)

        # Use the latest live frame for immediate streaming
        if self.latest_frame is not None:
            return self.latest_frame
        else:
            logger.warning("No live frame available, attempting to fetch from cache")
            if self._use_cache:
                return self._fetch_from_cache()
            return np.zeros((self._image_size[1], self._image_size[0], 3), dtype=np.uint8)

    def _fetch_from_cache(self):
        """Fetch a frame from the Redis cache if available."""
        frame_buf = self._redis_db.lpop(self._queue_name)
        if frame_buf:
            buffer_size = len(frame_buf)
            frame_size = self._image_size[0] * self._image_size[1] * 3
            frames_count = buffer_size // frame_size

            logger.info(f"Buffer size: {buffer_size}, Frame size: {frame_size}, Frames count: {frames_count}")

            if buffer_size % frame_size == 0:
                frames = np.reshape(
                    np.frombuffer(frame_buf, dtype=np.uint8),
                    (frames_count, self._image_size[1], self._image_size[0], 3)
                )
                return frames[0]  # Return the first frame from the batch
            else:
                logger.error("Buffer size does not match expected size for reshaping")
        return np.zeros((self._image_size[1], self._image_size[0], 3), dtype=np.uint8)

def generate_frames(cs):
    """Generator function that continuously yields frames as MJPEG."""
    while True:
        frame = cs.capture()  # Get the latest frame (either live or cached)
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            logger.error("Failed to encode frame")
            continue
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(1 / cs.fps)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(cs), mimetype='multipart/x-mixed-replace; boundary=frame')


def test_cam_stream():
    global cs
    addr = [0]  # Change camera address to your specific camera device
    cs = CamStream(addr, (640, 480), use_cache=True, fps=30)
    cs.start_cache()

    # SSL certificates for HTTPS
    cert_file = 'cert.pem'
    key_file = 'key.pem'

    # Run Flask app with SSL support
    app.run(host='0.0.0.0', port=5000, ssl_context=(cert_file, key_file), threaded=True, use_reloader=False)

if __name__ == "__main__":
    test_cam_stream()