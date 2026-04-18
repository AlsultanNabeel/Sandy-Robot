from typing import Any, Dict, List
import requests


def search_exa(query: str, exa_api_key: str, num_results: int = 10, timeout: int = 60) -> List[Dict[str, Any]]:
    """Search Exa and return simplified results."""
    if not exa_api_key:
        print("[Exa] ⚠️ EXA_API_KEY missing")
        return []

    try:
        url = "https://api.exa.ai/search"
        headers = {
            "x-api-key": exa_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "numResults": num_results,
            "type": "auto",
            "contents": {
                "text": True
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "text": str(item.get("text") or "").strip(),
                "published_date": str(item.get("publishedDate") or "").strip(),
            })

        print(f"[Exa] ✅ Found {len(results)} results for query: {query}")
        return results

    except Exception as e:
        print(f"[Exa] ❌ Search failed: {e}")
        return []


def get_exa_page_content(url: str, exa_api_key: str, timeout: int = 60) -> Dict[str, Any]:
    """Fetch page contents from Exa for a specific URL."""
    if not exa_api_key:
        print("[Exa] ⚠️ EXA_API_KEY missing")
        return {}

    try:
        api_url = "https://api.exa.ai/contents"
        headers = {
            "x-api-key": exa_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "urls": [url],
            "text": True
        }

        response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return {}

        item = results[0]
        return {
            "url": str(item.get("url") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "text": str(item.get("text") or "").strip(),
        }

    except Exception as e:
        print(f"[Exa] ❌ Contents fetch failed for {url}: {e}")
        return {}