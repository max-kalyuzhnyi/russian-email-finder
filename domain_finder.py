import requests
from bs4 import BeautifulSoup
import re
import logging
import time
import random
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger("domain_finder")

def extract_domain_from_url(url: str) -> str:
    """Extract the domain from a URL."""
    try:
        # Handle cases where the URL is not properly formatted
        if url.startswith('//'):
            url = 'http:' + url
        elif not url.startswith(('http://', 'https://')):
            # Check if it's a redirect URL from search engines
            if 'google.com/url' in url:
                # Extract the actual URL from Google redirect
                match = re.search(r'url=([^&]+)', url)
                if match:
                    url = match.group(1)
                    url = requests.utils.unquote(url)
            elif 'yandex.ru' in url and '/goto/' in url:
                # Extract the actual URL from Yandex redirect
                match = re.search(r'goto/([^&?]+)', url)
                if match:
                    url = match.group(1)
                    url = requests.utils.unquote(url)
            else:
                # Try to extract domain-like pattern directly from text
                domain_pattern = r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z0-9][-a-zA-Z0-9]+'
                match = re.search(domain_pattern, url)
                if match:
                    return match.group(0)
                
                # If no domain pattern found, try to make it a proper URL
                url = 'http://' + url
        
        # Parse the URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Remove www. if present
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Handle cases where the domain might be in the path (common in redirects)
        if not domain and parsed_url.path:
            # Try to extract domain from path
            path_parts = parsed_url.path.split('/')
            for part in path_parts:
                if '.' in part and not part.startswith('.'):
                    domain = part
                    break
        
        return domain
    except Exception as e:
        logger.error(f"Error extracting domain from URL {url}: {str(e)}")
        return ""

def is_valid_domain(domain: str) -> bool:
    """Check if a domain is valid."""
    # Basic validation
    if not domain or len(domain) < 4:  # At least a.bc
        return False
        
    # Must have at least one dot
    if '.' not in domain:
        return False
        
    # Check for valid TLD (at least 2 characters after last dot)
    parts = domain.split('.')
    if len(parts[-1]) < 2:
        return False
        
    # Check for common invalid domains and search engines
    invalid_domains = [
        # Search engines and their domains
        'google.com', 'yandex.ru', 'yandex.com', 'bing.com', 'yahoo.com', 'baidu.com',
        'duckduckgo.com', 'mail.ru', 'rambler.ru', 'ya.ru',
        # Common generic domains
        'example.com', 'domain.com', 'website.com', 'site.com',
        # Social media
        'facebook.com', 'twitter.com', 'instagram.com', 'vk.com', 'youtube.com',
        'linkedin.com', 'pinterest.com', 'reddit.com', 'telegram.org',
        # Common file hosting
        'dropbox.com', 'drive.google.com', 'docs.google.com', 'cloud.mail.ru',
        # Common email providers
        'gmail.com', 'outlook.com', 'hotmail.com', 'mail.ru', 'yandex.ru',
        # Common Russian sites that aren't company domains
        'rbc.ru', 'lenta.ru', 'ria.ru', 'gazeta.ru', 'kommersant.ru',
        'interfax.ru', 'tass.ru', 'vedomosti.ru', 'iz.ru'
    ]
    
    if domain.lower() in invalid_domains:
        return False
        
    return True

