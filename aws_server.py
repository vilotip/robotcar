from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import time

latest_distance = 0.0

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class EC2StreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Receives ultrasonic distance updates pushed from your local edge client."""
        global latest_distance
        if self.path == '/upload_distance':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            try:
                latest_distance = float(post_data)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid Data")

    def do_GET(self):
        """Serves the frontend dashboard and Server-Sent Events (SSE) telemetry stream."""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            try:
                with open('/var/www/html/index.html', 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b"<h1>Cloud Ultrasonic Dashboard Active</h1>")

        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            try:
                while True:
                    data_chunk = f"data: {latest_distance}\n\n".encode('utf-8')
                    self.wfile.write(data_chunk)
                    self.wfile.flush()
                    time.sleep(0.2)
            except (ConnectionResetError, BrokenPipeError):
                pass

if __name__ == '__main__':
    # Bind to port 8080 (Apache will proxy requests here)
    server = ThreadedHTTPServer(('0.0.0.0', 8080), EC2StreamHandler)
    print("AWS Ultrasonic Cloud Telemetry Receiver running on Port 8080...")
    server.serve_forever()