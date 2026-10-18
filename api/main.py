import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, status, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from google import genai
import requests

app = FastAPI(
    title="TravelBuddyAI FastAPI",
    description=" Nowy backend FastAPI przeniesiony z Node.js / Express",
    version="1.0.0"
)

# Konfiguracja CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model danych Pydantic
class PlanRequest(BaseModel):
    destination: str = Field(..., min_length=2)
    days: int = Field(..., ge=1, le=30)
    budget: Optional[str] = "standardowy"
    style: Optional[str] = "mieszany"

class SavePlanRequest(BaseModel):
    destination: str
    daysCount: Optional[int] = None
    userId: Optional[str] = None
    itinerary: Optional[list] = None
    imageUrl: Optional[str] = None

DATABASE_FILE = Path(os.getcwd()) / "baza_podrozy.json"

def read_database() -> list:
    if not DATABASE_FILE.exists():
        return []
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            return json.loads(content) if content else []
    except Exception:
        return []

def write_database(data: list):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "FastAPI TravelBuddy running"}


# Generowanie planu z Gemini AI 
@app.post("/api/plan")
async def generate_plan(payload: PlanRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Brak skonfigurowanego klucza GEMINI_API_KEY"
        )

    prompt = f"""Stwórz szczegółowy plan podróży do: {payload.destination}. 
    Czas trwania: {payload.days} dni. 
    Budżet: {payload.budget}. 
    Styl podróży: {payload.style}.
    
    Odpowiedz WYŁĄCZNIE w formacie JSON (czysty obiekt, bez żadnego dodatkowego tekstu na początku i końcu).
    Struktura obiektu JSON musi być dokładnie taka:
    {{
      "destination": "{payload.destination}",
      "daysCount": {payload.days},
      "itinerary": [
        {{
          "day": 1,
          "activities": [
            {{ "time": "09:00", "title": "Nazwa atrakcji", "description": "Opis atrakcji" }}
          ]
        }}
      ]
    }}"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'system_instruction': 'Jesteś doświadczonym, profesjonalnym przewodnikiem turystycznym. Generujesz odpowiedzi tylko jako czysty format JSON.',
            }
        )

        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:-3].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:-3].strip()

        plan_json = json.loads(clean_text)

    except Exception as e:
        print(f"BŁĄD GEMINI:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd podczas generowania planu AI: {str(e)}"
        )

    # Unsplash API
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    destination_image = "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200"

    try:
        if unsplash_key:
            url = f"https://api.unsplash.com/search/photos?query={payload.destination}&per_page=1&orientation=landscape"
            headers = {"Authorization": f"Client-ID {unsplash_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    destination_image = results[0]["urls"]["regular"]
    except Exception as photo_error:
        print("Błąd podczas pobierania zdjęcia z Unsplash:", photo_error)

    plan_json["imageUrl"] = destination_image
    return plan_json


# Zapisywanie planu
@app.post("/api/save-plan")
async def save_plan(new_plan: Dict[Any, Any] = Body(...)):
    if not new_plan or not new_plan.get("destination"):
        raise HTTPException(status_code=400, detail="Nieprawidłowe dane planu.")

    db = read_database()
    import time
    from datetime import datetime

    plan_to_save = {
        "id": str(int(time.time() * 1000)),
        "createdAt": datetime.utcnow().isoformat() + "Z",
        **new_plan
    }

    db.append(plan_to_save)
    write_database(db)

    return {
        "success": True, 
        "message": "Plan został pomyślnie zapisany!", 
        "savedPlan": plan_to_save
    }


# Pobieranie zapisanego planu
@app.get("/api/saved-plans")
async def get_saved_plans(userId: Optional[str] = Query(None)):
    if not userId:
        raise HTTPException(status_code=400, detail="Brak zdefiniowanego identyfikatora użytkownika!")

    db = read_database()
    user_plans = [plan for plan in db if plan.get("userId") == userId]
    return user_plans


# Usuwanie planu
@app.delete("/api/delete-plan/{plan_id}")
async def delete_plan(plan_id: str):
    db = read_database()
    initial_length = len(db)
    
    db = [plan for plan in db if plan.get("id") != plan_id]

    if len(db) == initial_length:
        raise HTTPException(status_code=404, detail="Nie znaleziono planu o podanym ID.")

    write_database(db)
    return {"success": True, "message": "Plan został usunięty!"}


# Aktualizacja planu
@app.put("/api/update-plan/{plan_id}")
async def update_plan(plan_id: str, updated_data: Dict[Any, Any] = Body(...)):
    db = read_database()
    index = next((i for i, plan in enumerate(db) if plan.get("id") == plan_id), -1)

    if index == -1:
        raise HTTPException(status_code=404, detail="Nie znaleziono planu do edycji.")

    from datetime import datetime
    db[index] = {
        **db[index],
        **updated_data,
        "updatedAt": datetime.utcnow().isoformat() + "Z"
    }

    write_database(db)
    return {
        "success": True, 
        "message": "Plan został zaktualizowany!", 
        "updatedPlan": db[index]
    }