def search_company_domain(company_name: str, lang: str = 'ru') -> str:
    """Search for a company's domain name using web search."""
    logger.info(f"Searching for domain of company: {company_name}")
    
    # Prepare search query
    if lang == 'ru':
        query = f"компания {company_name} официальный сайт"
    else:
        query = f"company {company_name} official website"
    
    # Add some randomization to avoid being blocked
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # Try different search engines
    search_urls = [
        f"https://www.google.com/search?q={query.replace(' ', '+')}",
        f"https://yandex.ru/search/?text={query.replace(' ', '+')}"
    ]
    
    domains_found = []
    
    for search_url in search_urls:
        try:
            logger.info(f"Searching with URL: {search_url}")
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract all links and visible URLs
                links = []
                
                # For Yandex search results
                if 'yandex.ru' in search_url:
                    # Look for the visible URL text in search results
                    for url_element in soup.select('.OrganicTitleContentSpan'):
                        parent = url_element.parent
                        if parent and parent.name == 'a' and parent.get('href'):
                            links.append(parent.get('href'))
                            logger.debug(f"Found Yandex title link: {parent.get('href')}")
                    
                    # Also look for the green URL text that Yandex displays
                    for url_element in soup.select('.Path-Item'):
                        url_text = url_element.get_text()
                        if url_text and '.' in url_text:
                            links.append(url_text)
                            logger.debug(f"Found Yandex path item: {url_text}")
                    
                    # Look for organic URLs
                    for url_element in soup.select('.organic__url'):
                        if url_element.get('href'):
                            links.append(url_element.get('href'))
                            logger.debug(f"Found Yandex organic URL: {url_element.get('href')}")
                    
                    # Look for visible domain text
                    for url_element in soup.select('.typo_type_greenurl'):
                        url_text = url_element.get_text()
                        if url_text and '.' in url_text:
                            links.append(url_text)
                            logger.debug(f"Found Yandex green URL: {url_text}")
                
                # For all search engines, get regular links
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    # Filter out search engine and common sites
                    if any(se in href for se in ['google.', 'yandex.', 'bing.', 'yahoo.', 'mail.ru', 'vk.com']):
                        continue
                    links.append(href)
                    logger.debug(f"Found regular link: {href}")
                
                # Also look for visible text that looks like a domain
                for text in soup.stripped_strings:
                    if '.' in text and not any(se in text.lower() for se in ['google.', 'yandex.', 'bing.', 'yahoo.']):
                        # Check if it looks like a domain (e.g., example.com)
                        domain_pattern = r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z0-9][-a-zA-Z0-9]+'
                        matches = re.findall(domain_pattern, text)
                        for match in matches:
                            if len(match) > 4:  # Avoid very short matches
                                links.append(match)
                                logger.debug(f"Found domain in text: {match}")
                
                # Extract domains from links
                for link in links:
                    # If the link is already a domain-like string
                    if '.' in link and '/' not in link and ' ' not in link:
                        domain = link.lower()
                        logger.debug(f"Using link as domain directly: {domain}")
                    else:
                        domain = extract_domain_from_url(link)
                        logger.debug(f"Extracted domain from link: {domain} (from {link})")
                    
                    if domain and is_valid_domain(domain):
                        # Additional check: domain should contain part of the company name
                        # or company name should be part of the domain (for short company names)
                        company_words = company_name.lower().split()
                        domain_parts = domain.lower().split('.')
                        
                        # Skip domains that are too generic
                        if len(domain_parts[0]) <= 3:  # Skip very short domains
                            logger.debug(f"Skipping too short domain: {domain}")
                            continue
                        
                        # For company names with multiple words, check if they're combined in the domain
                        company_name_no_spaces = company_name.lower().replace(' ', '')
                        domain_name = domain_parts[0].lower()
                        
                        # Check if domain contains company name or vice versa
                        domain_relevant = False
                        
                        # Check if domain contains company name without spaces
                        if company_name_no_spaces in domain_name:
                            domain_relevant = True
                            logger.debug(f"Domain {domain} contains company name without spaces: {company_name_no_spaces}")
                        
                        # Check if any word from company name is in domain
                        for word in company_words:
                            if len(word) >= 3 and word in domain_name:
                                domain_relevant = True
                                logger.debug(f"Domain {domain} contains company word: {word}")
                                break
                        
                        # Check for transliteration (Russian to Latin)
                        # Simple check for common Russian-to-Latin mappings
                        ru_to_lat = {
                            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
                            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
                        }
                        
                        # Transliterate company name
                        transliterated = ''
                        for char in company_name_no_spaces:
                            transliterated += ru_to_lat.get(char.lower(), char)
                        
                        if transliterated in domain_name:
                            domain_relevant = True
                            logger.debug(f"Domain {domain} contains transliterated company name: {transliterated}")
                        
                        if domain_relevant:
                            logger.info(f"Found relevant domain: {domain} for company {company_name}")
                            domains_found.append(domain)
            
            # Add delay between requests
            time.sleep(random.uniform(1, 3))
            
        except Exception as e:
            logger.error(f"Error searching for domain: {str(e)}")
    
    # Count domain occurrences and sort by frequency
    domain_counts = {}
    for domain in domains_found:
        if domain in domain_counts:
            domain_counts[domain] += 1
        else:
            domain_counts[domain] = 1
    
    # Sort domains by frequency
    sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Log all found domains with their counts
    if sorted_domains:
        logger.info(f"All domains found for {company_name}: {sorted_domains}")
    
    # Return the most frequent domain, or empty string if none found
    if sorted_domains:
        most_likely_domain = sorted_domains[0][0]
        logger.info(f"Found most likely domain for {company_name}: {most_likely_domain}")
        return most_likely_domain
    
    logger.warning(f"No domain found for company: {company_name}")
    return ""

def find_missing_domains(entries: list) -> list:
    """Find missing domains for company names in the entries list.
    
    Args:
        entries: List of (first_name, last_name, domain/company) tuples
        
    Returns:
        List of (first_name, last_name, domain) tuples with domains filled in
    """
    logger.info(f"Finding missing domains for {len(entries)} entries")
    
    result_entries = []
    for entry in entries:
        first_name, last_name, domain_or_company = entry
        
        # Check if the third column is already a valid domain
        if domain_or_company and '.' in domain_or_company:
            # Looks like a domain, clean it up
            domain = domain_or_company.lower()
            domain = re.sub(r'^https?://', '', domain)
            domain = re.sub(r'^www\.', '', domain)
            domain = domain.split('/')[0]  # Remove paths
            
            result_entries.append((first_name, last_name, domain))
            continue
        
        # If not a domain, treat as company name and search for domain
        if domain_or_company:
            domain = search_company_domain(domain_or_company)
            if domain:
                result_entries.append((first_name, last_name, domain))
                logger.info(f"Found domain {domain} for company {domain_or_company}")
            else:
                # If we couldn't find a domain, try a simpler approach - just add .ru to the company name
                company_name_simple = domain_or_company.lower().replace(' ', '')
                if len(company_name_simple) > 3:  # Only if the company name is reasonably long
                    domain = f"{company_name_simple}.ru"
                    result_entries.append((first_name, last_name, domain))
                    logger.info(f"Using simple domain {domain} for company {domain_or_company}")
                else:
                    # Keep the original entry if no domain found
                    result_entries.append(entry)
                    logger.warning(f"Could not find domain for company {domain_or_company}")
        else:
            # Keep the original entry if third column is empty
            result_entries.append(entry)
            logger.warning(f"No company name or domain provided for {first_name} {last_name}")
    
    return result_entries 