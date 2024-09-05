import socket
import ssl
import requests
import subprocess
import os
import signal
import sys
import logging
import certifi
import platform
import ipaddress
from binascii import hexlify

# Configuration
LISTEN_PORT = 53
DOH_SERVER = 'https://odoh.cloudflare-dns.com/dns-query'
CERTIFICATE_PATH = '/home/user/cloudflare.crt'
KEY_PATH = '/home/user/cloudflare.pem'
LOCAL_URL = 'http://127.0.0.1'  # Replace with your local URL/IP
PID_FILE = '/var/run/dns_server.pid'
LOG_FILE = '/var/log/dns-to-doh.log'
MAX_LOG_FILE_SIZE = 1 * 1024 * 1024 * 1024  # 1GB in bytes

# List of bogon IP ranges (excluding RFC 1918 private ranges)
BOGON_IP_RANGES = [
    '0.0.0.0/8',
    '127.0.0.0/8',
    '169.254.0.0/16',
    '192.0.2.0/24',
    '198.51.100.0/24',
    '203.0.113.0/24',
    '255.255.255.255/32',
]

# Dictionary to store user-defined static IP mappings
static_ip_mappings = {}


def add_static_ip_mapping(hostname, ip):
    """ Add a static IP mapping to the dictionary """
    static_ip_mappings[hostname] = ip
    logging.info(f"Added static IP mapping: {hostname} -> {ip}")


def remove_static_ip_mapping(hostname):
    """ Remove a static IP mapping from the dictionary """
    if hostname in static_ip_mappings:
        del static_ip_mappings[hostname]
        logging.info(f"Removed static IP mapping: {hostname}")


def create_directories_and_files():
    # Create log directory and log file if not exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create PID directory if not exists
    pid_dir = os.path.dirname(PID_FILE)
    if not os.path.exists(pid_dir):
        os.makedirs(pid_dir)

    # Check and create certificate and key files if needed
    if not os.path.exists(CERTIFICATE_PATH):
        raise FileNotFoundError(f"Certificate file not found: {CERTIFICATE_PATH}")

    if not os.path.exists(KEY_PATH):
        raise FileNotFoundError(f"Private key file not found: {KEY_PATH}")


def setup_logging():
    # Set up logging to file and console
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)

    # Check and truncate log file if it exceeds the max size
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_FILE_SIZE:
        logging.info("Log file size exceeds 1GB, truncating...")
        with open(LOG_FILE, 'w') as f:
            f.truncate(0)


def check_and_kill_process_on_port(port):
    try:
        # Find processes listening on the port
        result = subprocess.check_output(['lsof', '-i', f':{port}'])
        for line in result.decode().splitlines()[1:]:
            parts = line.split()
            pid = int(parts[1])  # Convert PID to integer

            try:
                # Check if the process exists
                os.kill(pid, 0)
                # Kill the process
                os.kill(pid, signal.SIGKILL)
                logging.info(f"Killed process {pid} listening on port {port}")
            except ProcessLookupError:
                logging.info(f"Process {pid} no longer exists")
            except PermissionError:
                logging.error(f"Permission denied when trying to kill process {pid}")

    except subprocess.CalledProcessError:
        # No process is listening on the port
        logging.info(f"No process found listening on port {port}")


def is_bogon_ip(ip):
    """ Check if IP address is within bogon ranges """
    ip_obj = ipaddress.ip_address(ip)
    for net in BOGON_IP_RANGES:
        if ip_obj in ipaddress.ip_network(net):
            return True
    return False


def extract_transaction_id(query):
    """ Extract the transaction ID from the DNS query """
    return query[:2]


def construct_dns_response(original_query, response_data):
    """ Construct the DNS response with the correct transaction ID """
    transaction_id = extract_transaction_id(original_query)
    return transaction_id + response_data[2:]


