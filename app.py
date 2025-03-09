from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import email_verification_tool
import russian_email_generator
import google_sheets_handler
import domain_finder
import os
import json
import logging
import threading
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("email_finder_app")

# Set domain_finder logger to DEBUG level
domain_finder_logger = logging.getLogger("domain_finder")
domain_finder_logger.setLevel(logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Get default settings from environment variables
DEFAULT_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH')
DEFAULT_CREDENTIALS_JSON = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
DEFAULT_TIMEOUT = int(os.getenv('EMAIL_VERIFICATION_TIMEOUT', 30))
DEFAULT_STOP_ON_FIRST_VALID = os.getenv('STOP_ON_FIRST_VALID', 'true').lower() == 'true'

# Check if we have credentials in .env
if not DEFAULT_CREDENTIALS_JSON and not DEFAULT_CREDENTIALS_PATH:
    logger.warning("No Google credentials found in .env file")

# Global variables to track verification progress
verification_progress = {
    'status': 'idle',
    'total': 0,
    'current': 0,
    'valid_emails': [],
    'all_checked_emails': {},
    'current_name': '',
    'current_email': '',
    'current_email_index': 0,
    'total_emails': 0,
    'error_message': '',
    'type': ''
}

# Flag to signal background threads to stop
stop_processing = False

verification_lock = threading.Lock()

@app.route('/', methods=['GET', 'POST'])
def home():
    logger.info("Home page accessed")
    if request.method == 'POST':
        logger.info("POST request to home page")
        # Check if the post request has the sheet_url part
        if 'sheet_url' in request.form:
            logger.info("Google Sheets form submitted")
            sheet_url = request.form.get('sheet_url')
            logger.info(f"Sheet URL: {sheet_url}")
            
            # Check if we have credentials in .env
            if DEFAULT_CREDENTIALS_JSON:
                logger.info("Using JSON credentials from GOOGLE_APPLICATION_CREDENTIALS in .env")
                credentials_source = DEFAULT_CREDENTIALS_JSON
            elif DEFAULT_CREDENTIALS_PATH:
                if not os.path.exists(DEFAULT_CREDENTIALS_PATH):
                    logger.warning(f"Credentials file not found at {DEFAULT_CREDENTIALS_PATH}")
                    flash(f'Credentials file not found at {DEFAULT_CREDENTIALS_PATH}. Please check your .env file.')
                    return redirect(request.url)
                
                logger.info(f"Using credentials path from .env: {DEFAULT_CREDENTIALS_PATH}")
                credentials_source = DEFAULT_CREDENTIALS_PATH
            else:
                logger.warning("No credentials found in .env file")
                flash('No credentials found in .env file. Please set GOOGLE_APPLICATION_CREDENTIALS in .env.')
                return redirect(request.url)
            
            # Store the credentials source and sheet URL in session
            session['credentials_source'] = credentials_source
            session['sheet_url'] = sheet_url
            
            # Redirect to processing page
            logger.info("Redirecting to process_sheet page")
            return redirect(url_for('process_sheet'))
    
    # Check if credentials are available
    has_credentials = bool(DEFAULT_CREDENTIALS_JSON or DEFAULT_CREDENTIALS_PATH)
    credentials_info = ""
    credentials_source = ""
    
    if DEFAULT_CREDENTIALS_JSON:
        credentials_info = "Using JSON credentials from .env"
        credentials_source = DEFAULT_CREDENTIALS_JSON
    elif DEFAULT_CREDENTIALS_PATH:
        credentials_info = f"Using credentials file: {DEFAULT_CREDENTIALS_PATH}"
        credentials_source = DEFAULT_CREDENTIALS_PATH
    
    return render_template('index.html', 
                          has_credentials=has_credentials,
                          credentials_info=credentials_info,
                          credentials_source=credentials_source)

@app.route('/process', methods=['GET', 'POST'])
def process_sheet():
    """Process a Google Sheet."""
    if request.method == 'POST':
        try:
            # Get form data
            sheet_url = request.form.get('sheet_url', '')
            credentials_source = request.form.get('credentials_source', '')
            timeout = int(request.form.get('timeout', 10))
            stop_on_first_valid = request.form.get('stop_on_first_valid') == 'on'
            
            # Log the received data
            logger.info(f"Process sheet form submitted with URL: {sheet_url}, credentials: {credentials_source}")
            
            # Validate sheet URL
            if not sheet_url:
                flash('Please enter a Google Sheet URL', 'danger')
                return redirect(url_for('home'))
            
            # Initialize Google Sheets handler
            sheets_handler = google_sheets_handler.GoogleSheetsHandler(credentials_source)
            
            # Get data from sheet
            logger.info(f"Fetching data from sheet: {sheet_url}")
            sheet_data = sheets_handler.get_sheet_data(sheet_url)
            
            if not sheet_data or len(sheet_data) < 2:  # Check if there's data (excluding header)
                flash('No data found in the sheet or sheet is not accessible', 'danger')
                return redirect(url_for('home'))
            
            # Extract header and data
            header = sheet_data[0]
            data_rows = sheet_data[1:]
            
            # Validate header (need at least first name and last name columns)
            if len(header) < 2:
                flash('Sheet must have at least 2 columns (First Name, Last Name)', 'danger')
                return redirect(url_for('home'))
            
            # Extract name entries (first_name, last_name, domain)
            name_entries = []
            for row in data_rows:
                if len(row) >= 2 and row[0] and row[1]:  # Must have first and last name
                    first_name = row[0].strip()
                    last_name = row[1].strip()
                    
                    # Get domain or company name from third column if available
                    domain_or_company = row[2].strip() if len(row) > 2 and row[2] else ""
                    
                    name_entries.append((first_name, last_name, domain_or_company))
            
            if not name_entries:
                flash('No valid entries found in the sheet', 'danger')
                return redirect(url_for('home'))
            
            # Store data in session
            session['name_entries'] = name_entries
            session['credentials_source'] = credentials_source
            session['sheet_url'] = sheet_url
            session['timeout'] = timeout
            session['stop_on_first_valid'] = stop_on_first_valid
            session['total_entries'] = len(name_entries)
            
            logger.info(f"Successfully processed sheet with {len(name_entries)} entries")
            
            # Show preview before processing
            preview_data = name_entries[:10]  # Show first 10 entries
            
            # Check if we have any entries with company names instead of domains
            has_company_names = any(entry[2] and '.' not in entry[2] for entry in name_entries)
            
            return render_template(
                'sheet_preview.html',
                preview_data=preview_data,
                total_entries=len(name_entries),
                credentials_source=credentials_source,
                sheet_url=sheet_url,
                timeout=timeout,
                stop_on_first_valid=stop_on_first_valid,
                has_company_names=has_company_names
            )
            
        except Exception as e:
            logger.error(f"Error processing sheet: {str(e)}", exc_info=True)
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('home'))
    
    # If GET request or if we have data in session, show the preview
    if 'name_entries' in session and 'sheet_url' in session:
        name_entries = session['name_entries']
        sheet_url = session['sheet_url']
        credentials_source = session.get('credentials_source', '')
        timeout = session.get('timeout', 10)
        stop_on_first_valid = session.get('stop_on_first_valid', True)
        
        # Show preview before processing
        preview_data = name_entries[:10]  # Show first 10 entries
        
        # Check if we have any entries with company names instead of domains
        has_company_names = any(entry[2] and '.' not in entry[2] for entry in name_entries)
        
        return render_template(
            'sheet_preview.html',
            preview_data=preview_data,
            total_entries=len(name_entries),
            credentials_source=credentials_source,
            sheet_url=sheet_url,
            timeout=timeout,
            stop_on_first_valid=stop_on_first_valid,
            has_company_names=has_company_names
        )
    
    # If no data in session, redirect to home
    return redirect(url_for('home'))

