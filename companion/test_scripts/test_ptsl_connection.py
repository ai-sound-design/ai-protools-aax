"""
PTSL Connection Test Script
============================

This script performs a basic TCP connection test to verify that the Pro Tools Scripting Library
(PTSL) server is running and accessible on the local machine.

PTSL Background:
- PTSL is Pro Tools' built-in automation server for remote control and scripting
- It runs as a gRPC service on localhost:31416 (default port)
- Must be explicitly enabled in Pro Tools preferences (Setup > Preferences > MIDI)
- Allows external applications to control Pro Tools (import audio, create tracks, etc.)

Purpose:
This is a lightweight connectivity check that doesn't require the full gRPC/Protobuf setup.
It simply verifies that:
1. Pro Tools is running
2. PTSL is enabled in preferences
3. The PTSL server port (31416) is accessible
4. No firewall is blocking the connection

Usage:
    python test_ptsl_connection.py              # Test localhost:31416
    python test_ptsl_connection.py --port 9001  # Test custom port
    
Exit Codes:
    0 - Success: PTSL server is accessible
    1 - Failure: Cannot connect to PTSL server

"""

import socket
import sys
from pathlib import Path

# Add parent directory (companion/) to Python path
companion_dir = Path(__file__).parent.parent
sys.path.insert(0, str(companion_dir))

def test_ptsl_connection(host='localhost', port=31416, timeout=2):
    """
    Test if Pro Tools PTSL server is accessible via TCP connection.
    
    This performs a simple socket connection test without sending any data.
    It's equivalent to checking if a web server is running before making HTTP requests.
    
    How it works:
    1. Creates a TCP socket
    2. Attempts to connect to the PTSL server port
    3. Closes the connection immediately
    4. Returns success/failure based on connection result
    
    Args:
        host (str): PTSL server hostname or IP address (default: 'localhost')
                   For local Pro Tools instances, this should always be 'localhost'
        port (int): PTSL server TCP port (default: 31416)
                   Pro Tools PTSL uses port 31416 by default (not configurable)
        timeout (float): Connection timeout in seconds (default: 2)
                        How long to wait before giving up on the connection
        
    Returns:
        bool: True if PTSL server accepts connections, False otherwise
        
    Example:
        >>> test_ptsl_connection()
        Testing PTSL connection to localhost:31416...
        ✅ PTSL server is running on localhost:31416
        True
    """
    print(f"Testing PTSL connection to {host}:{port}...")
    
    try:
        # Create a TCP socket (AF_INET = IPv4, SOCK_STREAM = TCP)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Set timeout to avoid hanging indefinitely if server is unresponsive
        sock.settimeout(timeout)
        
        # Attempt connection (connect_ex returns 0 on success, error code otherwise)
        # Unlike connect(), connect_ex doesn't raise exceptions - returns error code instead
        result = sock.connect_ex((host, port))
        
        # Always close the socket to free up system resources
        sock.close()
        
        # Check connection result
        if result == 0:
            # Success! Server is accepting connections
            print(f"✅ PTSL server is running on {host}:{port}")
            print("\nPro Tools is ready for scripting!")
            return True
        else:
            # Connection failed - server not running or port blocked
            print(f"❌ Cannot connect to PTSL server on {host}:{port}")
            print(f"   Error code: {result}")
            print(f"   (Common codes: 10061=Connection refused, 10060=Timeout)")
            return False
            
    except socket.gaierror as e:
        # DNS/hostname resolution failed (e.g., invalid hostname)
        print(f"❌ Hostname resolution failed: {e}")
        print(f"   Check that '{host}' is a valid hostname or IP address")
        return False
    except socket.timeout:
        # Connection timed out - server not responding within timeout period
        print(f"❌ Connection timeout - PTSL server not responding")
        print(f"   Server may be starting up, overloaded, or blocked by firewall")
        return False
    except Exception as e:
        # Catch-all for unexpected errors (permission issues, network down, etc.)
        print(f"❌ Connection test failed: {e}")
        return False


def print_ptsl_setup_instructions():
    """
    Display step-by-step instructions for enabling PTSL in Pro Tools.
    
    PTSL must be manually enabled in Pro Tools preferences as a security measure.
    This function provides clear setup instructions when the connection test fails.
    
    PTSL Setup Requirements:
    - Pro Tools 2019.5 or later (PTSL introduced in 2019.5)
    - A Pro Tools session must be open (PTSL only runs when session is active)
    - PTSL preference must be enabled (disabled by default)
    - Port 31416 must not be blocked by firewall
    
    Common Issues:
    - Firewall blocking: Windows Defender or antivirus may block Pro Tools network access
    - PTSL not enabled: Easy to miss the checkbox in MIDI preferences
    - No session open: PTSL server only starts when a session is open
    - Port conflict: Another application using port 31416 (rare)
    """
    print("\n" + "="*60)
    print("HOW TO ENABLE PTSL IN PRO TOOLS")
    print("="*60)
    print("\n📋 Step-by-Step Setup:")
    print("\n1. Open Pro Tools (2019.5 or later required)")
    print("2. Create or open a Pro Tools session")
    print("   ⚠️  PTSL only runs when a session is open!")
    print("\n3. Go to: Setup > Preferences > MIDI")
    print("4. Check: ☑ Enable PTSL (Pro Tools Scripting Library)")
    print("5. Click OK to save preferences")
    print("6. Restart Pro Tools if PTSL doesn't start immediately")
    print("\n🔥 Firewall Configuration:")
    print("   - Allow Pro Tools through Windows Firewall")
    print("   - Ensure port 31416 (TCP) is not blocked")
    print("   - Check antivirus software for network restrictions")
    print("\n🔍 Verification:")
    print("   - Run this script again to test connection")
    print("   - Check Pro Tools > Setup > Preferences > MIDI")
    print("   - Verify PTSL checkbox is enabled")
    print("\n" + "="*60)


if __name__ == "__main__":
    """
    Main entry point when script is run directly.
    
    Parses command-line arguments and performs the PTSL connection test.
    Exits with appropriate status codes for shell script integration.
    """
    import argparse
    
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Test Pro Tools Scripting Library (PTSL) connectivity",
        epilog="""
Examples:
  python test_ptsl_connection.py                    # Test default localhost:31416
  python test_ptsl_connection.py --port 9001        # Test custom port
  python test_ptsl_connection.py --host 192.168.1.5 # Test remote Pro Tools instance
        """
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="PTSL server hostname or IP address (default: localhost). "
             "Use 'localhost' for local Pro Tools instances."
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=31416,
        help="PTSL server TCP port (default: 31416). "
             "Pro Tools uses 31416 by default and this is not configurable."
    )
    
    # Parse command-line arguments
    args = parser.parse_args()
    
    # Run the connection test
    success = test_ptsl_connection(args.host, args.port)
    
    # Handle test results
    if not success:
        # Connection failed - show setup instructions and exit with error code
        print_ptsl_setup_instructions()
        sys.exit(1)  # Exit code 1 = failure (standard Unix convention)
    else:
        # Connection successful - ready to proceed
        print("\n✅ All checks passed!")
        print("You can proceed with PTSL integration.")
        print("\nNext steps:")
        print("  - Test full PTSL integration: python ptsl_integration/test_integration.py")
        print("  - Import audio to Pro Tools: Use ptsl_client.import_audio_to_timeline()")
        sys.exit(0)  # Exit code 0 = success (standard Unix convention)
