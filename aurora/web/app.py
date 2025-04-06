from flask import Flask, render_template, request, jsonify, make_response, Response
import os
import json
import uuid
from queue import Queue
from aurora.agent.agent import Agent
from aurora.agent.queued_tool_handler import QueuedToolHandler
from aurora.agent.tool_handler import ToolHandler

app = Flask(__name__)

# Initialize Aurora agent
api_key = os.getenv('OPENROUTER_API_KEY')
if not api_key:
    raise RuntimeError('OPENROUTER_API_KEY environment variable not set')

agent = Agent(api_key=api_key)

# Register all known tools with the agent's tool handler
for tool_entry in ToolHandler._tool_registry.values():
    agent.tool_handler.register(tool_entry['function'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/execute', methods=['POST'])
def execute():
    # Your existing logic
    pass

@app.route('/execute_stream', methods=['POST'])
def execute_stream():
    data = request.get_json()

    # Support both {"command": "..."} and {"messages": [...]}
    if 'messages' in data:
        messages = data['messages']
    elif 'command' in data:
        messages = [{"role": "user", "content": data['command']}]
    else:
        messages = []

    q = Queue()
    # Replace the tool handler with queued version
    agent.tool_handler = QueuedToolHandler(q, verbose=True)

    # Register all known tools again for the queued handler
    for tool_entry in ToolHandler._tool_registry.values():
        agent.tool_handler.register(tool_entry['function'])

    def enqueue_content(content):
        q.put(('content', content))

    def on_content_q(content):
        enqueue_content(content)

    import threading
    t = threading.Thread(target=agent.chat, args=(messages,), kwargs={'on_content': on_content_q})
    t.start()

    def generate():
        while t.is_alive() or not q.empty():
            try:
                event_type, payload = q.get(timeout=0.1)
                if event_type == 'content':
                    yield f"data: {json.dumps({'type': 'content', 'content': payload})}\n\n"
                elif event_type == 'tool_progress':
                    print(f"[WebServer] Tool progress event: {payload}")  # Debug print
                    yield f"data: {json.dumps({'type': 'tool_progress', 'progress': payload})}\n\n"
            except Exception:
                continue

    return Response(generate(), mimetype='text/event-stream')

@app.route('/favicon.ico')
def favicon():
    return '', 204
