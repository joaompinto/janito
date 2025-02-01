import os
import logging
import platform
import subprocess
import threading
from typing import Dict, Optional
from flask_socketio import SocketIO

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcessManager:
    def __init__(self, socketio: SocketIO):
        self.processes: Dict[str, dict] = {}
        self.socketio = socketio
        
        shell_env = os.environ.get('SHELL', 'Not set')
        if platform.system() == 'Windows':
            possible_shells = [
                os.environ.get('SHELL'),
                os.environ.get('BASH'),
                os.environ.get('BASH_EXE'),
                '/usr/bin/bash',
                r'C:\Program Files\Git\bin\bash.exe',
                r'C:\Program Files\Git\usr\bin\bash.exe',
                r'C:\Program Files (x86)\Git\bin\bash.exe',
            ]
            shell_env = next((
                shell for shell in possible_shells 
                if shell and (os.path.exists(shell) if '/' in shell or '\\' in shell else True)
            ), 'Not set')
        
        self.use_shell = bool(shell_env != 'Not set' and ('bash' in shell_env.lower() or 'git' in shell_env.lower()))
        
        logger.info(f"Platform: {platform.system()}")
        logger.info(f"Shell configuration:")
        logger.info(f"  - SHELL env: {shell_env}")
        logger.info(f"  - Using shell: {self.use_shell}")

    def _is_complete_output(self, buffer):
        if not buffer:
            return False
        last_line = buffer[-1]
        return (
            last_line.rstrip().endswith(('>', '$', '#')) or
            len(buffer) > 50
        )

    def start_process(self, command: str, args: list) -> str:
        try:
            logger.info(f"Starting process with shell={self.use_shell}")
            popen_kwargs = {
                'stdin': subprocess.PIPE,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'text': True,
                'bufsize': 1,
                'encoding': 'utf-8',
                'errors': 'replace'
            }

            if self.use_shell:
                quoted_args = [f'"{arg}"' for arg in args]
                shell_command = f'{command} {" ".join(quoted_args)}'
                cmd_array = ['bash', '-c', shell_command]
                proc = subprocess.Popen(cmd_array, **popen_kwargs)
            else:
                cmd_array = [command, *args]
                proc = subprocess.Popen(cmd_array, **popen_kwargs)
            
            process_id = str(proc.pid)
            full_command = f"{command} {' '.join(args)}"
            self.processes[process_id] = {
                "process": proc, 
                "status": "running",
                "command": full_command,
                "stdout_buffer": [],
                "stderr_buffer": []
            }

            self._start_process_monitoring(process_id, proc)
            return process_id

        except Exception as e:
            logger.error(f"Error starting process: {str(e)}")
            if 'process_id' in locals() and process_id in self.processes:
                del self.processes[process_id]
            raise

    def _start_process_monitoring(self, process_id: str, proc: subprocess.Popen):
        def monitor_process():
            proc.wait()
            returncode = proc.returncode
            status_msg = "completed" if returncode == 0 else "failed"
            
            if process_id in self.processes:
                self._send_remaining_output(process_id)
                self.socketio.emit(f'process_output_{process_id}', {
                    "type": "status",
                    "data": f"Process {status_msg} with code {returncode}"
                })
                del self.processes[process_id]

        def read_output(stream, stream_type):
            partial_line = ''
            try:
                while True:
                    chunk = stream.read(1024)
                    if not chunk:
                        break
                    
                    text = partial_line + chunk
                    lines = text.split('\n')
                    partial_line = lines[-1]
                    complete_lines = lines[:-1]
                    
                    for line in complete_lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        if process_id in self.processes:
                            buffer_key = f'{stream_type}_buffer'
                            self.processes[process_id][buffer_key].append(line)
                            self.socketio.emit(f'process_output_{process_id}', {
                                "type": stream_type,
                                "data": line
                            })
            
            finally:
                if partial_line and partial_line.strip():
                    if process_id in self.processes:
                        buffer_key = f'{stream_type}_buffer'
                        self.processes[process_id][buffer_key].append(partial_line.strip())
                        self.socketio.emit(f'process_output_{process_id}', {
                            "type": stream_type,
                            "data": partial_line.strip()
                        })
                stream.close()

        threading.Thread(target=monitor_process, daemon=True).start()
        threading.Thread(target=read_output, args=(proc.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=read_output, args=(proc.stderr, "stderr"), daemon=True).start()

    def _send_remaining_output(self, process_id: str):
        if process_id not in self.processes:
            return

        for buffer_type in ['stdout', 'stderr']:
            buffer = self.processes[process_id][f'{buffer_type}_buffer']
            if buffer:
                final_output = '\n'.join(buffer)
                self.socketio.emit(f'process_output_{process_id}', {
                    "type": buffer_type,
                    "data": final_output
                })

    def send_input(self, process_id: str, input_data: str):
        if process_id not in self.processes:
            raise KeyError("Process not found")
        
        proc = self.processes[process_id]["process"]
        if proc.poll() is not None:
            raise RuntimeError("Process has ended")
            
        try:
            full_input = input_data + '\n'
            proc.stdin.write(full_input)
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"Failed to send input: {str(e)}")

    def get_process_info(self, process_id: str) -> Optional[dict]:
        if process_id not in self.processes:
            return None
        proc = self.processes[process_id]["process"]
        return {
            "status": "completed" if proc.poll() is not None else "running",
            "exit_code": proc.poll()
        }

    def terminate_process(self, process_id: str):
        if process_id in self.processes:
            proc = self.processes[process_id]["process"]
            proc.terminate()
            proc.wait()
            self.socketio.emit(f'process_output_{process_id}', {
                "type": "status",
                "data": f"Process terminated with code {proc.returncode}"
            })
            del self.processes[process_id]

    def list_processes(self) -> dict:
        return {
            pid: {
                "command": info["command"],
                "status": "running" if info["process"].poll() is None else "completed",
                "pid": pid
            }
            for pid, info in self.processes.items()
        }