from __future__ import print_function
import os
import logging
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm
import io

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Update scopes to include read and write permissions
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/drive.file']

class GoogleAPI:
    def __init__(self, service_name, version, credentials_path='credentials.json', token_path='token.json', scopes=SCOPES):
        self.service_name = service_name
        self.version = version
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.scopes = scopes
        self.creds = self.authenticate()

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logging.error("Failed to refresh credentials: %s" % e)
                    creds = self.prompt_for_new_credentials()
            else:
                creds = self.prompt_for_new_credentials()
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        return creds

    def prompt_for_new_credentials(self):
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.scopes)
        creds = flow.run_local_server(port=0)
        return creds

    def get_service(self):
        return build(self.service_name, self.version, credentials=self.creds)

class GoogleDriveAPI(GoogleAPI):
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        super().__init__('drive', 'v3', credentials_path, token_path, SCOPES)

    def list_files(self, page_size=100):
        service = self.get_service()
        results = service.files().list(
            pageSize=page_size, fields="nextPageToken, files(id, name, mimeType)").execute()
        items = results.get('files', [])

        if not items:
            logging.info('No files found.')
        else:
            logging.info('Files:')
            for item in items:
                logging.info('{0} ({1}) [{2}]'.format(item['name'], item['id'], item['mimeType']))
            return items

    def download_file(self, file_type, file_name):
        if not file_type or not file_name:
            raise ValueError("Both file_type and file_name must be provided.")
        
        mime_type_prefix = self.get_mime_type_prefix(file_type)
        
        files = self.list_files(100)  # Increase page_size to search more files
        for file in files:
            if file_name.lower() in file['name'].lower() and file['mimeType'].startswith(mime_type_prefix):
                self.download_file_by_id(file['id'], file['name'], file['mimeType'])
                return
        logging.info('No matching files found.')

    def get_mime_type_prefix(self, file_type):
        file_type_map = {
            'image': 'image/',
            'pdf': 'application/pdf',
            'text': 'text/plain',
            'video': 'video/'
        }
        if file_type in file_type_map:
            return file_type_map[file_type]
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def download_file_by_id(self, file_id, file_name, mime_type):
        service = self.get_service()
        try:
            if mime_type.startswith('application/vnd.google-apps.'):
                # Export Google Docs Editors files to a suitable format
                request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
                file_name += '.pdf'
            else:
                # Download binary content directly
                request = service.files().get_media(fileId=file_id)

            # Create 'media' folder if it doesn't exist
            if not os.path.exists('media'):
                os.makedirs('media')

            print(f"Starting download for file: {file_name}")
            file_path = os.path.join('media', file_name)
            fh = io.FileIO(file_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            # Use tqdm to show the download progress
            with tqdm(total=None, unit='B', unit_scale=True, desc=file_name) as pbar:
                while not done:
                    status, done = downloader.next_chunk()
                    pbar.update(status.resumable_progress - pbar.n)

            fh.close()
            download_path = os.path.abspath(file_path)
            logging.info("Download completed for file: %s" % file_name)
            logging.info("File downloaded to: %s" % download_path)
        except Exception as e:
            logging.error("Error downloading file: %s" % e)

if __name__ == '__main__':
    drive_api = GoogleDriveAPI()
    file_type = 'image'  # Replace with the file type you want to download
    file_name = 'small-step-ladder.webp'  # Replace with the name of the file you want to download
    drive_api.download_file(file_type, file_name)
