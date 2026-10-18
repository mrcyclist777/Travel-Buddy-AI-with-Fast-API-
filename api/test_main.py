import os
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from api.main import app, DATABASE_FILE

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "FastAPI TravelBuddy running"}


def test_plan_request_validation():
    # Walidacja Pydantic
    response = client.post("/api/plan", json={"destination": "Rzym", "days": "niepoprawna_liczba"})
    assert response.status_code == 422

def test_generate_plan_mocked():
    # Sztuczne zmienne środowiskowe 
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key", "UNSPLASH_ACCESS_KEY": "fake_unsplash_key"}):
        with patch("api.main.genai.Client") as mock_genai_client, patch("api.main.requests.get") as mock_requests_get:
            
            # Sztuczna odpowiedź Gemini AI przy pomocy Mock
            mock_gemini_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = json.dumps({
                "destination": "Paryż",
                "daysCount": 2,
                "itinerary": [
                    {
                        "day": 1,
                        "activities": [{"time": "10:00", "title": "Wieża Eiffla", "description": "Zwiedzanie"}]
                    }
                ]
            })
            mock_gemini_instance.models.generate_content.return_value = mock_response
            mock_genai_client.return_value = mock_gemini_instance

            # Sztuczna odpowiedź Unsplash API przy pomocy Mock
            mock_unsplash_response = MagicMock()
            mock_unsplash_response.status_code = 200
            mock_unsplash_response.json.return_value = {
                "results": [
                    {"urls": {"regular": "https://images.unsplash.com/mock-photo.jpg"}}
                ]
            }
            mock_requests_get.return_value = mock_unsplash_response

            response = client.post("/api/plan", json={
                "destination": "Paryż",
                "days": 2,
                "budget": "niski",
                "style": "kultura"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["destination"] == "Paryż"
            assert data["daysCount"] == 2
            assert data["imageUrl"] == "https://images.unsplash.com/mock-photo.jpg"
            assert len(data["itinerary"]) == 1