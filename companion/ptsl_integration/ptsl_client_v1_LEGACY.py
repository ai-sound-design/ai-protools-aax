"""
⚠️ LEGACY FILE - For reference only ⚠️
=====================================

This is the original custom PTSL implementation (v1).
It has been replaced by ptsl_client_v2.py which uses the py-ptsl library.

DO NOT USE THIS FILE IN NEW CODE!

Kept for:
- Historical reference
- Documentation of PTSL protocol details
- Fallback in case of py-ptsl issues

Migration Status:
- ✅ Replaced by: ptsl_client_v2.py
- ✅ Date archived: 2025-10-31
- ✅ Reason: Switched to professional py-ptsl library
- ✅ Code reduction: 866 lines → 189 lines (78% less)

For current implementation, see:
- ptsl_client_v2.py (py-ptsl based)
- MIGRATION_TO_PY_PTSL.md (migration guide)

=====================================

ORIGINAL DOCUMENTATION BELOW:
"""
"""
PTSL (Pro Tools Scripting Library) Python Client
=================================================

This module provides a high-level Python interface for communicating with Pro Tools
via its Scripting Library (PTSL) using gRPC.

PTSL Background:
- PTSL is Avid's official API for remote control and automation of Pro Tools
- Runs as a gRPC server on localhost:31416 when enabled in Pro Tools preferences
- Requires Pro Tools 2019.5 or later
- Must be explicitly enabled: Setup > Preferences > MIDI > Enable PTSL
- Only active when a Pro Tools session is open

Core Functionality:
- Connect/authenticate with Pro Tools instance
- Import audio files to timeline (automatically creates tracks)
- Query session information (name, track list, etc.)
- Convert FLAC to WAV automatically (PTSL requires WAV format)

Communication Protocol:
- Uses Protocol Buffers (protobuf) for message serialization
- gRPC for remote procedure calls
- JSON-based request/response bodies (within protobuf wrappers)
- Session-based authentication (session_id from RegisterConnection)

Dependencies:
- grpcio: Python gRPC implementation
- protobuf: Protocol Buffers runtime
- PTSL_pb2.py: Generated protobuf message classes (from PTSL.proto)
- PTSL_pb2_grpc.py: Generated gRPC service stubs (from PTSL.proto)
- soundfile: Audio format conversion (FLAC → WAV)

Usage Example:
    >>> client = PTSLClient()
    >>> if client.connect():
    >>>     client.import_audio_to_timeline("C:/audio/generated.flac")
    >>>     client.disconnect()

"""

import grpc
import time
from pathlib import Path
from typing import Optional
import sys

# Import generated protobuf files
# These are generated from PTSL.proto using: python -m grpc_tools.protoc
# If import fails,  see setup_ptsl_env.txt to generate them
try:
    import PTSL_pb2           # Message definitions (Request, Response, Enums, etc.)
    import PTSL_pb2_grpc      # gRPC service stubs (PTSLStub.SendGrpcRequest)
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    print("Warning: PTSL protobuf files not found. Run setup.ps1 first.", file=sys.stderr)
    print("Expected files: PTSL_pb2.py, PTSL_pb2_grpc.py", file=sys.stderr)

