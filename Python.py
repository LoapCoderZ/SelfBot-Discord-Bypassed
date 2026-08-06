"""
Discord Selfbot - Production-grade implementation with real-device fingerprinting.
API version: v10 [😭✌️]
"""

import requests
import json
import base64
import time
import random
import secrets
import websocket
import threading
from typing import Optional, Dict, Any, List


class DiscordSelfbot:
    """Full-featured Discord selfbot with REST API and WebSocket gateway support."""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(self._build_headers())
        self.ws = None
        self.ws_thread = None
        self.running = False

    def _device_properties(self) -> Dict[str, Any]:
        """Generate realistic device fingerprint matching official Discord client."""
        return {
            "os": "Windows",
            "os_version": "10.0.19045",
            "browser": "Discord",
            "device": "",
            "system_locale": "en-US",
            "client_version": "1.0.9166",
            "client_build_number": 288475,
            "release_channel": "stable",
            "design_id": 0,
            "has_client_mods": False,
            "launch_signature": secrets.token_hex(16),
            "client_launch_id": secrets.token_hex(16)
        }

    def _build_headers(self) -> Dict[str, str]:
        """Construct full request headers with proper fingerprinting."""
        props = self._device_properties()
        props_b64 = base64.b64encode(
            json.dumps(props, separators=(",", ":")).encode()
        ).decode()

        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Discord/1.0.9166 Chrome/124.0.6367.243 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
            "X-Super-Properties": props_b64,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "America/New_York",
            "Sec-Ch-Ua": '"Chromium";v="124", "Discord";v="1.0.9166"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Any:
        """
        Execute API request with automatic retry and rate-limit handling.
        Discord uses a dual-layer architecture: REST API for state changes,
        WebSocket gateway for real-time events[reference:9].
        """
        url = f"https://discord.com/api/v10{endpoint}"

        for attempt in range(3):
            try:
                resp = self.session.request(method, url, json=data, timeout=30)

                # Rate limit: Discord returns 429 with retry_after[reference:10]
                if resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 5)
                    time.sleep(retry_after + random.uniform(0.5, 1.5))
                    continue

                # Server errors: exponential backoff with jitter[reference:11]
                if resp.status_code >= 500:
                    time.sleep((2 ** attempt) + random.uniform(0, 1))
                    continue

                resp.raise_for_status()
                return resp.json() if resp.text else None

            except requests.exceptions.RequestException:
                if attempt == 2:
                    raise
                time.sleep((2 ** attempt) + random.uniform(0, 1))

        raise RuntimeError("Request failed after maximum retries")

    # ---- REST API: User Endpoints ----

    def get_user(self) -> Dict:
        """Fetch authenticated user information."""
        return self._request("GET", "/users/@me")

    def get_guilds(self) -> List[Dict]:
        """List all guilds the user is a member of."""
        return self._request("GET", "/users/@me/guilds")

    def get_relationships(self) -> List[Dict]:
        """Fetch user's friend list and relationship statuses."""
        return self._request("GET", "/users/@me/relationships")

    def get_settings(self) -> Dict:
        """Retrieve current user settings."""
        return self._request("GET", "/users/@me/settings")

    def set_status(self, status: str = "online", custom_text: Optional[str] = None) -> Dict:
        """
        Update presence status.
        Status options: online, idle, dnd, invisible
        """
        payload = {"status": status, "since": 0, "activities": []}
        if custom_text:
            payload["activities"].append({
                "name": custom_text,
                "type": 0,
                "created_at": int(time.time() * 1000)
            })
        return self._request("PATCH", "/users/@me/settings", payload)

    def get_notes(self, user_id: str) -> Dict:
        """Fetch note for a specific user."""
        return self._request("GET", f"/users/@me/notes/{user_id}")

    def set_note(self, user_id: str, note: str) -> None:
        """Set or update a note for a user."""
        self._request("PUT", f"/users/@me/notes/{user_id}", {"note": note})

    # ---- REST API: Channel & Message Endpoints ----

    def get_channel(self, channel_id: str) -> Dict:
        """Fetch channel information."""
        return self._request("GET", f"/channels/{channel_id}")

    def create_dm(self, recipient_id: str) -> Dict:
        """Create a direct message channel with another user."""
        return self._request("POST", "/users/@me/channels", {"recipient_id": recipient_id})

    def send_message(self, channel_id: str, content: str) -> Dict:
        """Send a message to a channel."""
        return self._request(
            "POST",
            f"/channels/{channel_id}/messages",
            {"content": content, "nonce": str(int(time.time() * 1000))}
        )

    def edit_message(self, channel_id: str, message_id: str, content: str) -> Dict:
        """Edit an existing message."""
        return self._request(
            "PATCH",
            f"/channels/{channel_id}/messages/{message_id}",
            {"content": content}
        )

    def delete_message(self, channel_id: str, message_id: str) -> None:
        """Delete a message."""
        self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")

    def get_messages(self, channel_id: str, limit: int = 50) -> List[Dict]:
        """Fetch recent messages from a channel."""
        return self._request("GET", f"/channels/{channel_id}/messages?limit={limit}")

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Add a reaction to a message."""
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        )

    def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Remove a reaction from a message."""
        self._request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        )

    # ---- REST API: Guild Endpoints ----

    def join_guild(self, invite_code: str) -> Dict:
        """Join a guild using an invite code."""
        return self._request("POST", f"/invites/{invite_code}")

    def leave_guild(self, guild_id: str) -> None:
        """Leave a guild."""
        self._request("DELETE", f"/users/@me/guilds/{guild_id}")

    def get_guild_members(self, guild_id: str, limit: int = 1000) -> List[Dict]:
        """Fetch members of a guild."""
        return self._request("GET", f"/guilds/{guild_id}/members?limit={limit}")

    def get_guild_channels(self, guild_id: str) -> List[Dict]:
        """Fetch all channels in a guild."""
        return self._request("GET", f"/guilds/{guild_id}/channels")

    # ---- WebSocket Gateway ----

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            op = data.get("op")
            t = data.get("t")

            if op == 10:  # Hello - contains heartbeat interval
                heartbeat_interval = data["d"]["heartbeat_interval"]
                self._heartbeat_thread(ws, heartbeat_interval)

            elif op == 11:  # Heartbeat ACK
                pass  # Acknowledgment received

            elif t == "MESSAGE_CREATE":
                msg = data["d"]
                print(f"[{msg['author']['username']}]: {msg['content']}")

            elif t == "READY":
                print(f"WebSocket ready. Logged in as {data['d']['user']['username']}")

        except json.JSONDecodeError:
            pass

    def _on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.running = False
        print("WebSocket disconnected")

    def _on_open(self, ws):
        """Send IDENTIFY payload on connection open."""
        identify_payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "properties": self._device_properties(),
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False
                },
                "compress": False,
                "large_threshold": 250
            }
        }
        ws.send(json.dumps(identify_payload))

    def _heartbeat_thread(self, ws, interval):
        """Maintain WebSocket connection with periodic heartbeats."""
        import time
        while self.running:
            time.sleep(interval / 1000)
            if self.running:
                ws.send(json.dumps({"op": 1, "d": None}))

    def connect_gateway(self):
        """
        Establish WebSocket connection to Discord's gateway.
        The gateway uses an opcode-based communication system for
        real-time events[reference:12].
        """
        # Fetch gateway URL
        gateway_data = self._request("GET", "/gateway")
        gateway_url = gateway_data["url"]

        self.running = True
        self.ws = websocket.WebSocketApp(
            f"{gateway_url}/?v=10&encoding=json",
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def disconnect_gateway(self):
        """Close WebSocket connection gracefully."""
        self.running = False
        if self.ws:
            self.ws.close()


# ---- Usage Example ----

if __name__ == "__main__":
    TOKEN = "YOUR_USER_TOKEN_HERE"

    bot = DiscordSelfbot(TOKEN)

    # Test REST API
    user = bot.get_user()
    print(f"Logged in as: {user['username']}#{user.get('discriminator', '0')}")

    # Set presence
    bot.set_status("online", "Custom Status")

    # Connect to gateway for real-time events
    bot.connect_gateway()

    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.disconnect_gateway()
        print("Disconnected")
