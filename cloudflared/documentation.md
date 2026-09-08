# Cloudflared Tunnel + Client Configuration

This guide covers the client side of remote access: how the AAX plugin and the companion scripts reach the backend through a Cloudflare Tunnel protected by a Cloudflare Access service token.
For creating the tunnel and running the connector on the server, see [SETUP.md](../SETUP.md), section "Cloudflared Tunnel".

## 1. Create the Cloudflare Access application

1. In Cloudflare Zero Trust, go to **Networks → Tunnels** and select your tunnel.
2. Under **Public Hostnames**, add the three services and point them to the containers:

   | Hostname (example)    | Service                                |
   |-----------------------|----------------------------------------|
   | `mmaudio.example.com` | `http://mmaudio-api:8000`              |
   | `hyvf.example.com`    | `http://hunyuanvideo-foley-api:8001`   |
   | `sounds.example.com`  | `http://sound-search-api:8002`         |

3. In **Access → Applications**, create a **Self-hosted** application that includes all three hostnames, with a **Service Auth** policy.
4. In **Access → Service Auth → Service Tokens**, create a token. Copy the **Client ID** and **Client Secret** now; you can regenerate them later.

## 2. Client configuration file

The plugin and the companion scripts share one configuration file in the user config directory. It is created with localhost defaults on first run:

- Windows: `%APPDATA%\PTV2A\config.json`
- macOS: `~/Library/PTV2A/config.json`

A complete example is [`companion/api/config.sample.json`](../companion/api/config.sample.json). To route through the tunnel, set `use_cloudflared` to `true`, enter your hostnames, and add the service token:

```json
{
  "use_cloudflared": true,
  "services": {
    "mmaudio": {
      "api_url_direct": "http://localhost:8000",
      "api_url_cloudflared": "https://mmaudio.example.com"
    },
    "hunyuan": {
      "api_url_direct": "http://localhost:8001",
      "api_url_cloudflared": "https://hyvf.example.com"
    },
    "sound_search": {
      "api_url_direct": "http://localhost:8002",
      "api_url_cloudflared": "https://sounds.example.com"
    }
  },
  "cf_access_client_id": "<your-client-id>",
  "cf_access_client_secret": "<your-client-secret>"
}
```

- `use_cloudflared: false` (default): clients use `api_url_direct` and send no access headers.
- `use_cloudflared: true`: clients use `api_url_cloudflared` and attach the `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers.
- The credentials can also be entered in the plugin via the **API Settings** button, which writes them into the same file.

## 3. How the clients use the config

- `companion/api/config.py` loads the file and merges it over the built-in defaults.
- `get_api_url(service)` returns the active URL for `mmaudio`, `hunyuan`, or `sound_search`.
- `get_cf_headers()` returns the access headers only when Cloudflare mode is on and both values are set.
- The AAX plugin reads the same file in `PluginProcessor::getConfiguredAPIUrl()`.

## 4. Companion CLI usage

No changes to CLI invocations are needed: with `use_cloudflared` on, requests go through the tunnel with the access headers; with it off, they go to the direct URL.
To override the configured URL for a single call, pass `--api-url`.

## 5. Rotating or revoking the token

- In Cloudflare Zero Trust → **Access → Service Auth → Service Tokens** you can revoke or regenerate the token.
- After rotating, update `config.json` (or re-enter the credentials in the plugin) and restart any running CLI sessions.

## 6. Troubleshooting

- If the health check fails, verify:
  - The tunnel connector is running: `docker compose -f docker-compose.full.yml logs -f cloudflared`
  - DNS records for the hostnames point to the tunnel.
  - The service token in `config.json` matches the one shown in Cloudflare Access.
- Confirm the headers work manually:
  `curl -H "CF-Access-Client-Id: …" -H "CF-Access-Client-Secret: …" https://mmaudio.example.com/`
- To inspect the loaded configuration, run from the `companion/` directory:
  `python -c "from api.config import get_config; print(get_config())"`
