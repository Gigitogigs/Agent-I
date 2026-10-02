import httpx

async def verify_shopify(config: dict, client: httpx.AsyncClient) -> bool:
    store_url = config.get("store_url", "").rstrip("/")
    token = config.get("access_token", "")
    resp = await client.get(f"{store_url}/admin/api/2024-01/shop.json",
                             headers={"X-Shopify-Access-Token": token}, timeout=10.0)
    return resp.status_code == 200

async def verify_zendesk(config: dict, client: httpx.AsyncClient) -> bool:
    sub = config.get("subdomain", "")
    email = config.get("email", "")
    token = config.get("api_token", "")
    resp = await client.get(f"https://{sub}.zendesk.com/api/v2/users/me.json",
                             auth=(f"{email}/token", token), timeout=10.0)
    return resp.status_code == 200

async def verify_custom_mcp(config: dict, client: httpx.AsyncClient) -> bool:
    from mcp.client.streamable_http import streamable_http_client
    from mcp import ClientSession

    server_url = config.get("server_url", "")
    auth_token = config.get("auth_token", "")
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    
    try:
        async with streamable_http_client(server_url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return True
    except Exception:
        return False

VERIFIERS = {
    "shopify": verify_shopify,
    "zendesk": verify_zendesk,
    "custom_mcp": verify_custom_mcp,
    "inhouse": None,   # no external system to ping; always succeeds
}
