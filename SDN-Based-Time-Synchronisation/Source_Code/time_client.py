
import socket
import json
import time
import csv
import statistics
import argparse

SERVER_IP = "10.0.0.1"
SERVER_PORT = 5005

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=20)
parser.add_argument("--clock-offset-ms", type=float, default=0.0)
parser.add_argument("--output", default="client_results.csv")

args = parser.parse_args()

if args.count < 1:
    parser.error("--count must be at least 1")

simulated_offset = args.clock_offset_ms / 1000.0

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client.settimeout(3)

results = []
failures = 0

print("\nStarting time synchronization...\n")

for i in range(args.count):

    t1 = time.time() + simulated_offset

    request = {"t1": t1}

    try:
        client.sendto(
            json.dumps(request).encode(),
            (SERVER_IP, SERVER_PORT)
        )

        data, address = client.recvfrom(1024)
        t4 = time.time() + simulated_offset

        response = json.loads(data.decode())

        if response.get("t1") != t1:
            raise ValueError("Unexpected response")

        t2 = response["t2"]
        t3 = response["t3"]

        offset = ((t2 - t1) + (t3 - t4)) / 2
        rtt = (t4 - t1) - (t3 - t2)

        corrected_time = t4 + offset

        sync_error = abs(
            corrected_time - time.time()
        ) * 1000

        result = {
            "request": i + 1,
            "offset_ms": offset * 1000,
            "rtt_ms": rtt * 1000,
            "sync_error_ms": sync_error
        }

        results.append(result)

        print(
            f"Request {i+1}: "
            f"Offset={offset*1000:.3f} ms | "
            f"RTT={rtt*1000:.3f} ms | "
            f"Error={sync_error:.3f} ms"
        )

    except socket.timeout:
        failures += 1
        print(f"Request {i+1}: TIMEOUT")

    except (ValueError, KeyError, TypeError, OSError) as error:
        failures += 1
        print(f"Request {i+1}: ERROR - {error}")

client.close()

print("\n--- TIME SYNCHRONIZATION SUMMARY ---")

print(f"Total requests: {args.count}")
print(f"Successful requests: {len(results)}")
print(f"Failed requests: {failures}")

if results:

    rtts = [r["rtt_ms"] for r in results]
    offsets = [r["offset_ms"] for r in results]
    errors = [r["sync_error_ms"] for r in results]

    print(f"Average RTT: {statistics.mean(rtts):.3f} ms")
    print(f"Minimum RTT: {min(rtts):.3f} ms")
    print(f"Maximum RTT: {max(rtts):.3f} ms")

    print(
        f"Average clock offset: "
        f"{statistics.mean(offsets):.3f} ms"
    )

    print(
        f"Average synchronization error: "
        f"{statistics.mean(errors):.3f} ms"
    )

    with open(args.output, "w", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "request",
                "offset_ms",
                "rtt_ms",
                "sync_error_ms"
            ]
        )

        writer.writeheader()
        writer.writerows(results)

    print(f"Results saved to {args.output}")

else:
    print("No successful synchronization requests.")
