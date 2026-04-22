"""whyllm proxy layer — shared httpx client pool."""

from whyllm_api.proxy.client import close_proxy_client, get_proxy_client, init_proxy_client

__all__ = ["get_proxy_client", "init_proxy_client", "close_proxy_client"]