def handle_dns_query(data, addr, sock):
    """ Handle incoming DNS queries and forward them or respond locally """
    client_ip = addr[0]
    logging.info(f"Received DNS query from {client_ip}")

    # Check for bogon IPs
    if is_bogon_ip(client_ip):
        logging.info(f"Blocked bogon request from {client_ip}")
        # Respond with an appropriate DNS error or local response
        # Example DNS response
        local_response = b'\x00\x00\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00'
        sock.sendto(local_response, addr)
        return

    # Parse DNS query to extract hostname
    query_hostname = parse_dns_query_for_hostname(data)
    if query_hostname in static_ip_mappings:
        # Respond with the static IP from user-defined mappings
        static_ip = static_ip_mappings[query_hostname]
        logging.info(f"Responding with static IP for {query_hostname}: {static_ip}")
        # Construct a DNS response with the static IP (this is a simplified example)
        response_data = construct_dns_response(
            data, create_static_ip_dns_response(static_ip))
        sock.sendto(response_data, addr)
        return

    # Forward the DNS query over HTTPS
    response = requests.post(
        DOH_SERVER,
        headers={'Content-Type': 'application/dns-message'},
        data=data,
        verify=certifi.where()  # Use certifi's CA bundle
    )

    # Log the destination URL and response status
    logging.info(f"Forwarded query to DoH server: {DOH_SERVER}")
    logging.info(f"DoH server response status: {response.status_code}")

    if response.status_code == 200:
        # Ensure the response retains the same transaction ID
        response_data = response.content
        response_data_with_id = construct_dns_response(data, response_data)

        # Send the response back to the original client
        sock.sendto(response_data_with_id, addr)
        logging.info(f"Forwarded response to {addr}")
    else:
        logging.error(f"Error forwarding query: {response.status_code}")


def parse_dns_query_for_hostname(query):
    """ Parse DNS query to extract hostname (simplified example) """
    # DNS query parsing is complex and depends on the query format
    # This is a placeholder function
    return "example.com"


def create_static_ip_dns_response(ip):
    """ Create a DNS response with the static IP address """
    # This is a simplified example. A real implementation would need to construct a full DNS response
    # based on the format and requirements of DNS protocol.
    return b''  # Placeholder for a valid DNS response


def start_dns_server():
    # Set up a UDP socket to listen on port 53
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', LISTEN_PORT))
    logging.info(f"Listening on port {LISTEN_PORT}")

    # Create a context for TLS/SSL
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=CERTIFICATE_PATH, keyfile=KEY_PATH)

    while True:
        try:
            # Receive DNS query
            # DNS queries are typically <= 512 bytes
            data, addr = sock.recvfrom(512)
            handle_dns_query(data, addr, sock)

        except Exception as e:
            logging.error(f"Error: {e}")


def detect_os():
    """ Detect the operating system and adjust implementation accordingly """
    current_os = platform.system().lower()
    logging.info(f"Detected OS: {current_os}")

    if current_os in ['windows', 'cygwin', 'msys']:
        logging.info("Running on Windows")
        # Adjust implementation for Windows if necessary
    elif current_os == 'linux':
        logging.info("Running on Linux")
        # Adjust implementation for Linux if necessary
    elif current_os == 'darwin':
        logging.info("Running on MacOS")
        # Adjust implementation for MacOS if necessary
    else:
        logging.warning("Unknown OS detected")


def daemonize_process(target_function):
    """ Run the target function as a background process """
    pid = os.fork()
    if pid > 0:
        sys.exit()  # Exit the parent process
    elif pid == 0:
        os.setsid()  # Create a new session
        os.umask(0)  # Set file creation mask
        pid = os.fork()
        if pid > 0:
            sys.exit()  # Exit the second parent process
        elif pid == 0:
            # Redirect standard file descriptors
            sys.stdout.flush()
            sys.stderr.flush()
            with open('/dev/null', 'r') as dev_null:
                os.dup2(dev_null.fileno(), sys.stdin.fileno())
                os.dup2(dev_null.fileno(), sys.stdout.fileno())
                os.dup2(dev_null.fileno(), sys.stderr.fileno())
            # Write PID to file
            with open(PID_FILE, 'w') as pid_file:
                pid_file.write(str(os.getpid()))
            # Run the target function
            target_function()
        else:
            sys.exit(1)
    else:
        sys.exit(1)


def main():
    # Create necessary directories and files
    create_directories_and_files()

    # Set up logging
    setup_logging()

    # Check and kill existing processes on port 53
    check_and_kill_process_on_port(LISTEN_PORT)

    # Detect operating system
    detect_os()

    # Start the DNS server in daemon mode
    daemonize_process(start_dns_server)


if __name__ == "__main__":
    main()
