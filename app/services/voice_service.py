import json
import httpx
import logging
import socket
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.database.models.product_definition import ProductDefinition
from app.tasks.report_tasks import generate_inventory_report, generate_expiry_report, generate_audit_report_task, generate_temperature_report

logger = logging.getLogger(__name__)

class VoiceService:
    @classmethod
    def get_system_prompt(cls, product_list_str: str = "") -> str:
         return f"""
You are a warehouse assistant. Your ONLY job is to extract the intent from the user's command and output strict JSON.
NO explanations. NO markdown. NO extra text.

AVAILABLE PRODUCTS - USE ONLY THESE NAMES AND BARCODES, OTHERWISE RETURN UNKNOWN (Name -> Barcode):
{product_list_str}

Supported Intents:

1. GENERATE REPORT
   - Keywords: "raport", "zestawienie", "generate report"
   - JSON: {{"action": "report_generate", "parameters": {{"type": "inventory" | "expiry" | "temperature" | "audit"}}}}
   - INSTRUCTIONS:
     - "expiry" = Raport Terminów Ważności (Produkty przeterminowane/bliskie terminu)
     - "temperature" = Raport Temperatur
     - "audit" = Pełny Audyt Magazynu
   - Examples:
     "Sprawdź temperatury" -> {{"action": "report_generate", "parameters": {{"type": "temperature"}}}}

2. INBOUND PROCESS (Przyjęcie Towaru)
   - Keywords: "przyjmij", "dodaj na stan", "inbound", "odbierz"
   - JSON: {{"action": "process_inbound", "parameters": {{"product_name": "string", "barcode": "string", "quantity": "integer"}}}}
   - INSTRUCTIONS: 
     - Match the product name EXACTLY to the "AVAILABLE PRODUCTS" list. Do not use generic names if a specific one exists (e.g. use "Mleko 3.2%" instead of "mleko").
     - Set "barcode" to the corresponding ID from the list.
     - IF QUANTITY IS NOT MENTIONED, DEFAULT TO 1.
   - Examples:
     "Przyjmij 50 sztuk mleka" -> {{"action": "process_inbound", "parameters": {{"product_name": "Mleko 3.2%", "barcode": "123456", "quantity": 50}}}}
     "Rozpocznij przyjęcie" -> {{"action": "process_inbound", "parameters": {{}}}}
     "Przyjmij paletę wody" -> {{"action": "process_inbound", "parameters": {{"product_name": "Woda Mineralna", "barcode": "789012", "quantity": 1}}}}
     "Dodaj na stan Colę" -> {{"action": "process_inbound", "parameters": {{"product_name": "Coca Cola 0.5L", "barcode": "111222", "quantity": 1}}}}

3. OUTBOUND PROCESS (Wydanie Towaru)
   - Keywords: "wydaj", "zdejmij", "outbound", "wysyłka"
   - JSON: {{"action": "process_outbound", "parameters": {{"product_name": "string", "barcode": "string", "quantity": "integer"}}}}
   - INSTRUCTIONS: 
     - Match the product name EXACTLY to the "AVAILABLE PRODUCTS" list.
     - Set "barcode" to the corresponding ID.
     - IF QUANTITY IS NOT MENTIONED, DEFAULT TO 1.
   - Examples:
     "Wydaj paletę wody" -> {{"action": "process_outbound", "parameters": {{"product_name": "Woda Mineralna", "barcode": "789012", "quantity": 1}}}}
     "Przygotuj wysyłkę" -> {{"action": "process_outbound", "parameters": {{}}}}
     "Zdejmij mleko" -> {{"action": "process_outbound", "parameters": {{"product_name": "Mleko 3.2%", "barcode": "123456", "quantity": 1}}}}
     "Wydaj 5 sztuk Acetonu" -> {{"action": "process_outbound", "parameters": {{"product_name": "Aceton techniczny", "barcode": "QR-ACETON-001", "quantity": 5}}}}

4. UNKNOWN
   - If unclear: {{"action": "unknown", "parameters": {{}}}}
"""

    @classmethod
    async def process_command(cls, text: str, db: AsyncSession = None) -> dict:
        try:
            logger.info(f"Processing voice command: {text}")
            
            # Fetch products if DB session is provided
            product_context = ""
            if db:
                products = await cls._fetch_products(db)
                product_context = "\n".join([f"- {p['name']} (ID: {p['barcode']})" for p in products])
            
            system_prompt = cls.get_system_prompt(product_context)

            if settings.VOICE_LLM_PROVIDER == "ollama":
                 return await cls._process_with_ollama(text, system_prompt)
            elif settings.VOICE_LLM_PROVIDER == "openai":
                 return await cls._process_with_openai(text, system_prompt)
            else:
                 return {"status": "error", "message": f"Unknown Voice Provider: {settings.VOICE_LLM_PROVIDER}"}

        except Exception as e:
            logger.error(f"Error processing voice command: {e}")
            return {"status": "error", "message": str(e)}

    @classmethod
    async def _fetch_products(cls, db: AsyncSession) -> list[dict]:
        try:
            result = await db.execute(select(ProductDefinition))
            products = result.scalars().all()
            return [{"name": p.name, "barcode": p.barcode} for p in products]
        except Exception as e:
            logger.error(f"Failed to fetch products for context: {e}")
            return []

    @classmethod
    async def _process_with_ollama(cls, text: str, system_prompt: str) -> dict:
        url = settings.OLLAMA_URL
        prompt = f"{system_prompt}\n\nUser Command: {text}\nJSON Response:"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "model": settings.VOICE_LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json" 
                }
            )
            response.raise_for_status()
            result = response.json()
            
            # Parse LLM response
            llm_response_text = result.get("response", "")
            if not llm_response_text and "thinking" in result:
                 # Some models (e.g. reasoning models) put content in "thinking"
                 llm_response_text = result.get("thinking", "")
                 
            # Clean up potential markdown formatting
            llm_response_text = llm_response_text.replace("```json", "").replace("```", "").strip()
            
            intent_data = json.loads(llm_response_text)
            
            logger.info(f"LLM Intent: {intent_data}")
            return await cls._execute_intent(intent_data)

    @classmethod
    async def _process_with_openai(cls, text: str) -> dict:
         if not settings.VOICE_LLM_API_KEY:
              return {"status": "error", "message": "Missing VOICE_LLM_API_KEY configuration."}

         headers = {
             "Authorization": f"Bearer {settings.VOICE_LLM_API_KEY}",
             "Content-Type": "application/json"
         }
         
         base_url = settings.VOICE_LLM_BASE_URL or "https://api.openai.com/v1"
         url = f"{base_url}/chat/completions"

         messages = [
             {"role": "system", "content": cls.SYSTEM_PROMPT},
             {"role": "user", "content": text}
         ]

         async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": settings.VOICE_LLM_MODEL,
                    "messages": messages,
                    "temperature": 0,
                    # "response_format": {"type": "json_object"} # Enable if supported by provider
                }
            )
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            intent_data = json.loads(content)
             
            logger.info(f"LLM Intent (OpenAI): {intent_data}")
            return await cls._execute_intent(intent_data)


    @classmethod
    async def _execute_intent(cls, intent_data: dict) -> dict:
        action = intent_data.get("action")
        params = intent_data.get("parameters", {})
        
        if action == "report_generate":
            report_type = params.get("type")
            if report_type == "inventory":
                 task = generate_inventory_report.delay()
                 return {"status": "success", "message": "Generowanie raportu inwentaryzacji rozpoczęte.", "task_id": str(task.id)}
            elif report_type == "temperature":
                 task = generate_temperature_report.delay()
                 return {"status": "success", "message": "Generowanie raportu temperatur rozpoczęte.", "task_id": str(task.id)}
            else:
                 return {"status": "error", "message": f"Nieznany typ raportu: {report_type}"}

        elif action == "process_inbound":
            product = params.get("product")
            qty = params.get("quantity")
            msg = "Rozpoczynam proces przyjęcia."
            if product:
                msg += f" Produkt: {product}."
            if qty:
                msg += f" Ilość: {qty}."
            return {
                "status": "success",
                "message": msg,
                "action": "navigate_inbound", # Signal for frontend?
                "data": params
            }

        elif action == "process_outbound":
            product = params.get("product")
            msg = "Rozpoczynam proces wydania."
            if product:
                msg += f" Produkt: {product}."
            return {
                "status": "success",
                "message": msg,
                "action": "navigate_outbound",
                "data": params
            }
            
        elif action == "product_add":
             # Placeholder for product add logic
             product = params.get("product")
             qty = params.get("quantity")
             return {"status": "success", "message": f"Dodawanie produktu: {product}, Ilość: {qty} (Symulacja)"}

        elif action == "unknown":
            return {"status": "error", "message": "Nie zrozumiałem polecenia."}
            
        else:
            return {"status": "error", "message": f"Nieobsługiwana akcja: {action}"}
