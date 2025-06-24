import requests

def run_local_agent_zero_task():
    response = requests.post(
        "http://localhost:50001/message",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic YWRtaW46YWRtaW4xMjM="
        },
        json={
            "task": "Evaluate the Flask app and test_agent_zero.py in this repo. Return test success, LLM integration status, and a deployment confidence score.",
            "output_format": "text"
        }
    )
    print("Agent-Zero Local Response:\n", response.text)

if __name__ == "__main__":
    run_local_agent_zero_task()
