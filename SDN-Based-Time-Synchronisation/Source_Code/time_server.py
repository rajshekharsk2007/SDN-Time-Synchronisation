
import socket
import json
import time
from concurrent.futures import ThreadPoolExecutor

SERVER_IP = "10.0.0.1"
SERVER_PORT = 5005
BUFFER_SIZE = 1024

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((SERVER_IP, SERVER_PORT))

executor = ThreadPoolExecutor(max_workers=10)

print(f"Time server listening on {SERVER_IP}:{SERVER_PORT}", flush=True)
print("Concurrent client handling enabled", flush=True)

def process_request(data, client_address):
    try:
        request = json.loads(data.decode())

        t1 = request["t1"]

        if not isinstance(t1, (int, float)):
            raise ValueError("Invalid timestamp")

        t2 = time.time()
        t3 = time.time()

        response = {
            "t1": t1,
            "t2": t2,
            "t3": t3
        }

        server.sendto(
            json.dumps(response).encode(),
            client_address
        )

        print(
            f"Request from {client_address} | "
            f"T2={t2:.6f} | T3={t3:.6f}",
            flush=True
        )

    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        print(f"Invalid request from {client_address}", flush=True)

try:
    while True:
        data, client_address = server.recvfrom(BUFFER_SIZE)
        executor.submit(process_request, data, client_address)

except KeyboardInterrupt:
    print("Time server shutting down")

finally:
    server.close()
    executor.shutdown(wait=True)
