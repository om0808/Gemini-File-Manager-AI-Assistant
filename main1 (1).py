import utils_1 as u
import drive_utils as du
import pandas as pd
import warnings
import os
import google.generativeai as genai
import re
import time
import asyncio

# Configure pandas display settings
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore", category=UserWarning)

# Welcome message and API key setup
username = u.print_welcome()
api_key = u.check_and_store_api_key()



files_folder_name = "upload_files"

combined_files = {}

def main():
    global combined_files  # Ensure it's accessible in the function

    while True:
        genai.configure(api_key=api_key)
        u.check_files()


        while True:
            print("\nAvailable functionalities:")
            print("1. Upload files to Gemini")
            print("2. Delete files")
            print("3. Pass a prompt on uploaded files")
            print("4. View historical data")
            print("5. Save data for user")
            print("6. Exit program")

            choice = input("\nWhat would you like to do? (Enter 1, 2, 3, 4, 5, or 6): ").strip()

            if choice == '1':
                uploaded_files1 = {}
                uploaded_files = {}
                files = u.check_files()

                if files:
                    print(f'Uploading files from {files_folder_name}')
                    start_time = time.time()

                    async def upload():
                        global uploaded_files
                        uploaded_files = await u.upload_files_to_gemini(files_folder_name, genai)

                    asyncio.run(upload())
                    end_time = time.time()
                    print(f"Time taken to upload all files: {end_time - start_time:.2f} seconds")

                # Rename conflicting keys in uploaded_files1
                uploaded_files1 = u.get_uploaded_files() if files else {}
                uploaded_files1 = {f"{k}_1": v if k in uploaded_files else v for k, v in uploaded_files1.items()}
                combined_files = {**uploaded_files1, **uploaded_files}  # Update global variable

            elif choice == '2':
                confirmation = input("\nDo you want to delete files? (yes/no): ").strip().lower()
                files = u.check_files()
                if confirmation in ["yes", "y"]:
                    if files:
                        u.get_file_names()
                        user_input = input("Enter comma-separated file names to delete: ").strip()
                        u.delete_files_by_names(user_input)
                        print("Files deleted successfully.")
                    else:
                        print('No files present in Gemini to delete')

            elif choice == '3':
                gemini_prompt = ''
                files = u.check_files()
                if files:
                    while True:
                        gemini_prompt = input(
                            "\nDo you want to pass a prompt on files already uploaded to Gemini? (yes/no): ").strip().lower()
                        if gemini_prompt in ['yes', 'no']:
                            break
                        else:
                            print("Please enter 'yes' or 'no'.")

                if gemini_prompt == 'yes':
                    combined_files = u.get_uploaded_files()  # Fetch latest uploaded files

                if not combined_files:
                    print("No files are uploaded. Please upload files first.")
                    continue
                while True:
                    prompt = input("Enter your prompt for the uploaded files: ")
                    out = u.get_prompt(combined_files, prompt, username)
                    print(out)

                    another_prompt = input("Do you want to pass another prompt? (yes/no): ").strip().lower()
                    if another_prompt not in ['yes', 'y']:
                        break

            elif choice == '4':
                df = u.get_back_records(username)
                print(df)
            elif choice == '5':
                u.fetch_data_from_db_and_save(username)
                print("Data saved successfully.")

            elif choice == '6':
                print("Exiting program...")
                return
            else:
                print("Invalid choice. Please enter 1, 2, 3, 4, 5, or 6.")

if __name__ == "__main__":
    main()