def process_sheet_in_background(name_entries, credentials_source, sheet_url, timeout, stop_on_first_valid):
    """Process the sheet data in a background thread."""
    global verification_progress
    global stop_processing
    
    # Reset stop flag
    stop_processing = False
    
    try:
        verification_progress['status'] = 'running'
        verification_progress['current'] = 0
        verification_progress['total'] = len(name_entries)
        verification_progress['valid_emails'] = []
        verification_progress['all_checked_emails'] = {}
        verification_progress['current_name'] = ""
        verification_progress['current_email'] = ""
        verification_progress['current_email_index'] = 0
        verification_progress['total_emails'] = 0
        verification_progress['error_message'] = ""
        
        logger.info(f"Starting to process {len(name_entries)} entries from sheet")
        
        # Check if we need to find missing domains
        has_missing_domains = any(not entry[2] or '.' not in entry[2] for entry in name_entries)
        
        if has_missing_domains:
            logger.info("Found entries with missing domains or company names. Attempting to find domains...")
            verification_progress['status'] = 'finding_domains'
            try:
                # Find missing domains
                name_entries_with_domains = domain_finder.find_missing_domains(name_entries)
                
                # Log the results
                for i, (original, with_domain) in enumerate(zip(name_entries, name_entries_with_domains)):
                    orig_first, orig_last, orig_domain = original
                    new_first, new_last, new_domain = with_domain
                    
                    if orig_domain != new_domain:
                        logger.info(f"Found domain for entry {i+1}: {orig_first} {orig_last} - {orig_domain} -> {new_domain}")
                
                # Update name_entries with the new domains
                name_entries = name_entries_with_domains
                
                # Update status back to running
                verification_progress['status'] = 'running'
            except Exception as e:
                logger.error(f"Error finding domains: {str(e)}")
                verification_progress['status'] = 'error'
                verification_progress['error_message'] = f"Error finding domains: {str(e)}"
                return
        
        for i, entry in enumerate(name_entries):
            # Check if we should stop processing
            if stop_processing:
                logger.info("Processing stopped by user")
                verification_progress['status'] = 'stopped'
                verification_progress['error_message'] = "Processing stopped by user"
                return
                
            try:
                first_name, last_name, domain = entry
                
                # Update progress
                verification_progress['current'] = i + 1
                verification_progress['current_name'] = f"{first_name} {last_name} ({domain})"
                
                # Skip if domain is still missing
                if not domain or '.' not in domain:
                    logger.warning(f"Skipping entry {i+1}: {first_name} {last_name} - No valid domain found")
                    continue
                    
                logger.info(f"Processing entry {i+1}/{len(name_entries)}: {first_name} {last_name} ({domain})")
                
                # Generate email variations
                email_variations = russian_email_generator.generate_email_variations(first_name, last_name, domain)
                
                # Reset email progress tracking
                verification_progress['current_email_index'] = 0
                verification_progress['total_emails'] = len(email_variations)
                verification_progress['current_email'] = ""
                
                # Store all email variations for this person
                person_key = f"{first_name} {last_name} ({domain})"
                verification_progress['all_checked_emails'][person_key] = []
                
                # Check each email variation
                valid_email_found = False
                
                for j, email in enumerate(email_variations):
                    try:
                        # Update email progress
                        verification_progress['current_email'] = email
                        verification_progress['current_email_index'] = j
                        
                        logger.info(f"Checking email {j+1}/{len(email_variations)}: {email}")
                        
                        is_valid = email_verification_tool.verify_email(email, timeout)
                        
                        # Store result for this email
                        verification_progress['all_checked_emails'][person_key].append({
                            'email': email,
                            'is_valid': is_valid
                        })
                        
                        if is_valid:
                            logger.info(f"Valid email found: {email}")
                            verification_progress['valid_emails'].append({
                                'first_name': first_name,
                                'last_name': last_name,
                                'domain': domain,
                                'email': email
                            })
                            valid_email_found = True
                            
                            # Stop checking if we found a valid email and stop_on_first_valid is True
                            if stop_on_first_valid:
                                break
                    except Exception as e:
                        logger.error(f"Error verifying email {email}: {str(e)}")
                        # Store error result
                        verification_progress['all_checked_emails'][person_key].append({
                            'email': email,
                            'is_valid': False,
                            'error': str(e)
                        })
                    
                    # Add a small delay between email checks to avoid being blocked
                    time.sleep(1)
                
                # If we've processed all emails for this person, log the result
                if not valid_email_found:
                    logger.warning(f"No valid email found for {first_name} {last_name} ({domain})")
            except Exception as e:
                logger.error(f"Error processing entry {i+1}: {str(e)}")
                # Continue with next entry instead of failing the entire process
                continue
        
        # Update progress to complete
        logger.info("Sheet processing complete")
        verification_progress['status'] = 'complete'
        
        # Store results in session for the results page
        session['sheet_results'] = {
            'valid_emails': verification_progress['valid_emails'],
            'all_checked_emails': verification_progress['all_checked_emails'],
            'total_processed': len(name_entries)
        }
        
    except Exception as e:
        logger.error(f"Error processing sheet: {str(e)}")
        verification_progress['status'] = 'error'
        verification_progress['error_message'] = str(e)

