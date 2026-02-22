#!/usr/bin/env python3
import os
import re
import ipaddress

# Paths to ignore
IGNORE_DIRS = {'.git', 'venv', '__pycache__', '.env'}
# Common domains to NOT replace to avoid breaking scripts
IGNORE_DOMAINS = {'github.com', 'ubuntu.com', 'google.com', 'certbot.eff.org', 'netbox-community'}

ip_map = {}
next_dummy_ip = 1

def get_dummy_ip(original_ip):
    global next_dummy_ip
    if original_ip not in ip_map:
        ip_map[original_ip] = f"198.51.100.{next_dummy_ip}"
        next_dummy_ip += 1
        if next_dummy_ip > 254:
            next_dummy_ip = 1
    return ip_map[original_ip]

def sanitize_content(content):
    # Sanitize IPv4
    def ip_repl(match):
        ip_str = match.group(0)
        try:
            ip = ipaddress.IPv4Address(ip_str)
            if ip.is_loopback or ip_str == '0.0.0.0' or ip_str == '255.255.255.255':
                return ip_str
            return get_dummy_ip(ip_str)
        except ipaddress.AddressValueError:
            return ip_str

    content = re.sub(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', ip_repl, content)

    # Sanitize Domains
    def domain_repl(match):
        domain_str = match.group(0)
        for ignored in IGNORE_DOMAINS:
            if domain_str.endswith(ignored):
                return domain_str
        return 'example.com'

    content = re.sub(r'\b[a-zA-Z0-9.-]+\.(?:com|net|org|tw|local)\b', domain_repl, content)
    return content

def main():
    repo_root = '.' 
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            filepath = os.path.join(root, file)
            # Exclude self
            if file == 'sanitize_data.py':
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = sanitize_content(content)
                
                if content != new_content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Sanitized: {filepath}")
            except UnicodeDecodeError:
                pass

if __name__ == '__main__':
    main()
