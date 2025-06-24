from flask import Flask
from prometheus_client import Counter, generate_latest

app = Flask(__name__)

REQUEST_COUNT = Counter("request_count", "Total web requests")

@app.route("/")
def index():
    REQUEST_COUNT.inc()
    return "👋 Hello from Agent-Zero Flask App!"

@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