@app.route('/sheet_progress')
def sheet_progress():
    """Show progress of sheet processing."""
    # Check if we have data in session
    if 'name_entries' not in session:
        flash('No data to process. Please upload a sheet first.', 'danger')
        return redirect(url_for('home'))
    
    # Get total entries from session
    total_entries = session.get('total_entries', 0)
    
    # Check if processing has started
    if verification_progress.get('status') == 'idle':
        flash('Processing has not started yet.', 'warning')
        return redirect(url_for('process_sheet'))
    
    return render_template('sheet_progress.html', total_entries=total_entries)

@app.route('/sheet_progress_data')
def get_sheet_progress_data():
    """Return the current progress data for sheet processing."""
    global verification_progress
    
    # Calculate percentage
    total = verification_progress.get('total', 0)
    current = verification_progress.get('current', 0)
    percent = int((current / total * 100) if total > 0 else 0)
    
    # Calculate email percentage
    total_emails = verification_progress.get('total_emails', 0)
    current_email_index = verification_progress.get('current_email_index', 0)
    email_percent = int(((current_email_index + 1) / total_emails * 100) if total_emails > 0 else 0)
    
    # Prepare response
    response = {
        'status': verification_progress.get('status', 'initializing'),
        'current': current,
        'total': total,
        'percent': percent,
        'current_name': verification_progress.get('current_name', ''),
        'current_email': verification_progress.get('current_email', ''),
        'current_email_index': current_email_index,
        'total_emails': total_emails,
        'email_percent': email_percent
    }
    
    # Add error message if status is error
    if verification_progress.get('status') == 'error' and 'error_message' in verification_progress:
        response['error_message'] = verification_progress.get('error_message', '')
    
    # Use Flask's jsonify to ensure proper JSON response
    return jsonify(response)

