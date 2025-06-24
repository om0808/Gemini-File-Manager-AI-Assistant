import os
import google.generativeai as genai
import jwt
import pandas as pd
import pyodbc
from PIL import Image
import textwrap
import json
uploaded_files = {}  # Global dictionary to store uploaded files
import re
import shutil

import asyncio
from concurrent.futures import ThreadPoolExecutor

MAX_THREADS = 10  # Control the number of threads
lock = asyncio.Lock()  # Lock for thread-safe updates

def print_welcome():
    import os
    import pyfiglet
    from colorama import Fore, Style
    
    # Get the username
    username = os.getlogin()
    
    # Generate ASCII text
    ascii_art = pyfiglet.figlet_format(f"Welcome {username}")
    
    # Print in colorful style
    print(Fore.CYAN + Style.BRIGHT + ascii_art + Style.RESET_ALL)
    return username


def decode_db_creds(encoded):
    creds = jwt.decode(encoded, '', algorithms=['HS256'])
    return creds

encoded = "eyJzZXJ2ZXIiOiJtd3NjLW1lcy1kYi5kYXRhYmFzZS53aW5kb3dzLm5ldCIsImRhdGFiYXNlIjoicmVwb3J0X2xvZ2dpbmdfREIiLCJ1c2VybmFtZSI6InJlcG9ydF9sb2dnaW5nX3J3IiwicGFzc3dvcmQiOiJXclBHNGx5WGxzIn0.LsSKSLnI7dLEBm22MAWuV55Y8rxsONPwF4dlY_fADME"
creds = decode_db_creds(encoded)



def get_db_connection_and_engine(server, database, username, password, driver="{ODBC Driver 17 for SQL Server}"):
    """
    Establish a connection to the Azure SQL database using pyodbc and SQLAlchemy engine.
    Returns a pyodbc connection object and an SQLAlchemy engine.
    """
    connection_string = f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}'
    conn = pyodbc.connect(connection_string)
    return conn

conn = get_db_connection_and_engine(creds['server'], creds['database'], creds['username'], creds['password'])


# def save_to_db(prompt, output):
    
#     """Splits output into 4 parts and saves the prompt and responses to SQL Server."""
#     cursor = conn.cursor()

#     # Split text into 4 parts
#     parts = split_text(output, num_parts=4)

#     # Ensure all 4 parts exist (fill empty ones with None)
#     response1, response2, response3, response4 = (parts + [None] * 4)[:4]

#     cursor.execute(
#         """
#         INSERT INTO dbo.tAIImageResponses (prompt, response1, response2, response3, response4)
#         VALUES (?, ?, ?, ?, ?)
#         """,
#         (prompt, response1, response2, response3, response4)
#     )
#     conn.commit()

