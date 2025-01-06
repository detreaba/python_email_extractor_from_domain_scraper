import re
import os
import threading
import requests
from bs4 import BeautifulSoup
import dns.resolver
import smtplib
from urllib.parse import urljoin, urlparse
from colorama import Fore, Style, init
from tqdm import tqdm
from queue import Queue
import time
from random import choice

# Initialize Colorama
init()

# ----------------------
# Global Configuration
# ----------------------

MAX_RETRIES = 3
DELAY_BETWEEN_REQUESTS = 2  # Seconds
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
]

# ----------------------
# Email Validation Functions
# ----------------------

def is_valid_email(email):
    """Check if the email syntax is valid."""
    regex = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return re.match(regex, email)


def has_valid_mx(domain):
    """Check if the domain has valid MX records."""
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        return len(mx_records) > 0
    except Exception:
        return False


# ----------------------
# Website Scraping Functions
# ----------------------

def get_links_from_page(url, html, base_domain):
    """Extract all internal links from the HTML content."""
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a_tag in soup.find_all("a", href=True):
        link = urljoin(url, a_tag['href'])
        if is_same_domain(link, base_domain):
            links.add(link)
    return links


def is_same_domain(target_url, base_domain):
    """Check if the target URL belongs to the base domain."""
    target_domain = urlparse(target_url).netloc
    return target_domain == base_domain


def fetch_page(url):
    """Fetch a page with retries and handle exceptions."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            headers = {"User-Agent": choice(USER_AGENTS)}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response
        except requests.exceptions.RequestException as e:
            retries += 1
            print(f"{Fore.YELLOW}[!] Error visiting {url}: {e} (Retry {retries}/{MAX_RETRIES}){Style.RESET_ALL}")
            time.sleep(DELAY_BETWEEN_REQUESTS)
    return None


def scrape_website(domain, page_limit=100, size_limit_mb=10):
    """Spider through the website to scrape emails."""
    print(f"{Fore.CYAN}[*] Spidering through the website: {domain}{Style.RESET_ALL}")
    base_url = f"http://{domain}"
    base_domain = urlparse(base_url).netloc
    visited = set()
    to_visit = {base_url}
    found_emails = set()
    total_size = 0

    progress_bar = tqdm(total=page_limit, desc=f"Scraping {domain}", colour="cyan", leave=False)

    while to_visit and len(visited) < page_limit and total_size < size_limit_mb * 1024 * 1024:
        current_url = to_visit.pop()
        if current_url in visited:
            continue
        visited.add(current_url)
        progress_bar.update(1)

        response = fetch_page(current_url)
        if response is None:
            continue

        total_size += len(response.content)
        if response.status_code == 200:
            # Extract emails from the page
            emails = set(re.findall(rf'[A-Za-z0-9._%+-]+@{re.escape(domain)}', response.text))
            found_emails.update(emails)
            # Extract links to visit next
            new_links = get_links_from_page(current_url, response.text, base_domain)
            to_visit.update(new_links - visited)

    progress_bar.close()
    return found_emails


# ----------------------
# Save Emails to File
# ----------------------

def save_emails_to_file(domain, emails):
    """Save emails to a text file."""
    filename = f"{domain.replace('.', '_')}.txt"
    with open(filename, "w") as file:
        for email in emails:
            file.write(email + "\n")
    print(f"{Fore.GREEN}[*] Emails saved to {filename}{Style.RESET_ALL}")


# ----------------------
# Worker Function for Multithreading
# ----------------------

def worker(domain_queue):
    while not domain_queue.empty():
        domain = domain_queue.get()
        try:
            emails = scrape_website(domain)
            save_emails_to_file(domain, emails)
        finally:
            domain_queue.task_done()


# ----------------------
# Main Script
# ----------------------

def main():
    input_file = input("Enter the file name containing emails: ").strip()
    if not os.path.exists(input_file):
        print(f"{Fore.RED}[!] File not found: {input_file}{Style.RESET_ALL}")
        return

    # Extract domains from the file
    with open(input_file, "r") as file:
        domains = set(line.strip() for line in file if line.strip())

    print(f"{Fore.CYAN}[*] Starting to scrape {len(domains)} domains with a maximum of 10 threads...{Style.RESET_ALL}")

    # Set up the domain queue
    domain_queue = Queue()
    for domain in domains:
        domain_queue.put(domain)

    # Set up multithreading (10 threads)
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=worker, args=(domain_queue,))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print(f"{Fore.GREEN}[*] Scraping completed for all domains.{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
