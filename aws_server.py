from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import time

latest_frame = None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class EC2StreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Receives binary JPEG frame updates pushed from your local edge client."""
        global latest_frame
        if self.path == '/upload_frame':
            content_length = int(self.headers['Content-Length'])
            latest_frame = self.rfile.read(content_length)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_GET(self):
        """Serves the frontend dashboard and public MJPEG video stream."""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            try:
                with open('/var/www/html/index.html', 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b"<h1>Cloud Dashboard Active</h1>")

        elif self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            while True:
                if latest_frame is not None:
                    try:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(latest_frame)))
                        self.end_headers()
                        self.wfile.write(latest_frame)
                        self.wfile.write(b'\r\n')
                        time.sleep(0.05)
                    except (ConnectionResetError, BrokenPipeError):
                        break
                else:
                    time.sleep(0.1)

if __name__ == '__main__':
    # Bind to port 8080 (Apache will proxy requests here)
    server = ThreadedHTTPServer(('0.0.0.0', 8080), EC2StreamHandler)
    print("AWS Cloud Telemetry Receiver running on Port 8080...")
    server.serve_forever()