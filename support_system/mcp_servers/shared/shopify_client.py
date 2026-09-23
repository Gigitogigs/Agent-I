class SharedShopifyClient:
    """
    Authenticated connection handle for the Shopify Admin API.

    Holds the shop URL and access token required for every Shopify API call.
    This client is intentionally thin — it only stores credentials and is
    designed to be reused across multiple domain adapters (e.g. order-account
    and inventory) rather than duplicating connection setup in each adapter.

    In production, initialise this class once at server startup and pass the
    single instance to all adapters that need Shopify access.

    Args:
        shop_url: The full Shopify store URL (e.g. ``"https://my-store.myshopify.com"``).
        access_token: The Shopify Admin API access token for authentication.
    """

    def __init__(self, shop_url: str, access_token: str):
        """
        Initialise the client and store credentials for later use by adapters.

        Args:
            shop_url: The full Shopify store URL
                (e.g. ``"https://my-store.myshopify.com"``).
            access_token: The Shopify Admin API access token obtained during
                app installation or via private app credentials.
        """
        self.shop_url = shop_url
        self.access_token = access_token
        # In a real implementation, you would initialize your GraphQL or REST session here.