def save_to_db(prompt, output, user_name):
    """
    Saves prompt and responses to SQL Server.
    Only reconnects if the connection is closed.
    """
    global conn
    if conn is None or conn.closed:
        conn = get_db_connection_and_engine(creds['server'], creds['database'], creds['username'], creds['password'])
    cursor = conn.cursor()
    # Split text into 4 parts
    parts = split_text(output, num_parts=4)
    response1, response2, response3, response4 = (parts + [None] * 4)[:4]
    try:
        cursor.execute(
            """
            INSERT INTO dbo.tAIImageResponses (prompt, response1, response2, response3, response4, username)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (prompt, response1, response2, response3, response4, user_name)
        )
        conn.commit()
    except pyodbc.Error as e:
        print(f"Database insert error: {e}")

def check_files(file_names, directory='./'):
    """Check if the given files exist in the specified directory."""
    missing_files = []
    
    for file_name in file_names:
        file_path = os.path.join(directory, file_name)
        if not os.path.isfile(file_path):
            missing_files.append(file_name)
    
    if missing_files:
        print("Missing files:", ", ".join(missing_files))
        return False
    else:
        print("All files exist. Proceeding further...")
        return True

def split_text(text, num_parts=4):
    """Splits a large text into equal parts to fit into multiple columns."""
    text_length = len(text)
    part_size = (text_length // num_parts) + 1  # Ensure we cover all text
    return [text[i:i + part_size] for i in range(0, text_length, part_size)]

uploaded_files = {}  # Global dictionary to store uploaded files

# def upload_files_to_gemini(directory='upload_files'):
#     """Uploads all files in the 'upload_files' directory and updates the uploaded_files dictionary."""
#     global uploaded_files  

#     # Ensure the upload_files directory exists
#     if not os.path.exists(directory):
#         os.makedirs(directory)
#         print(f"Folder '{directory}' was missing and has been created. Please add files to upload.")
#         return None  

#     file_names = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

#     if not file_names:
#         print(f"No files found in '{directory}'. Please add files before uploading.")
#         return None

#     for file_name in file_names:
#         if file_name not in uploaded_files:  # Avoid re-uploading
#             var_name = f"myfile{len(uploaded_files) + 1}"
#             uploaded_files[var_name] = genai.upload_file(os.path.join(directory, file_name))
    
#     print("Updated uploaded files:", [file_info.display_name for file_info in uploaded_files.values()])
    
#     # save_uploaded_files_to_json(uploaded_files)  # Assuming this function is defined elsewhere
#     return uploaded_files



def get_prompt(uploaded_files,prompt, user_name):
    """Generates content using uploaded files and returns a pretty-formatted result."""
    file_list = list(uploaded_files.values()) + ["\n\n", prompt]
    model = genai.GenerativeModel("gemini-1.5-flash")
    result = model.generate_content(file_list)
    # save_to_db(prompt, result.text, user_name)
    
    if hasattr(result, "text"):  # Check if result has text attribute
        return textwrap.fill(result.text, width=80)  # Pretty format text output
    return "No text output from model."



def get_back_records(username):
    query = f"SELECT prompt, LEFT(response1, 4000) + LEFT(response2, 4000) + LEFT(response3, 4000) + LEFT(response4, 4000) AS response\
     FROM dbo.tAIImageResponses where username = '{username}' order by Ailogdatetime desc"
    
    # print(query)  # Debugging
    df = pd.read_sql_query(query, conn)
    return df

 

def compress_images_in_folder(input_folder, output_folder="compressed_images", quality=95):
    """
    Compress all images in a folder and save them in the output folder.
    
    Args:
        input_folder (str): Path to the folder containing images.
        output_folder (str): Path to save compressed images.
        quality (int): Quality level (1-100), higher is better quality.
    """
    if not os.path.exists(input_folder):
        print(f"Error: Input folder '{input_folder}' does not exist.")
        return
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Process each file in the folder
    for filename in os.listdir(input_folder):
        input_path = os.path.join(input_folder, filename)

        # Check if it's a file and an image
        if os.path.isfile(input_path) and filename.lower().endswith(("jpg", "jpeg", "png", "webp","bmp")):
            output_path = os.path.join(output_folder, filename)

            try:
                with Image.open(input_path) as img:
                    img = img.convert("RGB")  # Ensure it's in RGB mode
                    
                    # Detect the format and preserve it
                    format = img.format if img.format else "JPEG"
                    
                    img.save(output_path, format=format, optimize=True, quality=quality)
                    print(f"Compressed and saved: {output_path}")

            except Exception as e:
                print(f"Error processing {input_path}: {e}")
        else:
            print(f"Skipping non-image file: {filename}")



def compress_image(input_path, output_path, quality=80):
    """
    Compresses an image to reduce file size without resizing dimensions.
    
    Args:
        input_path (str): Path to the input image.
        output_path (str): Path to save the compressed image.
        quality (int): Quality level (1-100), higher is better quality.
    """
    try:
        with Image.open(input_path) as img:
            img = img.convert("RGB")  # Ensure it's in RGB mode
            
            # Detect the format and preserve it
            format = img.format  # Original format
            if format is None:
                format = "JPEG"  # Default to JPEG if format is unknown
            
            img.save(output_path, format=format, optimize=True, quality=quality)
            print(f"Compressed and saved: {output_path}")

    except Exception as e:
        print(f"Error processing {input_path}: {e}")

def compress_images(file_or_folders, quality=80):
    # Define the path to the compressed folder
    compressed_folder = "compressed_images"

    # If the folder exists, clear older files
    if os.path.exists(compressed_folder):
        for f in os.listdir(compressed_folder):
            file_path = os.path.join(compressed_folder, f)
            try:
                if os.path.isfile(file_path):  # Make sure to delete files only
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
    else:
        # If the folder doesn't exist, create it
        os.makedirs(compressed_folder, mode=0o777, exist_ok=True)

    compressed_files = []

    # Ensure file_or_folders is always a list
    if not isinstance(file_or_folders, list):
        file_or_folders = [file_or_folders]

    # Process each item in the provided list (both files and folders)
    for item in file_or_folders:
        try:
            if os.path.isdir(item):
                # If it's a directory, process all files in it
                file_list = [os.path.join(item, f) for f in os.listdir(item) if os.path.isfile(os.path.join(item, f))]
                for file in file_list:
                    file_name = os.path.basename(file)
                    output_path = os.path.join(compressed_folder, file_name)
                    compress_image(file, output_path, quality=quality)
                    compressed_files.append(output_path)
            elif os.path.isfile(item):
                # If it's a file, process it directly
                file_name = os.path.basename(item)
                output_path = os.path.join(compressed_folder, file_name)
                compress_image(item, output_path, quality=quality)
                compressed_files.append(output_path)
        except Exception as e:
            print(f"Error processing {item}: {e}")

    return compressed_files


def save_uploaded_files_to_json(uploaded_files, json_file='uploaded_files.json'):
    """Save the uploaded file details to a JSON file."""
    with open(json_file, 'w') as f:
        json.dump(uploaded_files, f, default=str, indent=4)  # Use default=str to handle non-serializable data (e.g., datetime)
    # print("Uploaded files saved to JSON file.")

def load_uploaded_files_from_json(json_file='uploaded_files.json'):
    """Load the uploaded file details from a JSON file."""
    if os.path.exists(json_file):
        with open(json_file, 'r') as f:
            return json.load(f)
    return {} 



def get_valid_files(file_names=None, folder_names=None):
    file_list = []

    # Process individual file names
    if file_names:
        for file in file_names:
            if os.path.isfile(file):
                file_list.append(file)
            else:
                print(f"File '{file}' not found.")

    # Process multiple folder names
    if folder_names:
        for folder in folder_names:
            if os.path.isdir(folder):
                folder_files = [
                    os.path.join(folder, f) for f in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, f))
                ]
                if folder_files:
                    file_list.extend(folder_files)
                else:
                    print(f"No files found in the folder '{folder}'.")
            else:
                print(f"Folder '{folder}' not found.")

    # If no valid files are found, return available files and folders in the current directory
    if not file_list:
        print("No valid files found. Available files and folders in the current directory:")
        for item in os.listdir():
            print(item)
        return []

    print("Selected files:", file_list)
    return file_list


def extract_display_name(file_string):
    """Extract display_name from the string representation of genai.File object."""
    match = re.search(r"'display_name':\s*'([^']+)'", file_string)
    return match.group(1) if match else None



def fetch_data_from_db(username):
    """
    Get the top 10 rows from dbo.tAIImageResponses as a Pandas DataFrame.
    """
    global conn
    query = """
            SELECT TOP 10 prompt, LEFT(response1, 4000) + LEFT(response2, 4000)+ LEFT(response3, 4000)+    LEFT(response4, 4000) AS response\
     FROM dbo.tAIImageResponses where username = '{username}'
            """
    # query = """
    #         SELECT TOP 10 {0}, prompt, LEFT(response1, 4000) + LEFT(response2, 4000)+ LEFT(response3, 4000)+    LEFT(response4, 4000) AS response\
    #  FROM dbo.tAIImageResponses 
    #         """.format(user_name)
    
    df = pd.read_sql_query(query,conn)
    return df

def fetch_data_from_db_and_save(username, output_file= 'user_data.xlsx'):
    """
    Get the data from dbo.tAIImageResponses as a Pandas DataFrame and saving it as a excel file
    """
    global conn
    query = f"SELECT prompt, LEFT(response1, 4000) + LEFT(response2, 4000) + LEFT(response3, 4000) + LEFT(response4, 4000) AS response\
     FROM dbo.tAIImageResponses where username = '{username}' order by Ailogdatetime desc"
    
    # print(query)  # Debugging
    df = pd.read_sql_query(query, conn)

    # Save to Excel
    df.to_excel(output_file, index=False)
    print(f"Data saved to {output_file}")
    return df

def check_uploaded_files(uploaded_files):
    loaded_files = load_uploaded_files_from_json('uploaded_files.json')
    existing_files = {extract_display_name(file_string) for file_string in loaded_files.values() if file_string}
    existing_files.discard(None)  # Remove any None values in case of extraction failure
    
    uploaded_file_names = {file.display_name for file in uploaded_files.values()}


    # Compare files
    already_present = uploaded_file_names.intersection(existing_files)
    newly_uploaded = uploaded_file_names - existing_files
    
    # Print results
    if already_present:
        print("These files were already present:", list(already_present))
    if newly_uploaded:
        print("These files are newly uploaded:", list(newly_uploaded))

def select_specific_files(user_response,list_of_files):
    selected_files = []
    if user_response in ["yes", "y"]:
        print("Available files:")
        for idx, file in enumerate(list_of_files, 1):
            print(f"{idx}. {file}")
        
        selected_indices = input("Enter the numbers of the files you want to select (comma-separated): ")
        selected_indices = [int(i.strip()) for i in selected_indices.split(",") if i.strip().isdigit()]
        
        selected_files = [list_of_files[i - 1] for i in selected_indices if 1 <= i <= len(list_of_files)]
    else:
        selected_files = list_of_files  # Keep all files if the user says no
    return selected_files

def get_files(file_names, folder_names, user_response, list_of_files ):
    # If file_names or folder_names is None, assign it an empty list
    file_names = file_names if file_names is not None else []
    folder_names = folder_names if folder_names is not None else []
    
    # Combine folder_names and file_names into a single list
    files = folder_names + file_names
    
    if user_response.lower() == 'yes':
        images = compress_images(files, quality=100)
        # images = select_specific_files(user_response,images)
    else:
        images = list_of_files

    return images

########################################################################

lock = asyncio.Lock()  # Async lock for thread-safe updates

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Folder '{directory}' was missing and has been created. Please add files to upload.")
        return False
    return True

async def upload_file_async(genai, file_path):
    """Uploads a single file and assigns a unique key to it after upload."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as pool:
        uploaded_file = await loop.run_in_executor(pool, genai.upload_file, file_path)

    async with lock:  # Ensure atomic update
        var_name = f"myfile{len(uploaded_files) + 1}"  # Generate key after upload
        uploaded_files[var_name] = uploaded_file
        print(f"Uploaded: {file_path} as {var_name}")


async def upload_files_to_gemini(directory='upload_files', genai=None):
    global uploaded_files

    # Ensure the upload directory exists
    if not ensure_directory_exists(directory):
        return None

    file_names = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if not file_names:
        print(f"No files found in '{directory}'. Please add files before uploading.")
        return None

    # Upload files asynchronously
    tasks = [upload_file_async(genai, os.path.join(directory, file_name)) for file_name in file_names]
    await asyncio.gather(*tasks)

    # After upload, create the 'archive' folder if it doesn't exist
    archive_directory = 'archive'
    if not os.path.exists(archive_directory):
        os.makedirs(archive_directory)
        print(f"Created archive directory: {archive_directory}")

    # Move files from upload_files folder to archive folder
    for file_name in file_names:
        src = os.path.join(directory, file_name)
        dst = os.path.join(archive_directory, file_name)
        shutil.move(src, dst)  # Move file to the archive folder
        print(f"Moved {file_name} to the archive folder.")

    # Locking mechanism to ensure thread safety
    async with lock:
        print("Updated uploaded files:", {k: v.display_name for k, v in uploaded_files.items()})

    return uploaded_files

def get_uploaded_files():
    files = {}
    cnt = 1
    for file in genai.list_files():
        if file :
            files['file'+str(cnt)] = file
            cnt += 1
    return files

def check_files():
    files = list(genai.list_files())
    print("Available files :",len(files))
    return files

def check_and_store_api_key(file_path = "api_key.txt"):
    if not os.path.exists(file_path):
        api_key = input("Enter your API key: ")
        with open(file_path, "w") as file:
            file.write(api_key)
        print("API key saved successfully.")
    else:
        with open(file_path, "r") as file:
            api_key = file.read().strip()
        print("API key file already exists.")

    return api_key

def get_file_names():
    files= [i.display_name for i in genai.list_files()]
    print('Available files on Gemini :',files)

def delete_files_by_names(display_names):
    # Split the input string into a list of filenames
    file_names = [name.strip() for name in display_names.split(",")]

    # Get all files
    files = genai.list_files()

    # Track not found files
    not_found_files = []

    for name in file_names:
        matched_files = [file for file in files if file.display_name == name]

        if not matched_files:
            not_found_files.append(name)
            continue

        for file in matched_files:
            file.delete()
            print(f"Deleted file: {file.display_name}")

    # Summary message
    if not_found_files:
        print(f"Files not found: {', '.join(not_found_files)}")