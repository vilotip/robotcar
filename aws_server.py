from flask import Flask, Response, request
import time

app = Flask(__name__)
latest_distance = 0.0

@app.route('/upload_distance', methods=['POST'])
def upload_distance():
    global latest_distance
    try:
        data = request.data.decode('utf-8')
        latest_distance = float(data)
        print(f"Received Distance: {latest_distance} cm")
        return "OK", 200
    except ValueError:
        return "Invalid Data", 400

@app.route('/stream')
def stream():
    def event_stream():
        print("Browser connected to SSE stream!")
        while True:
            yield f"data: {latest_distance}\n\n"
            time.sleep(0.2)
    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/')
@app.route('/index.html')
def index():
    try:
        with open('/var/www/html/index.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Cloud Ultrasonic Dashboard Active</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)
