"""
Centralized error handling for all API client scripts

Ensures consistent JSON error responses across:
- standalone_api_client.py (MMAudio)
- hunyuanvideo_foley_api_client.py (HunyuanVideo-Foley)
- sound_search_api_client.py (Sound Search)
"""

import json
import sys
import traceback
from typing import Callable, Any, Dict


def safe_action_wrapper(action_func: Callable[[], Any]) -> int:
    """
    Wrap an action function to always return JSON, even on exception.
    
    This ensures the C++ plugin always gets valid JSON to parse, instead of
    raw Python exceptions that cause "Failed to parse Python response" errors.
    
    Args:
        action_func: Function that executes the action (should return dict or None)
    
    Returns:
        int: Exit code (0 = success, 1 = error)
    
    Usage:
        def my_action():
            result = some_operation()
            return {"success": True, "data": result}
        
        exit_code = safe_action_wrapper(my_action)
    
    Exception Handling:
        - FileNotFoundError → {"success": false, "error": "File not found: ..."}
        - ValueError → {"success": false, "error": "Invalid value: ..."}
        - All others → {"success": false, "error": "..."}
    
    Output:
        - stdout: JSON only (for C++ parsing)
        - stderr: Debug info + full traceback (for python_stderr.log)
    """
    try:
        result = action_func()
        
        # Handle None result (action with no return value)
        if result is None:
            result = {"success": True}
        
        # Ensure result is a dict
        if not isinstance(result, dict):
            result = {"success": True, "data": result}
        
        # Print JSON to stdout (C++ plugin reads this)
        print(json.dumps(result))
        sys.stdout.flush()
        
        # Determine exit code
        # Check for 'success' key (our standard), 'valid' key (validation), or 'status' (sound search)
        if 'success' in result:
            return 0 if result['success'] else 1
        elif 'valid' in result:
            return 0 if result['valid'] else 1
        elif 'status' in result:
            return 0 if result['status'] == 'success' else 1
        else:
            # No known status field - assume success
            return 0
    
    except FileNotFoundError as e:
        error_result = {
            "success": False,
            "error": f"File not found: {e}"
        }
        print(json.dumps(error_result))
        sys.stdout.flush()
        
        print(f"ERROR [FileNotFoundError]: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    
    except ValueError as e:
        error_result = {
            "success": False,
            "error": f"Invalid value: {e}"
        }
        print(json.dumps(error_result))
        sys.stdout.flush()
        
        print(f"ERROR [ValueError]: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    
    except KeyboardInterrupt:
        error_result = {
            "success": False,
            "error": "Operation cancelled by user"
        }
        print(json.dumps(error_result))
        sys.stdout.flush()
        
        print("ERROR: Operation cancelled by user", file=sys.stderr)
        return 1
    
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e)
        }
        print(json.dumps(error_result))
        sys.stdout.flush()
        
        print(f"ERROR [Unexpected]: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


def wrap_main_with_json_error_handling(main_func: Callable[[], int]) -> int:
    """
    Wrap entire main() function to catch any unhandled exceptions.
    
    Use this as final safety net in __main__ block:
    
        if __name__ == "__main__":
            sys.exit(wrap_main_with_json_error_handling(main))
    
    Args:
        main_func: The main() function to wrap
    
    Returns:
        int: Exit code
    """
    try:
        return main_func()
    except Exception as e:
        # Last resort - even main() crashed
        error_result = {
            "success": False,
            "error": f"Fatal error: {e}"
        }
        print(json.dumps(error_result))
        sys.stdout.flush()
        
        print(f"FATAL ERROR in main(): {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
