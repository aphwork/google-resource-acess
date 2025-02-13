from __future__ import print_function
import os
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Update scopes to include Google Photos API access
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']

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
        return build(self.service_name, self.version, credentials=self.creds, static_discovery=False)

class GooglePhotosAPI(GoogleAPI):
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        super().__init__('photoslibrary', 'v1', credentials_path, token_path, SCOPES)
        self.service = self.get_service()

    def list_albums(self):
        albums = []
        next_page_token = None
        while True:
            results = self.service.albums().list(pageSize=50, pageToken=next_page_token).execute()
            albums.extend(results.get('albums', []))
            next_page_token = results.get('nextPageToken')
            if not next_page_token:
                break
        return albums

    def list_photos_in_album(self, album_id):
        photos = []
        next_page_token = None
        while True:
            results = self.service.mediaItems().search(body={"albumId": album_id, "pageSize": 100, "pageToken": next_page_token}).execute()
            photos.extend(results.get('mediaItems', []))
            next_page_token = results.get('nextPageToken')
            if not next_page_token:
                break
        return photos

    def download_photo(self, photo, album_name):
        url = photo['baseUrl'] + '=d'
        file_name = photo['filename']
        album_dir = os.path.join('downloads', album_name)

        if not os.path.exists(album_dir):
            os.makedirs(album_dir)

        file_path = os.path.join(album_dir, file_name)
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        t = tqdm(total=total_size, unit='B', unit_scale=True, desc=file_name)
        
        with open(file_path, 'wb') as f:
            for data in response.iter_content(block_size):
                t.update(len(data))
                f.write(data)
        t.close()
        logging.info(f"Downloaded {file_name} to {file_path}")

if __name__ == '__main__':
    api = GooglePhotosAPI()
    albums = api.list_albums()
    logging.info('Found Albums: {0}'.format(albums))

    for album in albums:
        album_name = album['title']
        logging.info(f"Processing album: {album_name}")
        photos = api.list_photos_in_album(album['id'])
        logging.info('Found Photos: {0}'.format(photos))
        for photo in photos:
            api.download_photo(photo, album_name)
