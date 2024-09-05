# DNS-to-DoH Server [STANDALONE PYTHON SCRIPT]

Welcome to the DNS-to-DoH server script! This tool listens for DNS queries on port 53, forwards them to a DoH (DNS over HTTPS) server, and sends back the responses. It’s designed to be efficient and robust, making it ideal for use as an upstream server. Let’s dive into how it works and how you can optimize it.

## Installation

### 1. Clone the Repository

First, clone the repository and navigate into the directory:

```sh
git clone https://github.com/your-repo/dns-to-doh.git
cd dns-to-doh
```

### 2. Install Required Packages

Ensure you have Python 3 and `pip` installed. Then, install the necessary packages. The primary packages required are `requests` for making HTTP requests and `certifi` for handling SSL certificates. You might also need `lxml` for more advanced DNS query parsing if your use case requires it:

```sh
pip install requests certifi
```

If you need more advanced DNS query handling, consider installing `dnspython`:

```sh
pip install dnspython
```

### 3. Obtain Certificates

You'll need SSL certificates for secure communication. Place them where the script expects them, or adjust the `CERTIFICATE_PATH` and `KEY_PATH` in the script to point to your files.

## How to Use

### Configuration

Update the script with your settings:

- **`CERTIFICATE_PATH`**: Path to your SSL certificate.
- **`KEY_PATH`**: Path to your SSL key.
- **`LOCAL_URL`**: Your local URL or IP.
- **`PID_FILE`**: Path to save the PID file.
- **`LOG_FILE`**: Path for the log file.
- **`DOH_SERVER`**: URL of the DoH server you want to use.

### Running the Script

To run the script as a background service, use:

```sh
python dns_to_doh.py
```

## Code Efficiency and Use Cases

### Streamlining DoH Requests

The script efficiently processes DNS queries and handles DoH requests. Here's how it achieves this:

#### Constructing DNS Responses

The `construct_dns_response` function maintains the correct transaction ID in DNS responses. This ensures that responses are correctly matched with their respective queries, which is crucial for reliable DNS communication.

```python
def construct_dns_response(original_query, response_data):
    """ Construct the DNS response with the correct transaction ID """
    transaction_id = extract_transaction_id(original_query)
    return transaction_id + response_data[2:]
```

By extracting the transaction ID from the original DNS query and appending it to the response data, this function maintains the integrity of the DNS communication.

#### Handling DNS Queries

The `handle_dns_query` function is designed to handle incoming DNS queries efficiently. It processes queries based on IP and hostname, using either local static mappings or forwarding the queries to the DoH server.

```python
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
```

This function checks for bogon IPs and uses static IP mappings when available. For other queries, it forwards them to the DoH server and handles the response efficiently.

### Ideal Use Cases

- **Upstream DNS Server**: This script is perfect for use as an upstream DNS server. It efficiently handles high loads and minimizes latency by forwarding queries to a DoH server and using local static IP mappings.
- **Clustering**: Deploy multiple instances of this server to handle increased traffic and provide redundancy. You can use a load balancer to distribute traffic among instances, ensuring high availability and reliability.

### Optimization Tips

- **Additional Packages**: For even better performance, consider using `asyncio` for asynchronous processing or `gunicorn` for process management.
- **Code Improvements**: Advanced DNS response handling could involve constructing full DNS responses based on specific query formats and requirements.

## Contributing

Want to contribute? Feel free to fork the repo and submit a pull request. For bugs or feature requests, open an issue on GitHub.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

That’s the rundown! Customize the settings as needed, and if you have any questions or need help, just reach out. Happy DNS-ing!
