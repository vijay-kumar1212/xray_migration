"""
Quick test: Create folder, move test DFE-72535 into it, and add sample steps.
Run from xray_migration/ directory:  python -m Scripts.quick_test
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xray.xray_client import XrayClient


def main():
    xray = XrayClient(project_key='DFE')
    test_key = 'DFE-72535'

    # 1. Create folder "Cloud Instance Test" under Test Repository root
    print("=== Step 1: Creating folder 'Cloud Instance Test' ===")
    folder_id = xray._ensure_folder_exists('Cloud Instance Test')
    if folder_id and folder_id > 0:
        print(f"Folder created/found with ID: {folder_id}")
    else:
        print(f"Folder creation result: {folder_id} (may need GraphQL for Cloud)")

    # 2. Move test case to the folder
    print(f"\n=== Step 2: Moving {test_key} to folder 'Cloud Instance Test' ===")
    xray._move_test_to_folder(test_key, '/Cloud Instance Test')
    print("Move attempted (check logs for result)")

    # 3. Add sample test steps
    print(f"\n=== Step 3: Adding test steps to {test_key} ===")
    steps = [
        {'content': 'Navigate to the login page', 'expected': 'Login page is displayed with username and password fields'},
        {'content': 'Enter valid username and password', 'expected': 'Credentials are accepted'},
        {'content': 'Click the Login button', 'expected': 'User is redirected to the dashboard'},
        {'content': 'Verify the dashboard elements', 'expected': 'Dashboard shows welcome message and navigation menu'},
    ]
    result = xray.add_steps_to_the_test_case(test_key, steps=steps)
    print(f"Steps added: {'Success' if result else 'Failed'}")


if __name__ == '__main__':
    main()
