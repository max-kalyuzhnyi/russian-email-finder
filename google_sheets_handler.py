import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import List, Tuple, Dict, Any
import re
import json
import os
import tempfile
import logging

logger = logging.getLogger("google_sheets")

class GoogleSheetsHandler:
    def __init__(self, credentials_source: str):
        """Initialize the Google Sheets handler with credentials.
        
        Args:
            credentials_source: Either a path to a JSON file or the JSON credentials string
        """
        self.scope = ['https://spreadsheets.google.com/feeds',
                      'https://www.googleapis.com/auth/drive']
        
        # Check if credentials_source is a file path or a JSON string
        if os.path.exists(credentials_source):
            # It's a file path
            logger.info(f"Loading credentials from file: {credentials_source}")
            self.credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_source, self.scope)
        else:
            # Try to parse as JSON string
            try:
                logger.info("Loading credentials from JSON string")
                # Create a temporary file to store the credentials
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    temp_file.write(credentials_source)
                    temp_path = temp_file.name
                
                # Load credentials from the temporary file
                self.credentials = ServiceAccountCredentials.from_json_keyfile_name(temp_path, self.scope)
                
                # Delete the temporary file
                os.unlink(temp_path)
                logger.info("Successfully loaded credentials from JSON string")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON credentials: {str(e)}")
                raise ValueError(f"Invalid JSON credentials: {str(e)}")
            except Exception as e:
                logger.error(f"Error loading credentials: {str(e)}")
                raise ValueError(f"Error loading credentials: {str(e)}")
        
        try:
            self.client = gspread.authorize(self.credentials)
            logger.info("Successfully authorized with Google Sheets API")
        except Exception as e:
            logger.error(f"Authorization failed: {str(e)}")
            raise ValueError(f"Authorization failed: {str(e)}")
    
    def get_sheet_data(self, sheet_url: str) -> List[List[str]]:
        """Read data from a Google Sheet.
        
        This is a wrapper around read_sheet that provides better error handling.
        """
        try:
            return self.read_sheet(sheet_url)
        except Exception as e:
            logger.error(f"Error reading sheet data: {str(e)}")
            raise ValueError(f"Error reading sheet data: {str(e)}")
    
    def read_sheet(self, sheet_url: str) -> List[List[str]]:
        """Read data from a Google Sheet."""
        try:
            # Open the spreadsheet
            logger.info(f"Opening spreadsheet: {sheet_url}")
            sheet = self.client.open_by_url(sheet_url)
            # Get the first worksheet
            worksheet = sheet.get_worksheet(0)
            # Get all values
            values = worksheet.get_all_values()
            logger.info(f"Read {len(values)} rows from sheet")
            return values
        except Exception as e:
            logger.error(f"Error reading Google Sheet: {str(e)}")
            raise ValueError(f"Error reading Google Sheet: {str(e)}")
    
    def write_results_to_sheet(self, sheet_url: str, results: List[Dict[str, Any]]) -> str:
        """Write verification results to a new sheet."""
        try:
            # Open the spreadsheet
            logger.info(f"Opening spreadsheet for writing: {sheet_url}")
            sheet = self.client.open_by_url(sheet_url)
            
            # Create a new worksheet for results
            result_sheet_title = f"Results_{sheet.title}"
            try:
                # Try to get the sheet if it exists
                result_sheet = sheet.worksheet(result_sheet_title)
                # Clear existing content
                result_sheet.clear()
                logger.info(f"Cleared existing result sheet: {result_sheet_title}")
            except gspread.exceptions.WorksheetNotFound:
                # Create a new sheet if it doesn't exist
                result_sheet = sheet.add_worksheet(title=result_sheet_title, rows="1000", cols="20")
                logger.info(f"Created new result sheet: {result_sheet_title}")
            
            # Prepare headers
            headers = ["First Name", "Last Name", "Domain", "Valid Email", "Status"]
            
            # Prepare data rows
            rows = [headers]
            for result in results:
                rows.append([
                    result.get('first_name', ''),
                    result.get('last_name', ''),
                    result.get('domain', ''),
                    result.get('valid_email', ''),
                    result.get('status', '')
                ])
            
            # Update the sheet
            result_sheet.update(rows)
            logger.info(f"Updated result sheet with {len(results)} results")
            
            return f"Results written to sheet: {result_sheet_title}"
        except Exception as e:
            logger.error(f"Error writing to Google Sheet: {str(e)}")
            return f"Error writing to Google Sheet: {str(e)}"
    
    def parse_input_sheet(self, data: List[List[str]]) -> List[Tuple[str, str, str]]:
        """Parse input sheet data into a list of (first_name, last_name, domain) tuples."""
        results = []
        
        # Skip header row if it exists
        start_row = 1 if len(data) > 0 and any(h.lower() in ['имя', 'фамилия', 'домен', 'name', 'first', 'last', 'domain'] 
                                              for h in data[0]) else 0
        
        logger.info(f"Parsing input sheet data, starting from row {start_row+1}")
        
        for row in data[start_row:]:
            if len(row) >= 3 and all(row[:3]):  # Ensure we have first name, last name, and domain
                first_name = row[0].strip()
                last_name = row[1].strip()
                domain = row[2].strip()
                
                # Clean domain (remove http://, https://, www. and trailing slashes)
                domain = domain.lower()
                domain = re.sub(r'^https?://', '', domain)
                domain = re.sub(r'^www\.', '', domain)
                domain = domain.split('/')[0]  # Remove paths
                
                results.append((first_name, last_name, domain))
        
        logger.info(f"Parsed {len(results)} name entries from sheet")
        return results 