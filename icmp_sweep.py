import subprocess
import concurrent.futures

def ping_ip(ip):
    res = subprocess.run(f"ping -n 1 -w 150 {ip}", capture_output=True, text=True, shell=True)
    if "TTL=" in res.stdout:
        return ip
    return None

if __name__ == '__main__':
    print("Sending ICMP pings to all 254 addresses...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        ips = [f"192.168.8.{i}" for i in range(1, 255)]
        active = [r for r in ex.map(ping_ip, ips) if r]
    print("ACTIVE_IPS:", active)
