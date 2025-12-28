import os
import json
import base64
import requests
import time
import psutil
import unicodedata
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Disable SSL warnings since LCU uses self-signed certificates
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class LCUCredentials:
    """LCU connection credentials."""

    port: int
    password: str
    base_url: str

    @property
    def auth_header(self) -> str:
        """Generate Basic auth header for LCU requests."""
        credentials = base64.b64encode(f"riot:{self.password}".encode()).decode()
        return f"Basic {credentials}"


class LCUClient:
    """League Client Update API client for connecting to the LoL client."""

    def __init__(self, verbose: bool = False):
        self.credentials: Optional[LCUCredentials] = None
        self.session = requests.Session()
        self.session.verify = False  # Ignore self-signed SSL cert
        self.verbose = verbose

    def find_lcu_credentials(self) -> Optional[LCUCredentials]:
        """
        Find LCU credentials using multiple methods.

        Returns:
            LCUCredentials if found, None otherwise
        """
        # Method 1: Try lockfile approach
        credentials = self._find_credentials_lockfile()
        if credentials:
            return credentials

        # Method 2: Try process list approach
        credentials = self._find_credentials_process()
        if credentials:
            return credentials

        return None

    def _find_credentials_lockfile(self) -> Optional[LCUCredentials]:
        """Find credentials using the League client lockfile."""
        try:
            # Common League installation paths
            possible_paths = [
                os.path.expandvars(r"C:\Riot Games\League of Legends\lockfile"),
                os.path.expandvars(r"%LOCALAPPDATA%\Riot Games\League of Legends\lockfile"),
                # Add more paths if needed
            ]

            if self.verbose:
                print("[DEBUG] Looking for lockfile...")
            for lockfile_path in possible_paths:
                if self.verbose:
                    print(f"[DEBUG] Checking: {lockfile_path}")
                if os.path.exists(lockfile_path):
                    if self.verbose:
                        print(f"[DEBUG] Found lockfile!")
                    with open(lockfile_path, "r") as f:
                        lockfile_content = f.read().strip()

                    if self.verbose:
                        print(f"[DEBUG] Lockfile content: {lockfile_content}")

                    # Format: "LeagueClient:PID:PORT:PASSWORD:https"
                    parts = lockfile_content.split(":")
                    if len(parts) >= 5:
                        port = int(parts[2])
                        password = parts[3]
                        base_url = f"https://127.0.0.1:{port}"

                        if self.verbose:
                            print(f"[DEBUG] Parsed - Port: {port}, Password: {password[:5]}...")
                        return LCUCredentials(port=port, password=password, base_url=base_url)
                    else:
                        if self.verbose:
                            print(f"[DEBUG] Invalid lockfile format")
                elif self.verbose:
                    print(f"[DEBUG] Not found")
        except Exception as e:
            print(f"[ERROR] Error reading lockfile: {e}")

        return None

    def _find_credentials_process(self) -> Optional[LCUCredentials]:
        """Find credentials by scanning running processes."""
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if proc.info["name"] and "LeagueClientUx" in proc.info["name"]:
                        cmdline = proc.info.get("cmdline", [])
                        if not cmdline:
                            continue

                        # Look for port and password in command line args
                        port = None
                        password = None

                        for i, arg in enumerate(cmdline):
                            if "--app-port=" in arg:
                                port = int(arg.split("=")[1])
                            elif "--remoting-auth-token=" in arg:
                                password = arg.split("=")[1]
                                # Handle truncated tokens in process list
                                if password.endswith("..."):
                                    continue  # Skip truncated, try lockfile instead

                        if port and password:
                            base_url = f"https://127.0.0.1:{port}"
                            return LCUCredentials(port=port, password=password, base_url=base_url)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            print(f"Error scanning processes: {e}")

        return None

    def connect(self) -> bool:
        """
        Establish connection to the LCU.

        Returns:
            True if connection successful, False otherwise
        """
        if self.verbose:
            print("[INFO] Searching for League client...")

        self.credentials = self.find_lcu_credentials()
        if not self.credentials:
            print("[ERROR] League client not found. Make sure LoL client is running.")
            return False

        # Test connection
        try:
            if self.verbose:
                print(f"[DEBUG] Testing connection to {self.credentials.base_url}")
            response = self._make_request("/lol-summoner/v1/current-summoner")
            if self.verbose:
                print(f"[DEBUG] Response received: {response}")
            if response and (response.get("gameName") or response.get("displayName")):
                summoner_name = response.get("displayName") or response.get("gameName", "Unknown")
                print(f"[SUCCESS] Connected to League client!")
                if self.verbose:
                    print(f"[INFO] Summoner: {summoner_name}")
                    print(f"[INFO] LCU Port: {self.credentials.port}")
                return True
            else:
                print(f"[ERROR] No valid response or missing summoner info")
        except Exception as e:
            print(f"[ERROR] Failed to connect to LCU: {e}")

        return False

    def _make_request(
        self, endpoint: str, method: str = "GET", data: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make a request to the LCU API.

        Args:
            endpoint: API endpoint (e.g. "/lol-champ-select/v1/session")
            method: HTTP method
            data: Request data for POST/PUT/PATCH

        Returns:
            Response JSON or None if error
        """
        if not self.credentials:
            return None

        url = f"{self.credentials.base_url}{endpoint}"
        headers = {"Authorization": self.credentials.auth_header}

        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, timeout=5)
            elif method == "POST":
                response = self.session.post(url, headers=headers, json=data, timeout=5)
            elif method == "PATCH":
                response = self.session.patch(url, headers=headers, json=data, timeout=5)
            elif method == "PUT":
                response = self.session.put(url, headers=headers, json=data, timeout=5)
            else:
                return None

            if response.status_code in [200, 204]:  # Include 204 No Content for PATCH success
                try:
                    return response.json() if response.content else {}
                except:
                    return {}  # For successful requests with no content
            elif response.status_code == 404:
                return None  # Endpoint not found (normal when not in champ select)
            else:
                if self.verbose:
                    print(f"[WARNING] LCU API error: {response.status_code}")
                return None

        except requests.exceptions.RequestException as e:
            if self.verbose:
                print(f"[WARNING] Request error: {e}")
            return None

    def get_champion_select_session(self) -> Optional[Dict[str, Any]]:
        """
        Get current champion select session data.

        Returns:
            Champion select data or None if not in champ select
        """
        return self._make_request("/lol-champ-select/v1/session")

    def get_gameflow_session(self) -> Optional[Dict[str, Any]]:
        """
        Get current game flow session (lobby, champ select, in-game, etc.).

        Returns:
            Game flow data or None if error
        """
        return self._make_request("/lol-gameflow/v1/session")

    def is_in_champion_select(self) -> bool:
        """
        Check if currently in champion select.

        Returns:
            True if in champion select, False otherwise
        """
        gameflow = self.get_gameflow_session()
        if gameflow:
            phase = gameflow.get("phase", "")
            return phase == "ChampSelect"
        return False

    def is_in_ready_check(self) -> bool:
        """
        Check if currently in ready check (queue found).

        Returns:
            True if in ready check, False otherwise
        """
        gameflow = self.get_gameflow_session()
        if gameflow:
            phase = gameflow.get("phase", "")
            return phase == "ReadyCheck"
        return False

    def get_ready_check_state(self) -> Optional[Dict[str, Any]]:
        """
        Get current ready check state.

        Returns:
            Ready check data or None if not in ready check
        """
        return self._make_request("/lol-matchmaking/v1/ready-check")

    def accept_ready_check(self) -> bool:
        """
        Accept the ready check when matchmaking finds a game.

        Returns:
            True if successful, False otherwise
        """
        if not self.is_in_ready_check():
            if self.verbose:
                print("[DEBUG] Not in ready check, cannot accept")
            return False

        result = self._make_request("/lol-matchmaking/v1/ready-check/accept", method="POST")
        if result is not None:
            if self.verbose:
                print("[SUCCESS] Ready check accepted")
            return True
        else:
            if self.verbose:
                print("[ERROR] Failed to accept ready check")
            return False

    def get_champion_id_by_name(self, champion_name: str) -> Optional[int]:
        """
        Get champion ID by champion name with flexible matching.

        Args:
            champion_name: Champion name (e.g. "DrMundo", "Aatrox")

        Returns:
            Champion ID or None if not found
        """
        response = self._make_request("/lol-champions/v1/owned-champions-minimal")
        if response:
            # Normalize input name for comparison
            search_name = self._normalize_champion_name(champion_name)

            for champion in response:
                client_name = champion.get("name", "")
                normalized_client_name = self._normalize_champion_name(client_name)

                # Try multiple matching strategies
                if (
                    client_name.lower() == champion_name.lower()
                    or normalized_client_name == search_name
                    or normalized_client_name == champion_name.lower()
                ):
                    return champion.get("id")
        return None

    def _normalize_champion_name(self, name: str) -> str:
        """Normalize champion name for flexible matching, handling accents and special characters."""
        # First, normalize Unicode and remove accents
        normalized = unicodedata.normalize("NFD", name)
        # Remove accent marks (combining characters)
        without_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Convert to lowercase and remove spaces, dots, apostrophes
        return without_accents.lower().replace(" ", "").replace(".", "").replace("'", "")

    def get_current_player_action_id(self) -> Optional[int]:
        """
        Get the current player's action ID in champion select.

        Returns:
            Action ID or None if not found
        """
        session = self.get_champion_select_session()
        if not session:
            return None

        local_player_cell_id = session.get("localPlayerCellId")
        if local_player_cell_id is None:
            return None

        # Find current action for local player
        for action_set in session.get("actions", []):
            for action in action_set:
                if (
                    action.get("actorCellId") == local_player_cell_id
                    and not action.get("completed", False)
                    and action.get("type") in ["pick", "hover"]
                ):
                    return action.get("id")

        return None

    def hover_champion(self, champion_name: str) -> bool:
        """
        Hover a champion during champion select.

        Args:
            champion_name: Champion name to hover

        Returns:
            True if successful, False otherwise
        """
        if not self.is_in_champion_select():
            if self.verbose:
                print("[DEBUG] Not in champion select, cannot hover")
            return False

        # Get champion ID
        champion_id = self.get_champion_id_by_name(champion_name)
        if not champion_id:
            # Enhanced debug information
            if self.verbose:
                print(f"[WARNING] Champion '{champion_name}' not found in client")
                # Show available champions for debugging
                response = self._make_request("/lol-champions/v1/owned-champions-minimal")
                if response:
                    similar_names = [c.get("name", "") for c in response[:5]]  # First 5 for debug
                    print(f"[DEBUG] Available champions sample: {similar_names}")
                    # Look for close matches
                    search_name = self._normalize_champion_name(champion_name)
                    close_matches = []
                    for c in response:
                        client_name = c.get("name", "")
                        if search_name in self._normalize_champion_name(client_name):
                            close_matches.append(client_name)
                    if close_matches:
                        print(f"[DEBUG] Possible matches: {close_matches[:3]}")
            return False

        # Get current action ID
        action_id = self.get_current_player_action_id()
        if not action_id:
            if self.verbose:
                print("[WARNING] No available action to update")
            return False

        # Update action to hover the champion
        endpoint = f"/lol-champ-select/v1/session/actions/{action_id}"
        data = {"championId": champion_id, "completed": False, "type": "pick"}

        result = self._make_request(endpoint, method="PATCH", data=data)
        if result is not None:  # None means error, {} means success
            if self.verbose:
                print(f"[SUCCESS] Hovered {champion_name} (ID: {champion_id})")
            return True
        else:
            if self.verbose:
                print(f"[ERROR] Failed to hover {champion_name}")
            return False

    def lock_champion(self, champion_name: str) -> bool:
        """
        Lock in a champion during champion select.

        Args:
            champion_name: Champion name to lock

        Returns:
            True if successful, False otherwise
        """
        if not self.is_in_champion_select():
            if self.verbose:
                print("[DEBUG] Not in champion select, cannot lock")
            return False

        # Get champion ID
        champion_id = self.get_champion_id_by_name(champion_name)
        if not champion_id:
            if self.verbose:
                print(f"[WARNING] Champion '{champion_name}' not found")
            return False

        # Get current action ID
        action_id = self.get_current_player_action_id()
        if not action_id:
            if self.verbose:
                print("[WARNING] No available action to update")
            return False

        # Update action to lock the champion
        endpoint = f"/lol-champ-select/v1/session/actions/{action_id}"
        data = {"championId": champion_id, "completed": True, "type": "pick"}

        result = self._make_request(endpoint, method="PATCH", data=data)
        if result is not None:
            if self.verbose:
                print(f"[SUCCESS] Locked {champion_name} (ID: {champion_id})")
            return True
        else:
            if self.verbose:
                print(f"[ERROR] Failed to lock {champion_name}")
            return False

    def disconnect(self):
        """Clean up connection resources."""
        if self.session:
            self.session.close()
        self.credentials = None
