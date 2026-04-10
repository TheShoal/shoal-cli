import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger("shoal.price_oracle")


class PriceOracle:
    """
    Price Oracle for LLM models.
    Fetches and caches model pricing from OpenRouter.
    """

    def __init__(self, cache_dir: Path):
        self.cache_path = cache_dir / "prices.json"
        self.cache_ttl = timedelta(hours=24)
        self._cached_data: Optional[Dict[str, Any]] = None

    async def get_model_prices(self) -> Dict[str, Any]:
        """Return cached model prices or fetch fresh ones from OpenRouter."""
        if self._cached_data:
            return self._cached_data

        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r") as f:
                    data = json.load(f)

                updated_at = datetime.fromisoformat(data.get("updated_at", ""))
                if datetime.now() - updated_at < self.cache_ttl:
                    self._cached_data = data
                    return data
            except Exception as e:
                logger.warning("Failed to load price cache: %s", e)

        return await self.refresh_prices()

    async def refresh_prices(self) -> Dict[str, Any]:
        """Fetch fresh prices from OpenRouter and cache them."""
        import httpx

        logger.info("Refreshing model prices from OpenRouter...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("https://openrouter.ai/api/v1/models")
                response.raise_for_status()
                models_data = response.json().get("data", [])

                # OpenRouter returns a list of model objects.
                # We map them to a lookup table: model_id -> {prompt, completion}
                prices = {}
                for m in models_data:
                    m_id = m.get("id")
                    if m_id:
                        prices[m_id] = {
                            "prompt": m.get("pricing", {}).get("prompt", 0.0),
                            "completion": m.get("pricing", {}).get("completion", 0.0),
                        }

                cache_data = {"updated_at": datetime.now().isoformat(), "models": prices}

                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.cache_path, "w") as f:
                    json.dump(cache_data, f, indent=2)

                self._cached_data = cache_data
                return cache_data
        except Exception as e:
            logger.exception("Failed to refresh prices from OpenRouter: %s", e)
            # Fallback to stale cache if available
            if self.cache_path.exists():
                with open(self.cache_path, "r") as f:
                    return json.load(f)
            return {"updated_at": "", "models": {}}


# Global singleton for the app
_oracle: Optional[PriceOracle] = None


def get_oracle(cache_dir: Path) -> PriceOracle:
    global _oracle
    if _oracle is None:
        _oracle = PriceOracle(cache_dir)
    return _oracle
