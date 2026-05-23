from flask import Flask, render_template, jsonify
import psutil, threading, time, csv
from datetime import datetime
from collections import deque

app = Flask(__name__)

history = deque(maxlen=300)
os_stats = {}
lock = threading.Lock()
LOG_FILE = "logs.csv"

# Create CSV File Header if needed
def init_csv():
    try:
        with open(LOG_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Time","CPU%","RAM%","Disk%",
                "Upload(KB/s)","Download(KB/s)",
                "DiskRead(KB/s)","DiskWrite(KB/s)",
                "Swap%","RAM_Used_GB","RAM_Free_GB","RAM_Total_GB",
                "Disk_Used_GB","Disk_Free_GB","Disk_Total_GB"
            ])
    except FileExistsError:
        pass

# Background System Monitor
def sample_system():
    prev_net = psutil.net_io_counters()
    prev_disk = psutil.disk_io_counters()
    prev_ctx = psutil.cpu_stats().ctx_switches

    while True:
        time.sleep(1)

        # REAL CPU % (Max 100)
        cpu = psutil.cpu_percent(interval=None)

        # REAL RAM VALUES
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = mem.used / (1024**3)
        ram_free_gb = mem.available / (1024**3)
        ram_total_gb = mem.total / (1024**3)

        # REAL DISK VALUES
        disk = psutil.disk_usage('/')
        disk_total = disk.total
        disk_free = disk.free
        disk_used = disk_total - disk_free
        disk_percent = (disk_used / disk_total) * 100

        # REAL NETWORK SPEED
        net = psutil.net_io_counters()
        up_kb = (net.bytes_sent - prev_net.bytes_sent) / 1024
        down_kb = (net.bytes_recv - prev_net.bytes_recv) / 1024
        prev_net = net

        # REAL DISK I/O SPEED
        disk_io = psutil.disk_io_counters()
        read_kb = (disk_io.read_bytes - prev_disk.read_bytes) / 1024
        write_kb = (disk_io.write_bytes - prev_disk.write_bytes) / 1024
        prev_disk = disk_io

        # REAL CONTEXT SWITCHES
        cpu_stat = psutil.cpu_stats()
        ctx_per_sec = cpu_stat.ctx_switches - prev_ctx
        prev_ctx = cpu_stat.ctx_switches

        swap = psutil.swap_memory()

        ts = datetime.now().strftime("%H:%M:%S")

        point = {
            "time": ts,
            "cpu": round(cpu, 1),
            "ram": round(ram_percent, 1),
            "disk": round(disk_percent, 1),
            "ram_used_gb": round(ram_used_gb, 1),
            "ram_free_gb": round(ram_free_gb, 1),
            "ram_total_gb": round(ram_total_gb, 1),
            "disk_used_gb": round(disk_used / (1024**3), 1),
            "disk_free_gb": round(disk_free / (1024**3), 1),
            "disk_total_gb": round(disk_total / (1024**3), 1),
            "up": round(up_kb, 2),
            "down": round(down_kb, 2)
        }

        with lock:
            history.append(point)
            global os_stats
            os_stats = {
                "ctx_per_sec": ctx_per_sec,
                "swap_percent": swap.percent,
                "swap_used_mb": round(swap.used / (1024**2), 1),
                "disk_read_kb": round(read_kb, 1),
                "disk_write_kb": round(write_kb, 1)
            }

        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now(), cpu, ram_percent, disk_percent,
                up_kb, down_kb, read_kb, write_kb,
                swap.percent, ram_used_gb, ram_free_gb, ram_total_gb,
                disk_used/(1024**3), disk_free/(1024**3), disk_total/(1024**3)
            ])

# Accurate Process Monitor (Works for Mac/Win/Linux)
def get_top_processes(limit=10):
    procs = []
    for p in psutil.process_iter(['pid']):
        try:
            p.cpu_percent(interval=None)
        except:
            continue

    time.sleep(0.15)

    for p in psutil.process_iter(
        ['pid', 'name', 'cpu_percent', 'memory_percent', 'nice', 'status']
    ):
        try:
            info = p.info
            procs.append({
                "pid": info['pid'],
                "name": (info['name'] or "unknown")[:18],
                "cpu": info['cpu_percent'],
                "mem": round(info['memory_percent'], 1),
                "prio": info['nice'],
                "status": info['status']
            })
        except:
            continue

    procs = [p for p in procs if p["cpu"] > 0]
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return procs[:limit]

# Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    with lock:
        return jsonify(list(history))

@app.route("/api/os")
def api_os():
    with lock:
        return jsonify(os_stats)

@app.route("/api/processes")
def api_processes():
    return jsonify(get_top_processes())

# Start Server
if __name__ == "__main__":
    init_csv()
    threading.Thread(target=sample_system, daemon=True).start()
    app.run(host="0.0.0.0", port=5021, debug=False)
