#!/usr/bin/env node
// Discord selfbot - complete implementation with modern evasion.
// Uses axios for REST and ws for WebSocket. Node's TLS fingerprint
// is harder to spoof, but we keep the header and property structure
// identical to the official client.

const axios = require('axios');
const WebSocket = require('ws');
const crypto = require('crypto');

class DiscordSelfbot {
    constructor(token) {
        this.token = token;
        // Build an axios instance with the correct base URL.
        this.client = axios.create({
            baseURL: 'https://discord.com/api/v10',
            timeout: 30000,
            headers: this._buildHeaders()
        });
        this.ws = null;
        this.wsHeartbeat = null;
        this.running = false;
    }

    // Device properties – must match a real client.
    _deviceProperties() {
        return {
            os: 'Windows',
            os_version: '10.0.19045',
            browser: 'Discord',
            device: '',
            system_locale: 'en-US',
            client_version: '1.0.9166',
            client_build_number: 288475,
            release_channel: 'stable',
            design_id: 0,
            has_client_mods: false,
            launch_signature: crypto.randomBytes(16).toString('hex'),
            client_launch_id: crypto.randomBytes(16).toString('hex')
        };
    }

    // Context properties – dynamic per request.
    _contextProperties(location = 'Guild Sidebar', guildId = null, channelId = null) {
        return {
            location: location,
            location_guild_id: guildId,
            location_channel_id: channelId,
            location_channel_type: 0
        };
    }

    // Build the complete header set for a REST call.
    _buildHeaders(endpoint = '', guildId = null, channelId = null) {
        const props = this._deviceProperties();
        const propsB64 = Buffer.from(JSON.stringify(props)).toString('base64');
        const ctx = this._contextProperties(undefined, guildId, channelId);
        const ctxB64 = Buffer.from(JSON.stringify(ctx)).toString('base64');

        return {
            'Authorization': this.token,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Discord/1.0.9166 Chrome/124.0.6367.243 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://discord.com',
            'Referer': 'https://discord.com/channels/@me',
            'X-Super-Properties': propsB64,
            'X-Context-Properties': ctxB64,
            'X-Discord-Locale': 'en-US',
            'X-Discord-Timezone': 'America/New_York',
            'Sec-Ch-Ua': '"Chromium";v="124", "Discord";v="1.0.9166"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        };
    }

    // Internal request with retry logic and rate‑limit handling.
    async _request(method, endpoint, data = null, guildId = null, channelId = null) {
        // Update headers for this specific request.
        this.client.defaults.headers = this._buildHeaders(endpoint, guildId, channelId);

        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                const resp = await this.client.request({ method, url: endpoint, data });
                if (resp.status === 429) {
                    const retryAfter = resp.data.retry_after || 5;
                    await this._sleep((retryAfter + Math.random() * 1.5) * 1000);
                    continue;
                }
                return resp.data;
            } catch (err) {
                if (err.response?.status >= 500) {
                    await this._sleep((2 ** attempt + Math.random()) * 1000);
                    continue;
                }
                throw err;
            }
        }
        throw new Error('Request failed after retries');
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // -----------------------------------------------------------------
    // REST API – all user‑level endpoints
    // -----------------------------------------------------------------

    async getUser() {
        return this._request('GET', '/users/@me');
    }

    async getGuilds() {
        return this._request('GET', '/users/@me/guilds');
    }

    async getRelationships() {
        return this._request('GET', '/users/@me/relationships');
    }

    async getSettings() {
        return this._request('GET', '/users/@me/settings');
    }

    async setStatus(status = 'online', customText = null) {
        const payload = { status, since: 0, activities: [] };
        if (customText) {
            payload.activities.push({ name: customText, type: 0, created_at: Date.now() });
        }
        return this._request('PATCH', '/users/@me/settings', payload);
    }

    async getNote(userId) {
        return this._request('GET', `/users/@me/notes/${userId}`);
    }

    async setNote(userId, note) {
        return this._request('PUT', `/users/@me/notes/${userId}`, { note });
    }

    async getChannel(channelId) {
        return this._request('GET', `/channels/${channelId}`, null, null, channelId);
    }

    async createDM(recipientId) {
        return this._request('POST', '/users/@me/channels', { recipient_id: recipientId });
    }