@app.route('/sheet_results')
def sheet_results():
    """Display the results of sheet processing."""
    # Check if we have results in session
    if 'sheet_results' in session:
        # Get results from session
        sheet_results = session.get('sheet_results', {})
        results = sheet_results.get('valid_emails', [])
        all_checked_emails = sheet_results.get('all_checked_emails', {})
        num_processed = sheet_results.get('total_processed', 0)
    else:
        # Fall back to verification_progress if session data is not available
        global verification_progress
        
        if verification_progress.get('status') != 'complete':
            flash('Processing is not complete yet', 'warning')
            return redirect(url_for('sheet_progress'))
        
        # Get results from verification progress
        results = verification_progress.get('valid_emails', [])
        all_checked_emails = verification_progress.get('all_checked_emails', {})
        num_processed = verification_progress.get('total', 0)
    
    # Count the number of valid emails
    num_valid = len(results)
    
    # Extract domain finding information if available
    domains_found = {}
    original_entries = session.get('name_entries', [])
    
    # Create a mapping of original company names to domains
    company_to_domain = {}
    for entry in original_entries:
        first_name, last_name, domain_or_company = entry
        if domain_or_company and '.' not in domain_or_company:
            # This is a company name, not a domain
            company_name = domain_or_company
            # Look for this person in all_checked_emails to find the domain that was used
            person_key_pattern = f"{first_name} {last_name} ("
            for person_key in all_checked_emails.keys():
                if person_key.startswith(person_key_pattern):
                    # Extract the domain from the key
                    domain = person_key.split('(')[1].rstrip(')')
                    if domain and '.' in domain:
                        # Found a domain for this company
                        company_to_domain[company_name] = domain
                        break
    
    # Store the company to domain mapping
    domains_found = company_to_domain
    
    # Store results in session for the all_checked_emails page
    session['all_checked_emails'] = all_checked_emails
    
    return render_template(
        'sheet_results.html',
        results=results,
        num_processed=num_processed,
        num_valid=num_valid,
        domains_found=domains_found
    )

