# Russian Email Finder

A web application that helps find and verify corporate email addresses for Russian names. The application can:

1. Transcribe Russian names into Latin alphabet
2. Generate multiple email variations based on names and company domains
3. Verify email addresses for validity
4. Process data from and output results to Google Sheets

## Features

- **Russian Name Transcription**: Properly converts Cyrillic characters to Latin
- **Email Pattern Generation**: Creates 5-10 most common email patterns for corporate emails
- **Email Verification**: Checks if emails exist using SMTP and DNS verification
- **Special Handling for Russian Email Providers**: Enhanced verification for Yandex, Mail.ru, and other Russian email services
- **Google Sheets Integration**: Process lists of names directly from Google Sheets and output results back
- **Manual Entry Option**: Test individual names without using Google Sheets

## Setup

### Prerequisites

- Python 3.7+
- Google API credentials (for Google Sheets integration)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/russian-email-finder.git
   cd russian-email-finder
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure environment variables (required):
   - Copy `.env.example` to `.env`
   - Edit `.env` to set your Google Sheets API credentials by pasting your entire JSON credentials string
   ```
   cp .env.example .env
   nano .env  # or use any text editor
   ```

5. For Google Sheets integration, you need to:
   - Create a Google Cloud project
   - Enable the Google Sheets API
   - Create a service account
   - Download the JSON credentials file
   - Copy the entire JSON content and paste it into your `.env` file as the value for `GOOGLE_APPLICATION_CREDENTIALS`

### Running the Application

Start the Flask application:
```
python app.py
```

The application will be available at `http://127.0.0.1:5000/`.

## Usage

### Google Sheets Integration

1. Prepare a Google Sheet with three columns:
   - First Name (in Russian)
   - Last Name (in Russian)
   - Company Domain (e.g., company.com)

2. Share your Google Sheet with the email address from your service account credentials

3. On the application homepage, enter the Google Sheet URL

4. Click "Process Sheet" and then "Start Processing"

5. The application will create a new tab in your Google Sheet with the verified email addresses

### Manual Entry

1. Click "Manual Entry" on the homepage

2. Enter a first name, last name (both in Russian), and company domain

3. Click "Generate & Verify Emails"

4. View the results showing which email variations are valid

## How It Works

1. **Name Transcription**: Uses the `transliterate` library to convert Russian names to Latin alphabet

2. **Email Generation**: Creates common email patterns like:
   - firstname@domain.com
   - lastname@domain.com
   - firstname.lastname@domain.com
   - f.lastname@domain.com
   - etc.

3. **Email Verification**:
   - Checks email syntax
   - Verifies domain MX records
   - Uses SMTP verification when possible
   - Applies special rules for Russian email providers

4. **Results Processing**:
   - Filters for valid emails only
   - For each name, returns the most likely valid email address

## License

MIT 