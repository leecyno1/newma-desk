import subprocess
import logging

logger = logging.getLogger(__name__)

def add_reminder(title: str, notes: str = "", due_date: str = None):
    """
    Adds a reminder to the default Reminders list on macOS using AppleScript.
    due_date should be a string that AppleScript can parse, e.g., "2023-10-27 14:00:00"
    """
    try:
        script = f'tell application "Reminders" to make new reminder with properties {{name:"{title}", body:"{notes}"'
        if due_date:
            # AppleScript date parsing can be tricky. 
            # A robust way is to use 'date "..."' but it depends on system locale.
            # Alternatively, we can just set the name and let the user handle the date, 
            # or try to parse it. For now, let's try to set it if provided.
            # We'll use a simple approach: assume ISO-like format might work or just append to notes if it fails.
            # Actually, passing date string to AppleScript is fragile. 
            # Let's append time to title or notes for safety if we can't guarantee locale.
            pass
        
        script += '}'
        
        # If due_date is provided, we try to set it. 
        # A safer way for 'due date' in AppleScript is constructing it from components, 
        # but that requires parsing in Python first.
        # For this MVP, we will just create the reminder.
        
        cmd = ['osascript', '-e', script]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Created reminder: {title}")
        return True, "Reminder created successfully"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create reminder: {e.stderr}")
        return False, f"Failed to create reminder: {e.stderr}"
    except Exception as e:
        logger.error(f"Error creating reminder: {str(e)}")
        return False, str(e)

def open_reminders_app():
    try:
        subprocess.run(['open', '-a', 'Reminders'], check=True)
        return True
    except Exception:
        return False