@app.route('/all_checked_emails')
def all_checked_emails():
    """Page that shows all checked emails for the sheet processing."""
    logger.info("All checked emails page accessed")
    
    with verification_lock:
        if verification_progress['type'] != 'sheet' or verification_progress['status'] != 'complete':
            logger.warning("Tried to access all checked emails before processing complete")
            flash("No email verification data available.")
            return redirect(url_for('home'))
        
        all_checked_emails = verification_progress['all_checked_emails']
    
    return render_template('all_checked_emails.html',
                          all_checked_emails=all_checked_emails)

@app.route('/manual', methods=['GET', 'POST'])
def manual_entry():
    logger.info("Manual entry page accessed")
    if request.method == 'POST':
        logger.info("Manual entry form submitted")
        first_name = request.form.get('first_name', '')
        last_name = request.form.get('last_name', '')
        domain = request.form.get('domain', '')
        
        # Get timeout parameter if provided
        try:
            timeout = int(request.form.get('timeout', '30'))
        except ValueError:
            timeout = 30
            
        # Get stop_on_first_valid parameter
        stop_on_first_valid = request.form.get('stop_on_first_valid') == 'on'
        
        logger.info(f"Form data: first_name={first_name}, last_name={last_name}, domain={domain}, timeout={timeout}, stop_on_first_valid={stop_on_first_valid}")
        
        if first_name and last_name and domain:
            # Generate email variations
            logger.info("Generating email variations")
            email_variations = russian_email_generator.generate_email_variations(
                first_name, last_name, domain
            )
            logger.info(f"Generated {len(email_variations)} variations: {email_variations}")
            
            # Store data in session for the verification page
            session['verification_data'] = {
                'first_name': first_name,
                'last_name': last_name,
                'domain': domain,
                'email_variations': email_variations,
                'timeout': timeout,
                'stop_on_first_valid': stop_on_first_valid
            }
            
            # Redirect to verification page
            return redirect(url_for('verify_emails'))
        else:
            logger.warning("Missing required fields in manual entry form")
            flash("Please fill in all fields")
            return redirect(url_for('manual_entry'))
    
    return render_template('manual_entry.html')

@app.route('/verify')
def verify_emails():
    """Page that shows verification progress and results."""
    logger.info("Verify emails page accessed")
    
    # Check if we have verification data in session
    if 'verification_data' not in session:
        logger.warning("No verification data in session")
        flash("No verification data found. Please enter name and domain first.")
        return redirect(url_for('manual_entry'))
    
    verification_data = session['verification_data']
    
    # Start verification in a background thread if not already running
    with verification_lock:
        if verification_progress['status'] == 'idle':
            verification_progress['status'] = 'running'
            verification_progress['total'] = len(verification_data['email_variations'])
            verification_progress['current'] = 0
            verification_progress['results'] = []
            verification_progress['current_name'] = ''
            verification_progress['all_checked_emails'] = {}
            verification_progress['type'] = 'manual'
            verification_progress['stop_on_first_valid'] = verification_data.get('stop_on_first_valid', True)
            verification_progress['total_emails'] = len(verification_data['email_variations'])
            verification_progress['current_email_index'] = 0
            verification_progress['current_email'] = ''
            
            # Start verification in a background thread
            threading.Thread(
                target=run_verification_in_background,
                args=(
                    verification_data['email_variations'],
                    verification_data['timeout']
                )
            ).start()
    
    return render_template('verify.html',
                          first_name=verification_data['first_name'],
                          last_name=verification_data['last_name'],
                          domain=verification_data['domain'],
                          total_emails=len(verification_data['email_variations']),
                          stop_on_first_valid=verification_data.get('stop_on_first_valid', True))

