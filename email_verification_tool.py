import re
import dns.resolver
import smtplib
import socket
import logging
import time
from typing import Tuple, List, Dict, Any
import random

# Configure more detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("email_verification.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("email_verifier")

def is_valid_syntax(email: str) -> bool:
    # Enhanced pattern with more strict rules
    pattern = r'^(?!.*\.\.)(?!.*\.$)[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if len(email) > 254:
        return False
    local_part = email.split('@')[0]
    if len(local_part) > 64 or len(local_part) < 1:
        return False
    if email.count('@') != 1:
        return False
    return re.match(pattern, email) is not None

def has_mx_record(domain: str, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            logging.debug(f"MX record check attempt {attempt + 1} for {domain}")
            try:
                mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
                if mx_records:
                    return True
            except dns.resolver.NoAnswer:
                # Try A record as fallback
                a_records = dns.resolver.resolve(domain, 'A', lifetime=5)
                if a_records:
                    return True
        except Exception as e:
            if attempt == retries - 1:
                logging.error(f"Failed to resolve records for {domain}: {str(e)}")
                return False
            time.sleep(1)  # Wait before retry
    return False

def email_exists(email: str) -> Tuple[bool, str]:
    logger.info(f"Verifying email existence: {email}")
    domain = email.split('@')[1]
    retries = 2
    
    # Special handling for Russian email providers
    if domain in ['mail.ru', 'inbox.ru', 'list.ru', 'bk.ru', 'internet.ru']:
        # Mail.ru group has specific verification behavior
        logger.info(f"Using special Mail.ru verification for {email}")
        return check_russian_mailru(email)
    elif domain in ['yandex.ru', 'yandex.com', 'ya.ru']:
        # Yandex has specific verification behavior
        logger.info(f"Using special Yandex verification for {email}")
        return check_russian_yandex(email)
    
    for attempt in range(retries):
        try:
            logger.info(f"Attempt {attempt+1} to verify {email}")
            mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
            mx_record = str(mx_records[0].exchange).rstrip('.')
            logger.info(f"Found MX record for {domain}: {mx_record}")
            
            try:
                logger.info(f"Connecting to SMTP server: {mx_record}")
                server = smtplib.SMTP(mx_record, port=25, timeout=10)
                server.set_debuglevel(0)
                
                server.ehlo('mail.google.com')
                logger.info(f"EHLO successful for {mx_record}")
                
                if server.has_extn('STARTTLS'):
                    logger.info(f"Starting TLS for {mx_record}")
                    server.starttls()
                    server.ehlo('mail.google.com')
                
                logger.info(f"Sending MAIL FROM command")
                server.mail('postmaster@gmail.com')
                logger.info(f"Sending RCPT TO command for {email}")
                code, message = server.rcpt(email)
                logger.info(f"RCPT TO response: code={code}, message={message}")
                server.quit()
                
                if code == 250:
                    logger.info(f"Email {email} is valid (code 250)")
                    return True, "Valid"
                elif code in [550, 551, 553, 554]:
                    logger.info(f"Email {email} is invalid (code {code})")
                    return False, "Invalid recipient"
                else:
                    logger.info(f"Email {email} returned ambiguous response: {code}")
                    return False, f"Ambiguous response: {code}"
                    
            except smtplib.SMTPServerDisconnected as e:
                logger.warning(f"Server disconnected while verifying {email}: {str(e)}")
                return False, "Server disconnected"
                
            except (smtplib.SMTPRecipientsRefused,
                    smtplib.SMTPResponseException,
                    socket.timeout,
                    ConnectionRefusedError) as e:
                logger.warning(f"Error while verifying {email}: {str(e)}")
                return False, str(e)
                
        except Exception as e:
            logger.error(f"Exception while verifying {email}: {str(e)}", exc_info=True)
            if attempt == retries - 1:
                return False, str(e)
            time.sleep(1)
    
    logger.warning(f"Verification failed for {email} after all attempts")
    return False, "Verification failed"

def check_russian_mailru(email: str) -> Tuple[bool, str]:
    """Special handling for Mail.ru group email providers."""
    try:
        # Mail.ru often blocks SMTP verification attempts
        # We'll use DNS verification and some heuristics
        domain = email.split('@')[1]
        local_part = email.split('@')[0]
        
        # Check if domain has MX records
        if not has_mx_record(domain):
            return False, "No mail server for domain"
        
        # Mail.ru typically has username restrictions
        if len(local_part) < 3 or len(local_part) > 32:
            return False, "Username length invalid for Mail.ru"
            
        # Mail.ru doesn't allow certain characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', local_part):
            return False, "Invalid characters for Mail.ru"
        
        # We can't definitively verify without SMTP, so return a cautious positive
        return True, "Likely valid (Mail.ru)"
    except Exception as e:
        return False, f"Mail.ru verification error: {str(e)}"

def check_russian_yandex(email: str) -> Tuple[bool, str]:
    """Special handling for Yandex email providers."""
    try:
        # Yandex often blocks SMTP verification attempts
        # We'll use DNS verification and some heuristics
        domain = email.split('@')[1]
        local_part = email.split('@')[0]
        
        # Check if domain has MX records
        if not has_mx_record(domain):
            return False, "No mail server for domain"
        
        # Yandex typically has username restrictions
        if len(local_part) < 3 or len(local_part) > 30:
            return False, "Username length invalid for Yandex"
            
        # Yandex doesn't allow certain characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', local_part):
            return False, "Invalid characters for Yandex"
        
        # We can't definitively verify without SMTP, so return a cautious positive
        return True, "Likely valid (Yandex)"
    except Exception as e:
        return False, f"Yandex verification error: {str(e)}"

def verify_email(email: str, timeout: int = 30) -> bool:
    """Verify a single email address and return True if valid, False otherwise.
    
    Args:
        email: Email address to verify
        timeout: Maximum time in seconds to spend on verification
        
    Returns:
        bool: True if the email is valid, False otherwise
    """
    logger.info(f"Verifying single email: {email} with {timeout}s timeout")
    
    if not email:  # Skip empty emails
        logger.info("Empty email provided")
        return False
    
    start_time = time.time()
    
    # Basic validation
    if not is_valid_syntax(email):
        logger.info(f"Email {email} has invalid syntax")
        return False
    
    domain = email.split('@')[1]
    logger.info(f"Extracted domain: {domain}")
    
    # Domain checks
    if domain.endswith(('.local', '.test', '.example', '.invalid')):
        logger.info(f"Domain {domain} is invalid (reserved TLD)")
        return False
        
    if not has_mx_record(domain):
        logger.info(f"Domain {domain} has no mail server")
        return False
    
    # Add random delay to avoid being blocked
    delay = random.uniform(1, 3)
    logger.info(f"Adding delay of {delay:.2f} seconds before SMTP check")
    time.sleep(delay)
    
    # Check if we've exceeded the timeout
    if time.time() - start_time > timeout:
        logger.warning(f"Timeout exceeded for {email}, skipping SMTP verification")
        return False
    
    # SMTP verification
    logger.info(f"Performing SMTP verification for {email}")
    try:
        # Set a timeout for the SMTP verification
        remaining_time = timeout - (time.time() - start_time)
        if remaining_time <= 0:
            logger.warning(f"No time left for SMTP verification of {email}")
            return False
            
        # Use a separate thread with timeout for email verification
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def verify_with_timeout():
            try:
                exists, reason = email_exists(email)
                result_queue.put((exists, reason))
            except Exception as e:
                logger.error(f"Error in verification thread: {str(e)}")
                result_queue.put((False, f"Error: {str(e)}"))
        
        verification_thread = threading.Thread(target=verify_with_timeout)
        verification_thread.daemon = True
        verification_thread.start()
        
        try:
            exists, reason = result_queue.get(timeout=remaining_time)
            if exists:
                logger.info(f"Email {email} is valid: {reason}")
                return True
            else:
                logger.info(f"Email {email} is invalid: {reason}")
                return False
        except queue.Empty:
            logger.warning(f"SMTP verification timed out for {email}")
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error during verification of {email}: {str(e)}")
        return False

def verify_emails(emails: List[str], timeout_per_email: int = 30) -> List[Tuple[str, str]]:
    """Verify a list of emails and return results.
    
    Args:
        emails: List of email addresses to verify
        timeout_per_email: Maximum time in seconds to spend on each email verification
    """
    logger.info(f"Starting verification of {len(emails)} emails with {timeout_per_email}s timeout per email")
    results = []
    for email in emails:
        if not email:  # Skip empty emails
            logger.info("Skipping empty email")
            continue
            
        logger.info(f"Verifying email: {email}")
        start_time = time.time()
        
        # Basic validation
        if not is_valid_syntax(email):
            logger.info(f"Email {email} has invalid syntax")
            results.append((email, 'Invalid syntax'))
            continue
        
        domain = email.split('@')[1]
        logger.info(f"Extracted domain: {domain}")
        
        # Domain checks
        if domain.endswith(('.local', '.test', '.example', '.invalid')):
            logger.info(f"Domain {domain} is invalid (reserved TLD)")
            results.append((email, 'Invalid domain'))
            continue
            
        if not has_mx_record(domain):
            logger.info(f"Domain {domain} has no mail server")
            results.append((email, 'Invalid domain (no mail server)'))
            continue
        
        # Add random delay to avoid being blocked
        delay = random.uniform(1, 3)
        logger.info(f"Adding delay of {delay:.2f} seconds before SMTP check")
        time.sleep(delay)
        
        # Check if we've exceeded the timeout
        if time.time() - start_time > timeout_per_email:
            logger.warning(f"Timeout exceeded for {email}, skipping SMTP verification")
            results.append((email, 'Verification timeout'))
            continue
        
        # SMTP verification
        logger.info(f"Performing SMTP verification for {email}")
        try:
            # Set a timeout for the SMTP verification
            remaining_time = timeout_per_email - (time.time() - start_time)
            if remaining_time <= 0:
                logger.warning(f"No time left for SMTP verification of {email}")
                results.append((email, 'Verification timeout'))
                continue
                
            # Use a separate thread with timeout for email verification
            import threading
            import queue
            
            result_queue = queue.Queue()
            
            def verify_with_timeout():
                try:
                    exists, reason = email_exists(email)
                    result_queue.put((exists, reason))
                except Exception as e:
                    logger.error(f"Error in verification thread: {str(e)}")
                    result_queue.put((False, f"Error: {str(e)}"))
            
            verification_thread = threading.Thread(target=verify_with_timeout)
            verification_thread.daemon = True
            verification_thread.start()
            
            try:
                exists, reason = result_queue.get(timeout=remaining_time)
                if exists:
                    logger.info(f"Email {email} is valid: {reason}")
                    results.append((email, 'Valid email'))
                else:
                    logger.info(f"Email {email} is invalid: {reason}")
                    results.append((email, f'Invalid email: {reason}'))
            except queue.Empty:
                logger.warning(f"SMTP verification timed out for {email}")
                results.append((email, 'SMTP verification timeout'))
                
        except Exception as e:
            logger.error(f"Unexpected error during verification of {email}: {str(e)}")
            results.append((email, f'Error: {str(e)}'))
    
    logger.info(f"Completed verification of {len(emails)} emails")
    return results

def batch_verify_emails(email_batches: List[List[str]], timeout_per_email: int = 30) -> Dict[str, str]:
    """Verify batches of emails with proper rate limiting."""
    all_results = {}
    
    for batch_index, email_batch in enumerate(email_batches):
        logger.info(f"Processing batch {batch_index + 1}/{len(email_batches)}")
        
        # Verify the batch
        batch_results = verify_emails(email_batch, timeout_per_email=timeout_per_email)
        
        # Store results
        for email, status in batch_results:
            all_results[email] = status
            
        # Add delay between batches to avoid rate limiting
        if batch_index < len(email_batches) - 1:
            delay = random.uniform(5, 10)
            logger.info(f"Adding delay of {delay:.2f} seconds between batches")
            time.sleep(delay)
    
    return all_results

def process_name_entries(entries: List[Tuple[str, str, str]], 
                         email_variations_func,
                         timeout_per_email: int = 30,
                         stop_on_first_valid: bool = True) -> List[Dict[str, Any]]:
    """Process a list of name entries and verify generated emails.
    
    Args:
        entries: List of (first_name, last_name, domain) tuples
        email_variations_func: Function to generate email variations
        timeout_per_email: Maximum time in seconds to spend on each email verification
        stop_on_first_valid: If True, stop verifying emails for a person once a valid one is found
    """
    logger.info(f"Processing {len(entries)} name entries with {timeout_per_email}s timeout per email")
    logger.info(f"Stop on first valid email: {stop_on_first_valid}")
    
    results = []
    
    # Process each name entry individually for better control
    for entry in entries:
        first_name, last_name, domain = entry
        logger.info(f"Processing entry: {first_name} {last_name} at {domain}")
        
        # Generate email variations
        email_variations = email_variations_func(first_name, last_name, domain)
        logger.info(f"Generated {len(email_variations)} variations: {email_variations}")
        
        # Verify emails one by one
        valid_emails = []
        
        for email in email_variations:
            logger.info(f"Verifying email: {email}")
            
            # Verify single email
            email_results = verify_emails([email], timeout_per_email=timeout_per_email)
            
            if email_results and 'Valid' in email_results[0][1]:
                logger.info(f"Found valid email: {email}")
                valid_emails.append((email, email_results[0][1]))
                
                # If we should stop on first valid email, break the loop
                if stop_on_first_valid:
                    logger.info(f"Stopping verification for {first_name} {last_name} after finding valid email")
                    break
            else:
                logger.info(f"Email {email} is not valid")
        
        # Add to results if we found valid emails
        if valid_emails:
            # Sort by most likely to be valid
            valid_emails.sort(key=lambda x: 0 if 'Valid email' in x[1] else 1)
            
            # Add best email to results
            best_email, status = valid_emails[0]
            logger.info(f"Best email for {first_name} {last_name}: {best_email} ({status})")
            
            results.append({
                'first_name': first_name,
                'last_name': last_name,
                'domain': domain,
                'valid_email': best_email,
                'status': status
            })
        else:
            logger.warning(f"No valid emails found for {first_name} {last_name} at {domain}")
    
    logger.info(f"Completed processing with {len(results)} valid results")
    return results
