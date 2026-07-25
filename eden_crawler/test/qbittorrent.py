"""Send magnet/torrent links to qBittorrent Web UI."""

import httpx


def add_magnet(magnet_url, host="http://127.0.0.1:8080", username="admin", password="adminadmin"):
    """POST a magnet link to qBittorrent. Returns True on success, False on failure."""
    try:
        with httpx.Client() as client:
            # Login
            client.post(f"{host}/api/v2/auth/login",
                        data={"username": username, "password": password})
            # Add torrent
            resp = client.post(f"{host}/api/v2/torrents/add",
                               data={"urls": magnet_url})
            return resp.status_code == 200
    except Exception:
        return False
