import json
import base64
import logging
from typing import Dict, Any, Optional
from .config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)


class ClaudeVision:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.base_url = "https://api.anthropic.com/v1"
    
    async def analyze_food(self, image_data: bytes) -> Dict[str, Any]:
        if not self.api_key:
            return self._fallback_response()
        
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        
        prompt = """Ты — эксперт по питанию. Проанализируй фото еды и верни JSON с точной структурой:
{
  "dish_name": "русское название блюда",
  "ingredients": [{"name": "ингредиент", "estimated_weight_g": число}],
  "total_weight_g": число (оценка общего веса порции),
  "calories_per_100g": число (ккал на 100г),
  "protein_g": число,
  "fat_g": число,
  "carbs_g": число,
  "confidence": 0.0-1.0,
  "needs_correction": true/false (нужна ли ручная корректировка веса)
}
Для оценки порции используй: сравнение с ложкой, вилкой, рукой, тарелкой на фото.
Верни только JSON без markdown."""
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/jpeg",
                                            "data": image_b64
                                        }
                                    },
                                    {"type": "text", "text": prompt}
                                ]
                            }
                        ]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    text = data.get("content", [{}])[0].get("text", "")
                    return self._parse_json_response(text)
                else:
                    logger.error(f"Claude API error: {response.status_code} {response.text}")
                    return self._fallback_response()
        except Exception as e:
            logger.exception(e)
            return self._fallback_response()
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        try:
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return self._fallback_response()
    
    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "dish_name": "Блюдо",
            "ingredients": [{"name": "еда", "estimated_weight_g": 150}],
            "total_weight_g": 150,
            "calories_per_100g": 150,
            "protein_g": 5,
            "fat_g": 5,
            "carbs_g": 20,
            "confidence": 0.3,
            "needs_correction": True
        }


async def analyze_food_image(image_data: bytes) -> Dict[str, Any]:
    analyzer = ClaudeVision()
    return await analyzer.analyze_food(image_data)