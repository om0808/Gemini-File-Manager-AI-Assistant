from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os
from googleapiclient.errors import HttpError
import re
from difflib import get_close_matches
from PIL import Image  # Ensure you have PIL installed: pip install pillow
import io

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'red-seeker-437615-h1-a5b444aad816.json'
LOCAL_DOWNLOAD_FOLDER = "upload_files"  # Updated to use 'drive_files' as the local folder

def get_user_input():
    """Ask user what they want to download (files, folders, URLs) and return the structured input."""
    while True:
        file_names = input("Enter file names (comma-separated) or press Enter to skip: ").strip()
        folder_names = input("Enter folder names (comma-separated) or press Enter to skip: ").strip()
        file_urls = input("Enter Google Drive URLs (comma-separated) or press Enter to skip: ").strip()
        gemini_prompt = input("Do you want to pass a prompt on files already uploaded to Gemini? (yes/no): ").strip().lower()
    
        # Convert comma-separated input into lists
        file_names = [name.strip() for name in file_names.split(",") if name] if file_names else None
        folder_names = [name.strip() for name in folder_names.split(",") if name] if folder_names else None
        file_urls = [url.strip() for url in file_urls.split(",") if url] if file_urls else None

        if file_names or folder_names or file_urls or gemini_prompt in ['yes', 'no']:
            break
        else:
            print("You must enter at least one file, folder, URL or please enter 'yes' or 'no'.")

    return file_names, folder_names, file_urls, gemini_prompt


def authenticate_drive():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def download_file(service, file_id, file_name, local_folder):
    request = service.files().get_media(fileId=file_id)
    file_path = os.path.join(local_folder, file_name)
    
    os.makedirs(local_folder, exist_ok=True)  # Ensure the local folder exists
    
    with open(file_path, 'wb') as file:
        file.write(request.execute())
    print(f"Downloaded: {file_name} -> {file_path}")

def list_files_in_folder(service, folder_id):
    files = []
    page_token = None

    while True:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=100,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        files.extend(results.get('files', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    
    return files

def list_all_folders(service):
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    folders = results.get('files', [])
    
    return folders

def get_folder_id(service, folder_name):
    folders = list_all_folders(service)
    folder_dict = {folder['name']: folder['id'] for folder in folders}
    
    if folder_name in folder_dict:
        return folder_dict[folder_name]
    
    # If exact match not found, suggest similar folders
    suggestions = get_close_matches(folder_name, folder_dict.keys(), n=5, cutoff=0.6)
    if suggestions:
        print(f"Folder '{folder_name}' not found. Did you mean: {', '.join(suggestions)}?")
    
    return None

# def extract_file_id(drive_url):
#     """Extracts file ID from a Google Drive URL."""
#     match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
#     return match.group(1) if match else None

def extract_file_id(drive_url):
    """Extracts file or folder ID from a Google Drive URL."""
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)  # For files
    if match:
        return match.group(1)

    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)  # For folders
    if match:
        return match.group(1)

    return None  # No valid ID found
    
def check_file_access(service, file_id):
    """Checks if the user has access to the file."""
    try:
        service.files().get(fileId=file_id, fields="id, name").execute()
        return True
    except HttpError as e:
        if e.resp.status == 403:
            print(f"Access denied for file ID: {file_id}. Request access from the file owner.")
        elif e.resp.status == 404:
            print(f"File not found: {file_id}. Check if the URL or file name is correct.")
        else:
            print(f"Error checking access: {e}")
        return False

