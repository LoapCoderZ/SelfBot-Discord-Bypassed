/**
 * Discord Selfbot - Production-grade implementation with real-device fingerprinting.
 * API version: v10
 */

const axios = require('axios');
const WebSocket = require('ws');
const crypto = require('crypto');

class DiscordSelfbot {
    /**
     * Full-featured Discord selfbot with REST API and WebSocket gateway support.
     */
    constructor(token) {
        this.token = token;
        this.ws = null;
        this.wsHeartbeat = null;
        this.running = false;

        this.client = axios.create({
            baseURL: 'https://discord.com/api/v10',
            timeout: 30000,
            headers: this._buildHeaders()
        });
    }

    /**
     * Generate realistic device fingerprint matching official Discord client.
     */
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

    /**
     * Construct full request headers with proper fingerprinting.
     */
    _buildHeaders() {
        const props = this._deviceProperties();
        const propsB64 = Buffer.from(JSON.stringify(props)).toString('base64');

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

    /**
     * Execute API request with automatic retry and rate-limit handling.
     * Discord uses a dual-layer architecture: REST API for state changes,
     * WebSocket gateway for real-time events[reference:13].
     */
    async _request(method, endpoint, data = null) {
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                const resp = await this.client.request({
                    method,
                    url: endpoint,
                    data
                });

                // Rate limit: Discord returns 429 with retry_after[reference:14]
                if (resp.status === 429) {
                    const retryAfter = resp.data.retry_after || 5;
                    await this._sleep((retryAfter + Math.random() * 1.5) * 1000);
                    continue;
                }

                return resp.data;

            } catch (err) {
                // Server errors: exponential backoff with jitter[reference:15]
                if (err.response?.status >= 500) {
                    await this._sleep((2 ** attempt + Math.random()) * 1000);
                    continue;
                }
                throw err;
            }
        }
        throw new Error('Request failed after maximum retries');
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ---- REST API: User Endpoints ----

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
            payload.activities.push({
                name: customText,
                type: 0,
                created_at: Date.now()
            });
        }
        return this._request('PATCH', '/users/@me/settings', payload);
    }

    async getNote(userId) {
        return this._request('GET', `/users/@me/notes/${userId}`);
    }

    async setNote(userId, note) {
        await this._request('PUT', `/users/@me/notes/${userId}`, { note });
    }

    // ---- REST API: Channel & Message Endpoints ----

    async getChannel(channelId) {
        return this._request('GET', `/channels/${channelId}`);
    }

    async createDM(recipientId) {
        return this._request('POST', '/users/@me/channels', { recipient_id: recipientId });
    }

    async sendMessage(channelId, content) {
        return this._request('POST', `/channels/${channelId}/messages`, {
            content,
            nonce: String(Date.now())
        });
    }

    async editMessage(channelId, messageId, content) {
        return this._request('PATCH', `/channels/${channelId}/messages/${messageId}`, {
            content
        });
    }

    async deleteMessage(channelId, messageId) {
        await this._request('DELETE', `/channels/${channelId}/messages/${messageId}`);
    }

    async getMessages(channelId, limit = 50) {
        return this._request('GET', `/channels/${channelId}/messages?limit=${limit}`);
    }

    async addReaction(channelId, messageId, emoji) {
        await this._request(
            'PUT',
            `/channels/${channelId}/messages/${messageId}/reactions/${emoji}/@me`
        );
    }

    async removeReaction(channelId, messageId, emoji) {
        await this._request(
            'DELETE',
            `/channels/${channelId}/messages/${messageId}/reactions/${emoji}/@me`
        );
    }

    // ---- REST API: Guild Endpoints ----

    async joinGuild(inviteCode) {
        return this._request('POST', `/invites/${inviteCode}`);
    }

    async leaveGuild(guildId) {
        await this._request('DELETE', `/users/@me/guilds/${guildId}`);
    }

    async getGuildMembers(guildId, limit = 1000) {
        return this._request('GET', `/guilds/${guildId}/members?limit=${limit}`);
    }

    async getGuildChannels(guildId) {
        return this._request('GET', `/guilds/${guildId}/channels`);
    }

    // ---- WebSocket Gateway ----

    /**
     * Establish WebSocket connection to Discord's gateway.
     * The gateway uses an opcode-based communication system for
     * real-time events[reference:16].
     */
    async connectGateway() {
        const gatewayData = await this._request('GET', '/gateway');
        const gatewayUrl = gatewayData.url;

        this.running = true;
        this.ws = new WebSocket(`${gatewayUrl}/?v=10&encoding=json`);

        this.ws.on('open', () => {
            const identifyPayload = {
                op: 2,
                d: {
                    token: this.token,
                    properties: this._deviceProperties(),
                    presence: {
                        status: 'online',
                        since: 0,
                        activities: [],
                        afk: false
                    },
                    compress: false,
                    large_threshold: 250
                }
            };
            this.ws.send(JSON.stringify(identifyPayload));
        });

        this.ws.on('message', (data) => {
            try {
                const payload = JSON.parse(data);
                const op = payload.op;
                const t = payload.t;

                if (op === 10) { // Hello - contains heartbeat interval
                    const interval = payload.d.heartbeat_interval;
                    this._startHeartbeat(interval);
                } else if (op === 11) { // Heartbeat ACK
                    // Acknowledgment received
                } else if (t === 'MESSAGE_CREATE') {
                    const msg = payload.d;
                    console.log(`[${msg.author.username}]: ${msg.content}`);
                } else if (t === 'READY') {
                    console.log(`WebSocket ready. Logged in as ${payload.d.user.username}`);
                }
            } catch (e) {
                // Ignore parse errors
            }
        });

        this.ws.on('error', (err) => {
            console.error('WebSocket error:', err.message);
        });

        this.ws.on('close', () => {
            this.running = false;
            if (this.wsHeartbeat) {
                clearInterval(this.wsHeartbeat);
                this.wsHeartbeat = null;
            }
            console.log('WebSocket disconnected');
        });
    }

    _startHeartbeat(interval) {
        if (this.wsHeartbeat) {
            clearInterval(this.wsHeartbeat);
        }
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
        if (this.ws) {
            this.ws.close();
        }
    }
}

// ---- Usage Example ----

(async () => {
    const TOKEN = 'YOUR_USER_TOKEN_HERE';

    const bot = new DiscordSelfbot(TOKEN);

    // Test REST API
    const user = await bot.getUser();
    console.log(`Logged in as: ${user.username}#${user.discriminator || '0'}`);

    // Set presence
    await bot.setStatus('online', 'Custom Status');

    // Connect to gateway for real-time events
    await bot.connectGateway();

    // Keep running
    process.on('SIGINT', () => {
        bot.disconnectGateway();
        console.log('Disconnected');
        process.exit(0);
    });
})();