def run_verification_in_background(email_variations, timeout):
    """Run email verification in a background thread."""
    global verification_progress
    global stop_processing
    
    # Reset stop flag
    stop_processing = False
    
    try:
        verification_progress['status'] = 'running'
        verification_progress['total_emails'] = len(email_variations)
        verification_progress['current_email_index'] = 0
        
        valid_emails = []
        all_checked_emails = []
        
        for i, email in enumerate(email_variations):
            # Check if we should stop processing
            if stop_processing:
                logger.info("Verification stopped by user")
                verification_progress['status'] = 'stopped'
                verification_progress['error_message'] = "Verification stopped by user"
                return
                
            try:
                # Update progress
                verification_progress['current_email'] = email
                verification_progress['current_email_index'] = i
                
                logger.info(f"Checking email {i+1}/{len(email_variations)}: {email}")
                
                is_valid = email_verification_tool.verify_email(email, timeout)
                
                # Store result
                result = {
                    'email': email,
                    'is_valid': is_valid
                }
                all_checked_emails.append(result)
                
                if is_valid:
                    logger.info(f"Valid email found: {email}")
                    valid_emails.append(email)
                    
                    # Stop if we found a valid email and stop_on_first_valid is True
                    if session.get('stop_on_first_valid', True):
                        logger.info("Stop on first valid is enabled, stopping verification")
                        break
            except Exception as e:
                logger.error(f"Error verifying email {email}: {str(e)}")
                # Store error result
                all_checked_emails.append({
                    'email': email,
                    'is_valid': False,
                    'error': str(e)
                })
            
            # Add a small delay between email checks to avoid being blocked
            time.sleep(1)
        
        # Update progress to complete
        verification_progress['status'] = 'complete'
        verification_progress['valid_emails'] = valid_emails
        verification_progress['all_checked_emails'] = all_checked_emails
        logger.info("Email verification complete")
        
        # Store results in session for the results page
        session['verification_results'] = {
            'valid_emails': valid_emails,
            'all_checked_emails': all_checked_emails,
            'first_name': session.get('first_name', ''),
            'last_name': session.get('last_name', ''),
            'domain': session.get('domain', '')
        }
        
    except Exception as e:
        logger.error(f"Error in verification thread: {str(e)}")
        verification_progress['status'] = 'error'
        verification_progress['error_message'] = str(e)

@app.route('/verification_progress')
def get_verification_progress():
    """Return the current progress data for email verification."""
    global verification_progress
    
    # Calculate email percentage
    total_emails = verification_progress.get('total_emails', 0)
    current_email_index = verification_progress.get('current_email_index', 0)
    email_percent = int(((current_email_index + 1) / total_emails * 100) if total_emails > 0 else 0)
    
    # Prepare response
    response = {
        'status': verification_progress.get('status', 'initializing'),
        'current_email': verification_progress.get('current_email', ''),
        'current_email_index': current_email_index,
        'total_emails': total_emails,
        'email_percent': email_percent
    }
    
    # Add error message if status is error
    if verification_progress.get('status') == 'error' and 'error_message' in verification_progress:
        response['error_message'] = verification_progress.get('error_message', '')
    
    # Use Flask's jsonify to ensure proper JSON response
    return jsonify(response)