def search_files(service, file_names):
    """Searches for files in Drive and returns matches or suggestions."""
    found_files = []
    available_files = {}

    # Retrieve all file names from Drive
    page_token = None
    while True:
        results = service.files().list(
            q="trashed=false",
            pageSize=100,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        for file in results.get('files', []):
            available_files[file['name']] = file['id']

        page_token = results.get('nextPageToken')
        if not page_token:
            break

    for file_name in file_names:
        if file_name in available_files:
            found_files.append({'id': available_files[file_name], 'name': file_name})
        else:
            suggestions = get_close_matches(file_name, available_files.keys(), n=5, cutoff=0.6)
            if suggestions:
                print(f"File '{file_name}' not found. Did you mean: {', '.join(suggestions)}?")

    return found_files


def download_and_process(service, file_id, file_name, local_folder, compress=False, quality=95):
    """
    Downloads an image file from Google Drive and processes it based on user preference.
    """
    request = service.files().get_media(fileId=file_id)
    file_path = os.path.join(local_folder, file_name)
    os.makedirs(local_folder, exist_ok=True)  # Ensure the local folder exists

    try:
        img_data = io.BytesIO(request.execute())  # Read image data into memory
        with Image.open(img_data) as img:
            img = img.convert("RGB")  # Ensure it's in RGB mode
            if compress:
                format = img.format if img.format else "JPEG"
                img.save(file_path, format=format, optimize=True, quality=quality)
                print(f"Compressed and stored: {file_path}")
            else:
                img.save(file_path)
                print(f"Original stored: {file_path}")
    except Exception as e:
        print(f"Error processing {file_name}: {e}")


def download_from_drive(local_folder=LOCAL_DOWNLOAD_FOLDER):
    service = authenticate_drive()
    files = []

    folder_name = input("Enter the folder name (or press Enter to skip): ").strip()
    if folder_name:
        folder_id = get_folder_id(service, folder_name)
        if folder_id:
            files.extend(list_files_in_folder(service, folder_id))
        else:
            print("Folder not found.")

    file_url = input("Enter the Google Drive file or folder URL (or press Enter to skip): ").strip()
    if file_url:
        file_id = extract_file_id(file_url)
        if file_id:
            try:
                file_info = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
                if file_info["mimeType"] == "application/vnd.google-apps.folder":
                    files.extend(list_files_in_folder(service, file_id))
                else:
                    files.append(file_info)
            except HttpError as e:
                print(f"Error accessing {file_url}: {e}")
        else:
            print("Invalid Google Drive URL.")

    if not files:
        print("No files found.")
        return

    compress_choice = input("Do you want to compress images? (yes/no): ").strip().lower()
    compress = compress_choice == 'yes'

    for file in files:
        if file['name'].lower().endswith(("jpg", "jpeg", "png", "webp", "bmp")):
            download_and_process(service, file['id'], file['name'], local_folder, compress)
        else:
            print(f"Skipping non-image file: {file['name']}")


# def download_file_and_compress(service, file_id, file_name, local_folder, quality=95):
#     """
#     Downloads an image file from Google Drive, compresses it, and saves it to the local folder.
#     """
#     request = service.files().get_media(fileId=file_id)
#     file_path = os.path.join(local_folder, file_name)
#
#     os.makedirs(local_folder, exist_ok=True)  # Ensure the local folder exists
#
#     try:
#         img_data = io.BytesIO(request.execute())  # Read image data into memory
#         with Image.open(img_data) as img:
#             img = img.convert("RGB")  # Ensure it's in RGB mode
#             format = img.format if img.format else "JPEG"
#
#             # Save the compressed image to the local folder
#             img.save(file_path, format=format, optimize=True, quality=quality)
#             print(f"Compressed and stored: {file_path}")
#
#     except Exception as e:
#         print(f"Error processing {file_name}: {e}")
#
# def download_from_drive(file_names=None, folder_names=None, file_urls=None, local_folder=LOCAL_DOWNLOAD_FOLDER):
#     service = authenticate_drive()
#     files = []
#
#     # Handle folder names
#     if folder_names:
#         for folder_name in folder_names:
#             folder_id = get_folder_id(service, folder_name)
#             if not folder_id:
#                 continue  # Skip if folder is not found
#             folder_files = list_files_in_folder(service, folder_id)
#             files.extend(folder_files)
#
#     # Handle file names
#     if file_names:
#         matched_files = search_files(service, file_names)
#         files.extend(matched_files)
#
#     # Handle file and folder URLs
#     if file_urls:
#         for url in file_urls:
#             file_id = extract_file_id(url)
#             if file_id:
#                 try:
#                     file_info = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
#                     if file_info["mimeType"] == "application/vnd.google-apps.folder":
#                         folder_files = list_files_in_folder(service, file_id)
#                         files.extend(folder_files)
#                     else:
#                         files.append(file_info)
#                 except HttpError as e:
#                     print(f"Error accessing {url}: {e}")
#             else:
#                 print(f"Invalid Google Drive URL: {url}")
#
#     if not files:
#         print("No files found.")
#         return
#
#     print("Files available for download and compression:")
#     for file in files:
#         print(file['name'])
#
#     # Download, compress, and store only compressed images
#     for file in files:
#         if file['name'].lower().endswith(("jpg", "jpeg", "png", "webp", "bmp")):
#             download_file_and_compress(service, file['id'], file['name'], local_folder)
#         else:
#             print(f"Skipping non-image file: {file['name']}")
#
