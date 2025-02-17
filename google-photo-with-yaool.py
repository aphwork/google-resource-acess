from __future__ import print_function
import os
import logging
import time
import aiohttp
import asyncio
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from tqdm import tqdm
from pymongo import MongoClient

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Update scopes to include Google Photos API access
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']

# Replace 'credentials.json' with your specified path
CRED_JSON = './creds/credentials_yaool_syncapp.json'
TOKEN_JSON = './token.json'


class GoogleAPI:
    def __init__(self, service_name, version, credentials_path=CRED_JSON, token_path=TOKEN_JSON, scopes=SCOPES):
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
        creds = flow.run_local_server(port=8080)
        return creds

    def get_service(self):
        return build(self.service_name, self.version, credentials=self.creds, static_discovery=False)


class GooglePhotosAPI(GoogleAPI):
    def __init__(self, mongo_uri, credentials_path=CRED_JSON, token_path=TOKEN_JSON):
        super().__init__('photoslibrary', 'v1', credentials_path, token_path, SCOPES)
        self.service = self.get_service()
        self.mongo_client = MongoClient(mongo_uri)
        self.mongo_db = self.mongo_client['photos_db']
        self.mongo_collection = self.mongo_db['media_items']

    def list_albums(self):
        albums = []
        next_page_token = None
        while True:
            try:
                results = self.service.albums().list(pageSize=50, pageToken=next_page_token).execute()
                albums.extend(results.get('albums', []))
                next_page_token = results.get('nextPageToken')
                if not next_page_token:
                    break
            except Exception as e:
                logging.error(f"Failed to list albums: {e}")
                break
        return albums

    def list_photos_in_album(self, album_id):
        photos = []
        next_page_token = None
        while True:
            try:
                results = self.service.mediaItems().search(body={"albumId": album_id, "pageSize": 100, "pageToken": next_page_token}).execute()
                photos.extend(results.get('mediaItems', []))
                next_page_token = results.get('nextPageToken')
                if not next_page_token:
                    break
            except Exception as e:
                logging.error(f"Failed to list photos in album {album_id}: {e}")
                break
        return photos

    def list_all_photos(self):
        photos = []
        next_page_token = None
        while True:
            try:
                results = self.service.mediaItems().list(pageSize=100, pageToken=next_page_token).execute()
                photos.extend(results.get('mediaItems', []))
                next_page_token = results.get('nextPageToken')
                if not next_page_token:
                    break
            except Exception as e:
                logging.error(f"Failed to list all photos: {e}")
                break
        return photos

    async def download_media_item(self, session, media_item, folder_name, retries=3, delay=5):
        url = media_item['baseUrl'] + '=d'
        file_name = media_item['filename']
        media_id = media_item['id']
        media_version = media_item['mediaMetadata']['creationTime']
        folder_dir = os.path.join('downloads', folder_name)

        if not os.path.exists(folder_dir):
            os.makedirs(folder_dir)

        file_path = os.path.join(folder_dir, file_name)

        # Check if file already exists in the MongoDB database
        result = self.mongo_collection.find_one({"id": media_id})
        if result and result['version'] == media_version:
            logging.info(f"File already exists and is up-to-date in MongoDB: {file_path}")
            return

        for attempt in range(retries):
            try:
                async with session.get(url) as response:
                    total_size = int(response.headers.get('content-length', 0))
                    block_size = 1024
                    t = tqdm(total=total_size, unit='B', unit_scale=True, desc=file_name)

                    with open(file_path, 'wb') as f:
                        async for data in response.content.iter_chunked(block_size):
                            t.update(len(data))
                            f.write(data)
                    t.close()

                    # Get the downloaded file size
                    file_size = os.path.getsize(file_path)

                    # Update the MongoDB database with the new media item
                    self.mongo_collection.update_one(
                        {"id": media_id},
                        {"$set": {"filename": file_name, "version": media_version, "size": file_size}},
                        upsert=True
                    )

                    logging.info(f"Downloaded {file_name} to {file_path} with size {file_size} bytes")
                    return

            except Exception as e:
                logging.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logging.error(f"Failed to download media item {media_item['id']} after {retries} attempts")

    async def download_all_albums_and_photos(self):
        async with aiohttp.ClientSession() as session:
            # Download all albums
            albums = self.list_albums()
            if not albums:
                logging.info("No albums found.")
            for album in albums:
                album_name = album['title']
                album_id = album['id']
                logging.info(f"Processing album: {album_name}")
                photos = self.list_photos_in_album(album_id)
                download_tasks = [self.download_media_item(session, media_item, f"albums/{album_name}") for media_item in photos]
                await asyncio.gather(*download_tasks)

            # Download all photos (not in albums)
            logging.info("Processing all photos")
            photos = self.list_all_photos()
            if not photos:
                logging.info("No photos found.")
            download_tasks = [self.download_media_item(session, media_item, 'all_photos') for media_item in photos]
            await asyncio.gather(*download_tasks)


if __name__ == '__main__':
    mongo_uri = 'mongodb://localhost:27017'  # Replace with your MongoDB URI
    api = GooglePhotosAPI(mongo_uri)
    asyncio.run(api.download_all_albums_and_photos())