@app.route('/verification_results')
def get_verification_results():
    """Display the results of email verification."""
    # Check if we have results in session
    if 'verification_results' in session:
        # Get results from session
        verification_results = session.get('verification_results', {})
        valid_emails = verification_results.get('valid_emails', [])
        all_checked_emails = verification_results.get('all_checked_emails', [])
        first_name = verification_results.get('first_name', '')
        last_name = verification_results.get('last_name', '')
        domain = verification_results.get('domain', '')
    else:
        # Fall back to verification_progress if session data is not available
        global verification_progress
        
        if verification_progress.get('status') != 'complete':
            flash('Verification is not complete yet', 'warning')
            return redirect(url_for('verify_emails'))
        
        # Get data from session
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        domain = session.get('domain', '')
        
        # Get results from verification progress
        valid_emails = verification_progress.get('valid_emails', [])
        all_checked_emails = verification_progress.get('all_checked_emails', [])
    
    return render_template(
        'verification_results.html',
        first_name=first_name,
        last_name=last_name,
        domain=domain,
        valid_emails=valid_emails,
        all_checked_emails=all_checked_emails
    )

@app.route('/logs')
def view_logs():
    """View the application logs in the browser."""
    logger.info("Logs page accessed")
    
    log_files = {
        'app': 'app.log',
        'email_verification': 'email_verification.log'
    }
    
    log_type = request.args.get('type', 'app')
    log_file = log_files.get(log_type, 'app.log')
    
    try:
        with open(log_file, 'r') as f:
            logs = f.readlines()
            # Get the last 100 lines (most recent logs)
            logs = logs[-100:] if len(logs) > 100 else logs
    except FileNotFoundError:
        logs = [f"Log file {log_file} not found"]
    
    return render_template('logs.html', logs=logs, log_type=log_type)

@app.route('/start_processing', methods=['POST'])
def start_processing():
    """Start processing the sheet after preview."""
    if 'name_entries' not in session:
        flash('No data to process. Please upload a sheet first.', 'danger')
        return redirect(url_for('home'))
    
    try:
        # Get data from session
        name_entries = session['name_entries']
        credentials_source = session.get('credentials_source', '')
        sheet_url = session.get('sheet_url', '')
        timeout = session.get('timeout', 10)
        
        # Get stop_on_first_valid from form or session
        stop_on_first_valid = request.form.get('stop_on_first_valid') == 'on'
        logger.info(f"Stop on first valid from form: {stop_on_first_valid}")
        
        # Update session with the new value
        session['stop_on_first_valid'] = stop_on_first_valid
        
        logger.info(f"Starting processing of {len(name_entries)} entries from sheet: {sheet_url}")
        logger.info(f"Stop on first valid: {stop_on_first_valid}")
        
        # Reset progress tracking
        global verification_progress
        verification_progress = {
            'status': 'initializing',
            'total': len(name_entries),
            'current': 0,
            'valid_emails': [],
            'all_checked_emails': {},
            'current_name': '',
            'current_email': '',
            'current_email_index': 0,
            'total_emails': 0,
            'error_message': '',
            'type': 'sheet'
        }
        
        # Start processing in a background thread
        processing_thread = threading.Thread(
            target=process_sheet_in_background,
            args=(
                name_entries,
                credentials_source,
                sheet_url,
                timeout,
                stop_on_first_valid
            ),
            daemon=True
        )
        processing_thread.start()
        
        # Redirect to the progress page
        return redirect(url_for('sheet_progress'))
        
    except Exception as e:
        logger.error(f"Error starting processing: {str(e)}", exc_info=True)
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('home'))

@app.route('/cancel_processing')
def cancel_processing():
    """Cancel the current processing."""
    global stop_processing
    global verification_progress
    
    # Set the stop flag to signal background threads to stop
    stop_processing = True
    
    # Update the verification progress
    verification_progress['status'] = 'stopping'
    verification_progress['error_message'] = "Processing is being stopped..."
    
    logger.info("User requested to stop processing")
    flash('Processing is being stopped. Please wait a moment...', 'warning')
    
    # Redirect to home
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=port)
