import socket
import concurrent.futures

def check_ssh(ip):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.7)
        res = sock.connect_ex((ip, 22))
        sock.close()
        if res == 0:
            return ip
    except Exception:
        pass
    return None

def check_ping_or_web(ip):
    # Check port 80 or 8080 or 22
    for port in [22, 80, 8080, 5000]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            res = sock.connect_ex((ip, port))
            sock.close()
            if res == 0:
                return (ip, port)
        except Exception:
            pass
    return None

if __name__ == '__main__':
    print("Scanning subnet 192.168.8.1 - 192.168.8.254...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as ex:
        ips = [f"192.168.8.{i}" for i in range(1, 255)]
        ssh_results = [r for r in ex.map(check_ssh, ips) if r]
        
    print(f"Devices with SSH (Port 22) Open: {ssh_results}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as ex:
        web_results = [r for r in ex.map(check_ping_or_web, ips) if r]
    print(f"All responding devices (ports 22, 80, 8080, 5000): {web_results}")