    async sendMessage(channelId, content) {
        return this._request(
            'POST',
            `/channels/${channelId}/messages`,
            { content, nonce: String(Date.now()) },
            null,
            channelId
        );
    }

    async editMessage(channelId, messageId, content) {
        return this._request(
            'PATCH',
            `/channels/${channelId}/messages/${messageId}`,
            { content },
            null,
            channelId
        );
    }

    async deleteMessage(channelId, messageId) {
        await this._request('DELETE', `/channels/${channelId}/messages/${messageId}`, null, null, channelId);
    }

    async getMessages(channelId, limit = 50) {
        return this._request('GET', `/channels/${channelId}/messages?limit=${limit}`, null, null, channelId);
    }

    async addReaction(channelId, messageId, emoji) {
        await this._request(
            'PUT',
            `/channels/${channelId}/messages/${messageId}/reactions/${emoji}/@me`,
            null,
            null,
            channelId
        );
    }

    async removeReaction(channelId, messageId, emoji) {
        await this._request(
            'DELETE',
            `/channels/${channelId}/messages/${messageId}/reactions/${emoji}/@me`,
            null,
            null,
            channelId
        );
    }

    async joinGuild(inviteCode) {
        return this._request('POST', `/invites/${inviteCode}`);
    }

    async leaveGuild(guildId) {
        await this._request('DELETE', `/users/@me/guilds/${guildId}`, null, guildId);
    }

    async getGuildMembers(guildId, limit = 1000) {
        return this._request('GET', `/guilds/${guildId}/members?limit=${limit}`, null, guildId);
    }

    async getGuildChannels(guildId) {
        return this._request('GET', `/guilds/${guildId}/channels`, null, guildId);
    }

    // -----------------------------------------------------------------
    // WebSocket gateway
    // -----------------------------------------------------------------

    async connectGateway() {
        const gateway = await this._request('GET', '/gateway');
        const url = gateway.url;

        this.running = true;
        this.ws = new WebSocket(`${url}/?v=10&encoding=json`);

        this.ws.on('open', () => {
            // IDENTIFY payload – must match the REST properties.
            const identify = {
                op: 2,
                d: {
                    token: this.token,
                    properties: this._deviceProperties(),
                    presence: { status: 'online', since: 0, activities: [], afk: false },
                    compress: false,
                    large_threshold: 250,
                    client_state: { guild_versions: {}, highest_last_message_id: '0' }
                }
            };
            this.ws.send(JSON.stringify(identify));
        });

        this.ws.on('message', (data) => {
            try {
                const msg = JSON.parse(data);
                const op = msg.op;
                const t = msg.t;

                if (op === 10) {
                    const interval = msg.d.heartbeat_interval;
                    this._startHeartbeat(interval);
                } else if (op === 11) {
                    // Heartbeat ACK – do nothing
                } else if (t === 'MESSAGE_CREATE') {
                    const m = msg.d;
                    console.log(`[${m.author.username}]: ${m.content}`);
                } else if (t === 'READY') {
                    console.log(`Gateway ready: ${msg.d.user.username}`);
                }
            } catch (_) {
                // Ignore malformed messages
            }
        });

        this.ws.on('error', (err) => console.error('WebSocket error:', err.message));
        this.ws.on('close', () => {
            this.running = false;
            if (this.wsHeartbeat) {
                clearInterval(this.wsHeartbeat);
                this.wsHeartbeat = null;
            }
        });
    }

    _startHeartbeat(interval) {
        if (this.wsHeartbeat) clearInterval(this.wsHeartbeat);
        this.wsHeartbeat = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ op: 1, d: null }));
            }
        }, interval);
    }

    disconnectGateway() {
        this.running = false;
        if (this.wsHeartbeat) {
            clearInterval(this.wsHeartbeat);
            this.wsHeartbeat = null;
        }
        if (this.ws) this.ws.close();
    }
}

// -------------------------------------------------------------------
// Example usage
// -------------------------------------------------------------------
(async () => {
    const TOKEN = 'YOUR_USER_TOKEN';
    const bot = new DiscordSelfbot(TOKEN);

    const user = await bot.getUser();
    console.log(`Logged in: ${user.username}#${user.discriminator || '0'}`);

    await bot.setStatus('online', 'Custom status');
    await bot.connectGateway();

    process.on('SIGINT', () => {
        bot.disconnectGateway();
        process.exit(0);
    });
})();
