#!/usr/bin/env python3
# Discord selfbot - production implementation with modern evasion
# Uses tls-client for TLS fingerprint spoofing (Chrome 124) and
# full WebSocket gateway support. Works on Linux/Windows.

import json
import base64
import time
import random
import secrets
import threading
import tls_client
import websocket

# -------------------------------------------------------------------
# The core class. Handles REST API and WebSocket gateway.
# All headers and properties match a real Discord desktop client.
# -------------------------------------------------------------------

class DiscordSelfbot:
    def __init__(self, token: str):
        self.token = token
        # TLS session mimics Chrome 124 – this avoids the obvious
        # fingerprint that normal requests or urllib3 leave behind.
        self.session = tls_client.Session(
            client_identifier="chrome_124",
            random_tls_extension_order=True
        )
        self.ws = None
        self.ws_thread = None
        self.running = False

    # -----------------------------------------------------------------
    # Device properties – the X-Super-Properties header.
    # The launch_signature must be random per request to avoid
    # static fingerprinting. has_client_mods must be false.
    # -----------------------------------------------------------------
    def _device_properties(self):
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

    # X-Context-Properties – tells Discord where the request comes from.
    # We set location to 'Guild Sidebar' by default; can be overridden.
    def _context_properties(self, location="Guild Sidebar", guild_id=None, channel_id=None):
        return {
            "location": location,
            "location_guild_id": guild_id,
            "location_channel_id": channel_id,
            "location_channel_type": 0
        }

    # Build full headers for a given endpoint.
    def _headers(self, endpoint: str, guild_id=None, channel_id=None):
        props = self._device_properties()
        props_b64 = base64.b64encode(json.dumps(props).encode()).decode()
        ctx = self._context_properties(guild_id=guild_id, channel_id=channel_id)
        ctx_b64 = base64.b64encode(json.dumps(ctx).encode()).decode()

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
            "X-Context-Properties": ctx_b64,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "America/New_York",
            "Sec-Ch-Ua": '"Chromium";v="124", "Discord";v="1.0.9166"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

    # Internal request handler with retry and rate‑limit backoff.
    def _request(self, method: str, endpoint: str, data=None, guild_id=None, channel_id=None):
        url = f"https://discord.com/api/v10{endpoint}"
        headers = self._headers(endpoint, guild_id, channel_id)

        for attempt in range(3):
            resp = self.session.request(method, url, headers=headers, json=data)
            if resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 5)
                time.sleep(retry_after + random.uniform(0.5, 1.5))
                continue
            if resp.status_code >= 500:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            resp.raise_for_status()
            return resp.json() if resp.text else None
        raise RuntimeError("Request failed after retries")

    # -----------------------------------------------------------------
    # REST API – full coverage of user‑level endpoints.
    # -----------------------------------------------------------------

    def get_user(self):
        return self._request("GET", "/users/@me")

    def get_guilds(self):
        return self._request("GET", "/users/@me/guilds")

    def get_relationships(self):
        return self._request("GET", "/users/@me/relationships")

    def get_settings(self):
        return self._request("GET", "/users/@me/settings")

    def set_status(self, status="online", custom_text=None):
        payload = {"status": status, "since": 0, "activities": []}
        if custom_text:
            payload["activities"].append({
                "name": custom_text,
                "type": 0,
                "created_at": int(time.time() * 1000)
            })
        return self._request("PATCH", "/users/@me/settings", payload)

    def get_note(self, user_id):
        return self._request("GET", f"/users/@me/notes/{user_id}")

    def set_note(self, user_id, note):
        return self._request("PUT", f"/users/@me/notes/{user_id}", {"note": note})

    # Channels & messages
    def get_channel(self, channel_id):
        return self._request("GET", f"/channels/{channel_id}", channel_id=channel_id)

    def create_dm(self, recipient_id):
        return self._request("POST", "/users/@me/channels", {"recipient_id": recipient_id})

    def send_message(self, channel_id, content):
        return self._request(
            "POST",
            f"/channels/{channel_id}/messages",
            {"content": content, "nonce": str(int(time.time() * 1000))},
            channel_id=channel_id
        )

    def edit_message(self, channel_id, message_id, content):
        return self._request(
            "PATCH",
            f"/channels/{channel_id}/messages/{message_id}",
            {"content": content},
            channel_id=channel_id
        )

    def delete_message(self, channel_id, message_id):
        self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}", channel_id=channel_id)

    def get_messages(self, channel_id, limit=50):
        return self._request("GET", f"/channels/{channel_id}/messages?limit={limit}", channel_id=channel_id)

    def add_reaction(self, channel_id, message_id, emoji):
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=channel_id
        )

    def remove_reaction(self, channel_id, message_id, emoji):
        self._request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=channel_id
        )

    # Guild management
    def join_guild(self, invite_code):
        return self._request("POST", f"/invites/{invite_code}")

    def leave_guild(self, guild_id):
        self._request("DELETE", f"/users/@me/guilds/{guild_id}", guild_id=guild_id)

    def get_guild_members(self, guild_id, limit=1000):
        return self._request("GET", f"/guilds/{guild_id}/members?limit={limit}", guild_id=guild_id)

    def get_guild_channels(self, guild_id):
        return self._request("GET", f"/guilds/{guild_id}/channels", guild_id=guild_id)

    # -----------------------------------------------------------------
    # WebSocket gateway – real‑time events with proper IDENTIFY.
    # -----------------------------------------------------------------

    def _on_open(self, ws):
        # The IDENTIFY payload must match the REST fingerprint exactly.
        identify = {
            "op": 2,
            "d": {
                "token": self.token,
                "properties": self._device_properties(),
                "presence": {"status": "online", "since": 0, "activities": [], "afk": False},
                "compress": False,
                "large_threshold": 250,
                "client_state": {"guild_versions": {}, "highest_last_message_id": "0"}
            }
        }
        ws.send(json.dumps(identify))

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            op = data.get("op")
            t = data.get("t")

            if op == 10:   # Hello – start heartbeat
                interval = data["d"]["heartbeat_interval"]
                self._heartbeat_loop(ws, interval)
            elif op == 11:
                pass   # ACK, ignore
            elif t == "MESSAGE_CREATE":
                msg = data["d"]
                print(f"[{msg['author']['username']}]: {msg['content']}")
            elif t == "READY":
                print(f"Gateway ready: {data['d']['user']['username']}")
        except:
            pass

    def _heartbeat_loop(self, ws, interval):
        # Heartbeat in a separate thread to keep connection alive.
        def beat():
            while self.running:
                time.sleep(interval / 1000)
                if self.running:
                    ws.send(json.dumps({"op": 1, "d": None}))
        threading.Thread(target=beat, daemon=True).start()

    def connect_gateway(self):
        gateway = self._request("GET", "/gateway")["url"]
        self.running = True
        self.ws = websocket.WebSocketApp(
            f"{gateway}/?v=10&encoding=json",
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=lambda ws, e: print("WS error:", e),
            on_close=lambda ws, code, msg: setattr(self, "running", False)
        )
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()

    def disconnect_gateway(self):
        self.running = False
        if self.ws:
            self.ws.close()


# -------------------------------------------------------------------
# Example usage
# -------------------------------------------------------------------
if __name__ == "__main__":
    TOKEN = "YOUR_USER_TOKEN"

    bot = DiscordSelfbot(TOKEN)
    user = bot.get_user()
    print(f"Logged in: {user['username']}#{user.get('discriminator', '0')}")

    bot.set_status("online", "Custom presence")
    bot.connect_gateway()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.disconnect_gateway()
