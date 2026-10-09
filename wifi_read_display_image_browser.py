#!/usr/bin/env python

import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import cv2
import numpy as np

# ESP32 Wi-Fi Access Point Settings
ESP32_IP = "192.168.4.1"
ESP32_PORT = 80

# Local Web Server Settings
WEB_HOST = "0.0.0.0"  # Listens on all local interfaces (accessible by VirtualBox / local network)
WEB_PORT = 8080

# Map ASCII characters matching ESP32 mapping (0 = Dark, 255 = Light)
GRAYSCALE_MAP = {
    ' ': 0,
    '.': 60,
    ':': 110,
    '*': 160,
    '#': 255
}

latest_jpeg_frame = None


def process_frame(lines):
    """Converts ASCII grid to a rotated binary mask and encodes it directly to JPEG."""
    matrix = []
    for line in lines:
        row = [GRAYSCALE_MAP.get(char, 0) for char in line]
        if row:
            matrix.append(row)

    if not matrix:
        return None

    max_received_width = max(len(row) for row in matrix)
    if max_received_width == 0:
        return None

    padded_matrix = [row + [0] * (max_received_width - len(row)) for row in matrix]
    img_array = np.array(padded_matrix, dtype=np.uint8)

    # Dynamic cropping of empty right border
    valid_cols = np.where(img_array.any(axis=0))[0]
    if len(valid_cols) > 0:
        crop_right = valid_cols[-1] + 1
        img_cropped = img_array[:, :crop_right]
    else:
        img_cropped = img_array

    # Rotate 90 degrees Clockwise
    rotated_img = cv2.rotate(img_cropped, cv2.ROTATE_90_COUNTERCLOCKWISE)

    # Thresholding (< 150 is Black, >= 150 is White)
    _, binary_mask = cv2.threshold(rotated_img, 150, 255, cv2.THRESH_BINARY)

    # Scale up for web viewing
    h, w = binary_mask.shape
    scaled_binary = cv2.resize(binary_mask, (w * 4, h * 4), interpolation=cv2.INTER_NEAREST)

    # Encode NumPy array directly into JPEG bytes in memory
    success, encoded_image = cv2.imencode('.jpg', scaled_binary)
    if success:
        return encoded_image.tobytes()
    return None


def esp32_tcp_client_thread():
    """Continuously fetches TCP ASCII frames from ESP32 AP and converts them to JPEG."""
    global latest_jpeg_frame

    while True:
        try:
            print(f"Connecting to ESP32 Wi-Fi AP at {ESP32_IP}:{ESP32_PORT}...")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            client_socket.connect((ESP32_IP, ESP32_PORT))
            print("Connected to ESP32 Stream!\n")

            buffer = ""
            frame_buffer = []
            capturing = False

            while True:
                data = client_socket.recv(1024).decode('utf-8', errors='ignore')
                if not data:
                    break

                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.rstrip('\r')

                    if "--- START FRAME ---" in line:
                        frame_buffer = []
                        capturing = True
                        continue

                    elif "--- END FRAME ---" in line and capturing:
                        capturing = False
                        if frame_buffer:
                            jpeg_data = process_frame(frame_buffer)
                            if jpeg_data is not None:
                                latest_jpeg_frame = jpeg_data
                        continue

                    if capturing:
                        frame_buffer.append(line)

        except (socket.timeout, socket.error) as e:
            print(f"Wi-Fi Connection Error: {e}. Retrying in 2 seconds...")
            time.sleep(2)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle web requests in separate threads to maintain continuous video streaming."""
    daemon_threads = True


class CamStreamHandler(BaseHTTPRequestHandler):
    """Simple HTTP Handler serving index.html and the MJPEG video feed."""

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            try:
                with open('index.html', 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b"<h1>Error: index.html not found! Place it in the same directory.</h1>")

        elif self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()

            while True:
                if latest_jpeg_frame is not None:
                    try:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(latest_jpeg_frame)))
                        self.end_headers()
                        self.wfile.write(latest_jpeg_frame)
                        self.wfile.write(b'\r\n')
                        time.sleep(0.05)  # Stream refresh rate (~20 FPS)
                    except (ConnectionResetError, BrokenPipeError):
                        break
                else:
                    time.sleep(0.1)


if __name__ == '__main__':
    import threading

    # Start ESP32 TCP client loop in background thread
    t = threading.Thread(target=esp32_tcp_client_thread, daemon=True)
    t.start()

    # Start Web Server on port 8080
    print(f"Starting Web Dashboard at http://localhost:{WEB_PORT}")
    server = ThreadedHTTPServer((WEB_HOST, WEB_PORT), CamStreamHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb Server Stopped.")