class PTSLClient:
    """
    High-level client for Pro Tools Scripting Library (PTSL) gRPC API.
    
    This class manages the connection lifecycle and provides methods for common
    Pro Tools automation tasks like importing audio files to the timeline.
    
    Connection Flow:
        1. __init__() - Create client instance
        2. connect() - Establish gRPC channel and register with Pro Tools
        3. import_audio_to_timeline() - Perform operations
        4. disconnect() - Clean up connection
    
    Key Concepts:
        - Session ID: Unique identifier from RegisterConnection, required for all operations
        - gRPC Channel: Persistent connection to PTSL server
        - Request/Response Pattern: All operations use SendGrpcRequest with JSON bodies
    
    Thread Safety:
        Not thread-safe. Create separate instances for concurrent operations.
        
    Attributes:
        address (str): PTSL server address in "host:port" format
        channel (grpc.Channel): gRPC channel for communication
        stub (PTSLStub): gRPC service stub for making requests
        connected (bool): Connection state flag
        session_id (str): Session identifier from Pro Tools (required for all requests)
    """
    
    def __init__(self, host: str = "localhost", port: int = 31416):
        """
        Initialize PTSL client instance.
        
        Creates client configuration but does NOT establish connection yet.
        Call connect() to actually connect to Pro Tools.
        
        Args:
            host (str): PTSL server hostname or IP address
                       For local Pro Tools: always use "localhost"
                       For remote Pro Tools: use machine's IP (rare, network config needed)
            port (int): PTSL server TCP port
                       Default: 31416 (Pro Tools standard, not configurable)
                       
        Note:
            Multiple PTSLClient instances can coexist but each needs its own connection.
            Pro Tools can handle multiple concurrent PTSL connections.
        """
        self.address = f"{host}:{port}"
        self.channel = None          # gRPC channel - created in connect()
        self.stub = None             # gRPC stub - created in connect()
        self.connected = False       # Connection state tracking
        self.session_id = None       # Pro Tools session ID - obtained from RegisterConnection
        
    def connect(self, company_name: str = "Master Thesis", 
                app_name: str = "PT V2A Plugin") -> bool:
        """
        Establish connection to Pro Tools PTSL server and authenticate.
        
        Connection Process:
            1. Create insecure gRPC channel (localhost, no encryption needed)
            2. Create PTSLStub for making RPC calls
            3. Send RegisterConnection command with client identification
            4. Receive and store session_id for subsequent requests
            5. Set connected flag on success
        
        Authentication:
            - PTSL uses simple name-based identification 
            - company_name and app_name are displayed in Pro Tools logs
            - session_id is the actual authentication token for requests
            
        Prerequisites:
            - Pro Tools must be running
            - PTSL must be enabled in Pro Tools preferences
            - A Pro Tools session must be open
            - Port 31416 must not be blocked by firewall
        
        Args:
            company_name (str): Your company/institution name
                               Shown in Pro Tools PTSL connection logs
            app_name (str): Your application name
                           Shown in Pro Tools PTSL connection logs
            
        Returns:
            bool: True if connection and registration successful
                  False if connection failed or Pro Tools not ready
                  
        Side Effects:
            - Sets self.channel (gRPC channel)
            - Sets self.stub (gRPC service stub)
            - Sets self.session_id (authentication token)
            - Sets self.connected flag
            - Prints connection status to stdout
            - Prints errors to stderr
            
        Raises:
            No exceptions raised - all errors caught and logged
            
        Example:
            >>> client = PTSLClient()
            >>> if client.connect("MyCompany", "AudioTool"):
            >>>     print("Connected!")
            >>> else:
            >>>     print("Connection failed - check Pro Tools")
        """
        if not PROTOBUF_AVAILABLE:
            print("PTSL: Protobuf files not available", file=sys.stderr)
            print("Refer to .\\setup_ptsl_env.txt to generate PTSL_pb2.py and PTSL_pb2_grpc.py", file=sys.stderr)
            return False
        
        try:
            import json
            
            # Step 1: Create gRPC channel
            # insecure_channel = no TLS encryption (localhost connection is safe)
            self.channel = grpc.insecure_channel(self.address)
            
            # Step 2: Create gRPC service stub
            # This is the client-side interface for calling PTSL methods
            self.stub = PTSL_pb2_grpc.PTSLStub(self.channel)
            
            # Step 3: Build RegisterConnection request
            # All PTSL requests use the same Request protobuf message structure:
            # - header: Contains command ID, version, and session info
            # - request_body_json: JSON string with command-specific parameters
            request = PTSL_pb2.Request()
            request.header.command = PTSL_pb2.CommandId.CId_RegisterConnection
            
            # Version numbers MUST match Pro Tools version (critical!)
            # Pro Tools 2025.6.0 requires these exact values
            request.header.version = 2025           # Major version
            request.header.version_minor = 6        # Minor version  
            request.header.version_revision = 0     # Revision
            
            # RegisterConnection request body (as JSON string)
            # PTSL uses JSON within protobuf for flexibility
            body_json = {
                "company_name": company_name,        # Your organization
                "application_name": app_name         # Your app name
            }
            request.request_body_json = json.dumps(body_json)
            
            # Step 4: Send request to Pro Tools
            # All PTSL commands use the same SendGrpcRequest RPC method
            # The specific command is identified by request.header.command
            response = self.stub.SendGrpcRequest(request)
            
            # Step 5: Check for errors in response
            # PTSL returns errors as JSON in response_error_json field
            if response.response_error_json:
                print(f"PTSL: Registration error: {response.response_error_json}", file=sys.stderr)
                self.connected = False
                return False
            
            # Step 6: Parse response and extract session_id
            # Verify we got the expected response type
            if response.header.command == PTSL_pb2.CommandId.CId_RegisterConnection:
                # Debug: Print response header fields (for troubleshooting)
                # This shows all fields in the response header
                print(f"PTSL: Response header fields:")
                for field in response.header.DESCRIPTOR.fields:
                    value = getattr(response.header, field.name)
                    print(f"  {field.name}: {value}")
                
                # Extract session_id from response body
                # RegisterConnection returns session_id in JSON body
                # This is the authentication token for all subsequent requests
                if response.response_body_json:
                    response_data = json.loads(response.response_body_json)
                    print(f"PTSL: Response body: {json.dumps(response_data, indent=2)}")
                    
                    # Store session_id - CRITICAL for all future requests!
                    if 'session_id' in response_data:
                        self.session_id = response_data['session_id']
                        print(f"PTSL: Session ID from body: {self.session_id}")
                
                # Response header also contains task_id (for async operations)
                if hasattr(response.header, 'task_id') and response.header.task_id:
                    print(f"PTSL: Task ID from header: {response.header.task_id}")
                
                print(f"PTSL: Connected to {self.address}")
                print(f"PTSL: Registered as '{company_name} - {app_name}'")
                self.connected = True
                return True
            else:
                print(f"PTSL: Registration failed", file=sys.stderr)
                self.connected = False
                return False
            
        except grpc.RpcError as e:
            print(f"PTSL: gRPC Error - {e.code()}: {e.details()}", file=sys.stderr)
            self.connected = False
            return False
        except Exception as e:
            print(f"PTSL: Connection failed - {e}", file=sys.stderr)
            self.connected = False
            return False
    
    def get_session_name(self) -> Optional[str]:
        """
        Retrieve the name of the currently open Pro Tools session.
        
        This is useful for:
        - Verifying a session is open before operations
        - Displaying session context to users
        - Logging which session was modified
        
        PTSL Command: GetSessionName (CId_GetSessionName)
        - Empty request body
        - Returns: {"session_name": "My Session"}
        
        Note:
            PTSL operations only work when a session is open.
            Import, track creation, etc. all require an active session.
        
        Returns:
            str: Session name (e.g., "My Project", "Untitled")
            None: If no session is open, not connected, or query failed
            
        Example:
            >>> session = client.get_session_name()
            >>> if session:
            >>>     print(f"Current session: {session}")
            >>> else:
            >>>     print("No session open - please open a session first")
        """
        if not self.connected or not PROTOBUF_AVAILABLE:
            return None
        
        try:
            import json
            
            # Create GetSessionName request
            request = PTSL_pb2.Request()
            request.header.command = PTSL_pb2.CommandId.CId_GetSessionName
            request.header.version = 2025
            request.header.version_minor = 6
            request.header.version_revision = 0
            
            if self.session_id:
                request.header.session_id = self.session_id
            
            request.request_body_json = "{}"  # Empty body
            
            response = self.stub.SendGrpcRequest(request)
            
            if response.response_error_json:
                return None
            
            if response.response_body_json:
                data = json.loads(response.response_body_json)
                return data.get('session_name', None)
            
            return None
        except Exception as e:
            print(f"PTSL: Failed to get session name - {e}", file=sys.stderr)
            return None
    

    
    def import_audio_to_timeline(
        self,
        audio_file_path: str,
        location: str = "SessionStart",
        destination: str = "NewTrack"
    ) -> Optional[str]:
        """
        Import an audio file to the Pro Tools timeline, creating a new track automatically.
        
        This is the main method for integrating generated audio into Pro Tools sessions.
        
        Features:
            - Automatic FLAC → WAV conversion (PTSL requires WAV format)
            - Path normalization (Windows backslashes → Unix forward slashes)
            - Long path name expansion (resolves 8.3 short names like USERNA~1)
            - Session validation (ensures Pro Tools session is open)
            - Automatic track creation at specified timeline position
        
        PTSL Import Process:
            1. Verify Pro Tools session is open
            2. Convert FLAC to WAV if needed (Pro Tools/PTSL limitation)
            3. Normalize file path format
            4. Build Import request with:
               - import_type: "IType_Audio" (audio file import)
               - file_list: [audio_file_path]
               - destination: "MD_NewTrack" (create new track)
               - location: "ML_Spot" with location_data (precise positioning)
            5. Send request synchronously
            6. Verify completion status
        
        Known Limitations:
            - PTSL does NOT support FLAC format (converted to WAV automatically)
            - Only WAV files are reliably imported
            - Import is synchronous (blocks until complete or fails)
            - No progress reporting during import
        
        Args:
            audio_file_path (str): Absolute path to audio file
                                  Supported: WAV (native), FLAC (converted)
                                  Example: "C:/Users/Me/audio/generated.flac"
            location (str): Timeline position for imported audio
                           Note: Currently fixed to "SessionStart" (sample 0)
                           Parameter kept for future flexibility
            destination (str): Import destination
                              Note: Currently fixed to "NewTrack"
                              Parameter kept for future flexibility
            
        Returns:
            str: Success message if import completed
            None: If import failed (check stderr for error details)
            
        Side Effects:
            - May create WAV file in same directory as FLAC (if conversion needed)
            - Creates new audio track in Pro Tools session
            - Places audio clip on timeline at session start
            - Prints progress and status messages to stdout
            - Prints errors to stderr
            
        Raises:
            No exceptions raised - all errors caught and logged
            
        Example:
            >>> client = PTSLClient()
            >>> if client.connect():
            >>>     # Import FLAC (auto-converted to WAV)
            >>>     result = client.import_audio_to_timeline("C:/audio/output.flac")
            >>>     if result:
            >>>         print("Audio imported successfully!")
            >>>     client.disconnect()
        """
        # Prerequisite check: must be connected to Pro Tools
        if not self.connected or not PROTOBUF_AVAILABLE:
            print("PTSL: Not connected to Pro Tools", file=sys.stderr)
            print("Call connect() first before importing audio", file=sys.stderr)
            return None
        
        # Critical requirement: Pro Tools session must be open
        # PTSL operations fail silently if no session is active
        session_name = self.get_session_name()
        if not session_name:
            print("PTSL: No Pro Tools session is open! Please open or create a session.", file=sys.stderr)
            return None
        
        print(f"PTSL: Current session: {session_name}")
        
        try:
            import json
            
            # Create request
            request = PTSL_pb2.Request()
            request.header.command = PTSL_pb2.CommandId.CId_Import
            request.header.version = 2025
            request.header.version_minor = 6
            request.header.version_revision = 0
            
            # Add session ID
            if self.session_id:
                request.header.session_id = self.session_id
            
            # ===== CRITICAL: FLAC → WAV CONVERSION =====
            # PTSL/Pro Tools does NOT support FLAC format for import!
            # Symptoms if FLAC used: Import command returns "Completed" but nothing appears on timeline
            # Root cause discovered: PTSL silently ignores unsupported formats
            # Solution: Convert FLAC to 24-bit PCM WAV before sending to PTSL
            import os
            from pathlib import Path
            
            actual_file_path = audio_file_path
            
            if audio_file_path.lower().endswith('.flac'):
                print(f"PTSL: Converting FLAC to WAV for Pro Tools compatibility...")
                try:
                    # Use soundfile library for lossless audio conversion
                    # Preserves sample rate, channels, and audio data integrity
                    import soundfile as sf
                    
                    # Read FLAC file: returns numpy array (samples) and sample rate (Hz)
                    data, samplerate = sf.read(audio_file_path)
                    
                    # Write as 24-bit PCM WAV (Pro Tools standard)
                    # PCM_24 = 24-bit linear pulse code modulation (uncompressed)
                    wav_path = str(Path(audio_file_path).with_suffix('.wav'))
                    sf.write(wav_path, data, samplerate, subtype='PCM_24')
                    
                    print(f"PTSL: Converted to WAV: {wav_path}")
                    actual_file_path = wav_path  # Use converted WAV for import
                    
                except ImportError:
                    # soundfile not installed in virtual environment
                    print(f"PTSL: soundfile not available, trying with audio file as-is...")
                except Exception as e:
                    # Conversion failed (file corrupt, unsupported FLAC variant, etc.)
                    print(f"PTSL: Conversion failed: {e}, trying with audio file as-is...")
            
            # ===== PATH NORMALIZATION =====
            # PTSL requires Unix-style paths with forward slashes, even on Windows
            # Example: "C:/Users/Name/file.wav" not "C:\Users\Name\file.wav"
            normalized_path = actual_file_path.replace('\\', '/')
            
            # ===== EXPAND SHORT PATH NAMES (8.3 FORMAT) =====
            # Windows may use short names like "USERNA~1" instead of "Username"
            # PTSL may fail with short names, so expand to long path names
            # Example: C:/Users/USERNA~1/file.wav → C:/Users/Username/file.wav
            if os.path.exists(actual_file_path):
                try:
                    # Use Windows API to get long path name
                    # kernel32.GetLongPathNameW converts 8.3 short names to full names
                    import ctypes
                    from ctypes import wintypes
                    
                    # Configure Windows API function signature
                    GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
                    GetLongPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
                    GetLongPathNameW.restype = wintypes.DWORD
                    
                    # Call API with 260-character buffer (MAX_PATH)
                    buffer = ctypes.create_unicode_buffer(260)
                    get_long_path_name = GetLongPathNameW(actual_file_path, buffer, 260)
                    
                    # If successful, use long path name with forward slashes
                    if get_long_path_name:
                        normalized_path = buffer.value.replace('\\', '/')
                except:
                    # API call failed or not on Windows - use simple path
                    pass  # Fall back to simple replacement
            
            # ===== BUILD IMPORT REQUEST =====
            # PTSL Import command structure: JSON body within protobuf wrapper
            # 
            # CRITICAL LESSONS LEARNED:
            # 1. ALL enum values MUST be STRINGS (e.g., "IType_Audio" NOT integer 2)
            # 2. location_data is REQUIRED even for simple positioning
            # 3. Without audio_data wrapper, get PT_UnknownError
            # 4. Without location_data, get PT_InvalidParameter
            # 5. String enums prevent "SDK_VersionMismatch" errors
            
            body_json = {
                # import_type: Specifies what we're importing
                # "IType_Audio" = audio file (not MIDI, video, etc.)
                # Must be STRING, not integer enum value
                "import_type": "IType_Audio",
                
                # audio_data: Container for audio-specific import parameters
                "audio_data": {
                    # file_list: Array of file paths to import
                    # Must use forward slashes (Unix-style)
                    # Can import multiple files in one command
                    "file_list": [normalized_path],
                    
                    # destination: Where to place imported audio
                    # "MD_NewTrack" = create new track automatically
                    # Alternative: "MD_ClipList" (clip list only, no timeline placement)
                    "destination": "MD_NewTrack",
                    
                    # location: Positioning mode
                    # "ML_Spot" = use precise location_data positioning
                    # Alternatives: "ML_SessionStart", "ML_SongStart", "ML_Selection"
                    "location": "ML_Spot",
                    
                    # location_data: Precise timeline position (REQUIRED for ML_Spot)
                    "location_data": {
                        # location_type: Reference point for positioning
                        # "Start" = session beginning (sample 0)
                        "location_type": "Start",
                        
                        # location: Timeline position in specified time format
                        "location": {
                            # "0" = start position (sample 0 = beginning)
                            # Could use other values for offset from start
                            "location": "0",
                            
                            # time_type: Unit for location value
                            # "TLType_Samples" = samples (most precise)
                            # Alternatives: "TLType_Ticks", "TLType_MinSecs"
                            "time_type": "TLType_Samples"
                        }
                    }
                }
            }
            
            # Serialize request body to JSON string
            # PTSL uses JSON-within-protobuf pattern for flexibility
            request.request_body_json = json.dumps(body_json)
            
            print(f"PTSL: Importing audio file to Pro Tools...")
            
            # ===== SEND IMPORT REQUEST =====
            # Import is a SYNCHRONOUS command:
            # - Response.Status = 3 (Completed) means import finished
            # - No task polling needed (unlike some other PTSL commands)
            # - If Status ≠ 3, import failed
            response = self.stub.SendGrpcRequest(request)
            
            # ===== HANDLE RESPONSE =====
            
            # Check for PTSL errors (error_json takes precedence)
            if response.response_error_json:
                error_data = json.loads(response.response_error_json)
                print(f"PTSL: Import failed:", file=sys.stderr)
                print(json.dumps(error_data, indent=2), file=sys.stderr)
                # Common errors:
                # - PT_InvalidParameter: Missing or malformed parameter
                # - PT_FileNotFound: File path invalid or not accessible by Pro Tools
                # - SDK_VersionMismatch: Version headers don't match Pro Tools
                return None
            
            # Check response status code
            # Status enum values:
            #   0 = Unknown (unexpected)
            #   1 = InProgress (shouldn't happen for Import)
            #   2 = Succeeded (task completed successfully)
            #   3 = Completed (operation finished)
            #   4 = Failed (operation failed)
            status = response.header.status
            
            if status == 4:  # Failed
                print(f"PTSL: Import failed - status: Failed", file=sys.stderr)
                print(f"   Check Pro Tools for error messages or logs", file=sys.stderr)
                return None
                
            elif status == 3 or status == 2:  # Completed or Succeeded
                # Import successful! Audio now on Pro Tools timeline
                print(f"✅ Audio successfully imported to Pro Tools!")
                print(f"   Track: New track at session start")
                
                # Inform user about FLAC→WAV conversion if it occurred
                if actual_file_path.lower().endswith('.wav') and audio_file_path.lower().endswith('.flac'):
                    print(f"   Note: Converted from FLAC to WAV (PTSL requires WAV format)")
                
                return f"Audio imported successfully"
            else:
                # InProgress (1) or Unknown (0) - shouldn't happen for Import command
                # Import is synchronous, so non-terminal status is unexpected
                print(f"PTSL: Import status: {status} (unexpected for synchronous command)")
                print(f"✅ Audio import request accepted (unusual state)")
                return f"Audio import requested for {audio_file_path}"
            
        except grpc.RpcError as e:
            # gRPC-level errors (network issues, channel closed, etc.)
            print(f"PTSL: gRPC Error - {e.code()}: {e.details()}", file=sys.stderr)
            print(f"   Check if Pro Tools is still running and PTSL is enabled", file=sys.stderr)
            return None
            
        except Exception as e:
            # Python-level errors (file operations, JSON parsing, etc.)
            print(f"PTSL: Import failed - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return None
    
    def _wait_for_task_completion(self, task_id: str, timeout: int = 60) -> Optional[str]:
        """
        Poll PTSL task status until completion (for asynchronous commands).
        
        NOTE: Currently NOT used in this implementation!
        - Import command is synchronous (immediate Status 3/Completed)
        - No task polling needed for audio import
        - Kept for reference and potential future async PTSL operations
        
        This method demonstrates the task polling pattern for PTSL commands
        that return InProgress status and require periodic status checks.
        
        PTSL Task Lifecycle:
            1. Send command → Response with task_id in header
            2. Response.Status = 1 (InProgress)
            3. Poll GetTaskStatus until Status changes
            4. Status 2 (Succeeded) or 3 (Completed) = done
            5. Status 4 (Failed) or timeout = abort
        
        Commands that require task polling:
            - Export operations (large file generation)
            - Long-running audio processing
            - Batch operations
        
        Commands that DON'T require polling (synchronous):
            - Import (Status 3 returned immediately)
            - GetSessionName (immediate response)
            - Simple queries
        
        Args:
            task_id (str): Task ID from response header
                          Example: "550e8400-e29b-41d4-a716-446655440000"
            timeout (int): Maximum seconds to wait before aborting
                          Default: 60 seconds
            
        Returns:
            str: Success message if task completed (Status 2/3)
            None: If task failed, timed out, or error occurred
            
        Example:
            >>> # For hypothetical async command:
            >>> response = stub.SendGrpcRequest(export_request)
            >>> if response.header.status == 1:  # InProgress
            >>>     task_id = response.header.task_id
            >>>     result = client._wait_for_task_completion(task_id, timeout=120)
        """
        if not PROTOBUF_AVAILABLE:
            return None
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                import json
                
                # Create request
                request = PTSL_pb2.Request()
                request.header.command = PTSL_pb2.CommandId.CId_GetTaskStatus
                request.header.version = 2025
                request.header.version_minor = 6
                request.header.version_revision = 0
                
                # Add session ID
                if self.session_id:
                    request.header.session_id = self.session_id
                
                # Create GetTaskStatus body as JSON
                body_json = {"task_id": task_id}
                request.request_body_json = json.dumps(body_json)
                
                response = self.stub.SendGrpcRequest(request)
                
                # Debug: Print full response
                print(f"PTSL: Task status - command: {response.header.command}")
                print(f"PTSL: Task status - task_id: {response.header.task_id}")
                print(f"PTSL: Task status - response body: {response.response_body_json if response.response_body_json else 'empty'}")
                
                # Check all response fields
                for field in response.DESCRIPTOR.fields:
                    value = getattr(response, field.name)
                    if value:
                        print(f"PTSL: Response field '{field.name}': {str(value)[:200]}")
                
                # Parse response
                if response.response_body_json:
                    response_data = json.loads(response.response_body_json)
                    task_state = response_data.get("task_state", 0)
                    
                    print(f"PTSL: Task state: {task_state}")
                    
                    if task_state == 2:  # TS_Completed
                        print("PTSL: Task completed successfully!")
                        return "Import completed"
                    elif task_state == 3:  # TS_Failed
                        error_msg = response_data.get("error_message", "Unknown error")
                        print(f"PTSL: Task failed: {error_msg}", file=sys.stderr)
                        return None
                    elif task_state == 4:  # TS_Cancelled
                        print("PTSL: Task was cancelled", file=sys.stderr)
                        return None
                
                # Still in progress, wait a bit
                time.sleep(0.5)
                
            except Exception as e:
                print(f"PTSL: Task status check failed - {e}", file=sys.stderr)
                return None
        
        print(f"PTSL: Task timeout after {timeout} seconds", file=sys.stderr)
        return None
    
    def disconnect(self):
        """
        Close the gRPC connection to PTSL server gracefully.
        
        Cleanup Operations:
            - Closes gRPC channel (releases network resources)
            - Sets connected flag to False
            - Does NOT close Pro Tools session (session remains open)
        
        Call this when:
            - Finished with all PTSL operations
            - Application shutting down
            - Switching to different PTSL server/port
        
        Thread Safety:
            Safe to call multiple times (idempotent)
            Safe to call if never connected
        
        Example:
            >>> client = PTSLClient()
            >>> try:
            >>>     client.connect()
            >>>     client.import_audio_to_timeline("audio.flac")
            >>> finally:
            >>>     client.disconnect()  # Always cleanup
        """
        if self.channel:
            self.channel.close()
            self.connected = False
            print("PTSL: Disconnected from Pro Tools")
        else:
            # Already disconnected or never connected
            self.connected = False


def import_audio_to_pro_tools(
    audio_path: str,
    location: str = "SessionStart",
    host: str = "localhost",
    port: int = 31416
) -> bool:
    """
    Convenience wrapper function for one-shot audio import to Pro Tools.
    
    This is a simplified interface that handles the full connection lifecycle:
    1. Create PTSLClient instance
    2. Connect to Pro Tools
    3. Import audio file
    4. Disconnect cleanly
    
    Use this when:
        - You need a quick one-time import
        - You don't need to keep connection alive
        - You're calling from standalone scripts (not long-running services)
    
    Use PTSLClient directly when:
        - Performing multiple operations (more efficient to keep connection)
        - Building interactive applications
        - Need fine-grained control over connection lifecycle
    
    Args:
        audio_path (str): Absolute path to audio file (WAV or FLAC)
                         FLAC will be automatically converted to WAV
                         Example: "C:/Users/Me/output/audio.flac"
        location (str): Timeline position (currently unused, fixed to SessionStart)
                       Kept for API compatibility
        host (str): PTSL server hostname
                   Default: "localhost" (Pro Tools on same machine)
        port (int): PTSL server port
                   Default: 31416 (Pro Tools PTSL default)
        
    Returns:
        bool: True if import succeeded, False if failed
        
    Side Effects:
        - Creates and destroys gRPC connection
        - May create WAV file (if input is FLAC)
        - Creates new track in Pro Tools
        - Prints progress messages to stdout
        - Prints errors to stderr
        
    Example:
        >>> # Simple usage from standalone script
        >>> success = import_audio_to_pro_tools("C:/audio/generated.flac")
        >>> if success:
        >>>     print("Audio is now in Pro Tools!")
        >>>
        >>> # Custom PTSL server
        >>> success = import_audio_to_pro_tools(
        >>>     "C:/audio/file.wav",
        >>>     host="192.168.1.100",
        >>>     port=31416
        >>> )
    """
    client = PTSLClient(host, port)
    
    if not client.connect():
        return False
    
    try:
        result = client.import_audio_to_timeline(
            audio_file_path=audio_path,
            location=location,
            destination="NewTrack"
        )
        
        return result is not None
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    """Test PTSL connection"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test PTSL connection and import")
    parser.add_argument("--audio", help="Audio file to import (for testing)")
    parser.add_argument("--host", default="localhost", help="PTSL host")
    parser.add_argument("--port", type=int, default=31416, help="PTSL port")
    
    args = parser.parse_args()
    
    print(f"Testing PTSL connection to {args.host}:{args.port}...")
    
    client = PTSLClient(args.host, args.port)
    
    if client.connect():
        print("✅ Connected to Pro Tools!")
        
        if args.audio:
            print(f"\nAttempting to import: {args.audio}")
            result = client.import_audio_to_timeline(args.audio)
            
            if result:
                print(f"✅ {result}")
            else:
                print("❌ Import failed")
        
        client.disconnect()
    else:
        print("❌ Connection failed")
        print("\nMake sure:")
        print("1. Pro Tools is running")
        print("2. PTSL is enabled (Setup > Preferences > MIDI > Enable PTSL)")
        print("3. No firewall is blocking port 31416")
