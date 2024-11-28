import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

import os

# Get the current working directory
current_directory = os.getcwd()
print(f"Current Directory: {current_directory}")

# google api key: AIzaSyAq56c8QJy51fjxFQmOXL6WpbUu1esmyuM

# Path to your credentials.json file
CREDENTIALS_FILE = os.path.join(current_directory,'creds', 'credentials.json')
print('CREDENTIAL FILE: {0}'.format(CREDENTIALS_FILE))

# Scopes required by the API
SCOPES = ['https://www.googleapis.com/auth/drive']

# Authenticate and create the service
credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)

# Function to list files
def list_drive_files():
    results = service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name)").execute()
    print('Files - {0}'.format(results))
    items = results.get('files', [])

    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            print(f'{item["name"]} ({item["id"]})')

# Call the function
list_drive_files()
