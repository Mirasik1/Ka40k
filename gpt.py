import base64
from io import BytesIO
from PIL import Image
from API_KEYS import OPENAI_API_KEY
import requests
import datetime
import os
import db

LOG_FILE = "gpt_usage.log"

def analyze_food(photo_bytes,user_description):
    # --- подготовка изображения ---
    image = Image.open(BytesIO(photo_bytes))
    image = image.convert("RGB")
    image = image.resize((512, 512))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    compressed_bytes = buffer.getvalue()

    photo_b64 = base64.b64encode(compressed_bytes).decode("utf-8")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    prompt = f"""
    Ты профессиональный нутрициолог и эксперт по анализу состава продуктов.  
    Твоя задача: проанализировать продукт(ы) на фото и вернуть результат строго в формате JSON.  

    ВАЖНО:  
    - Игнорируй фон, упаковку, надписи и посторонние объекты.  
    - Если еда надкусанная или частично съедена — учитывай её как если бы она была целой.  
    - Если на фото несколько продуктов — каждый продукт оформить как отдельный объект (product_1, product_2 и т.д.).  
    - Снаружи укажи общее число продуктов ("total_products").  
    - Если на тарелке цельное блюдо (например суп, салат, плов) — считать его одним продуктом.  
    - Напитки не учитывать.  
    - Если на тарелке есть отдельные дополнительные продукты (например хлеб, булочки) — учитывать их отдельно.  
    - Каждому продукту добавь поле "name" — короткое и лаконичное название блюда/продукта, отражающее его главный ингредиент или тип (например "Плов с курицей", "Рис с курицей").  
    - После названия пользователь может добавить собственное описание блюда в формате: {{{user_description}}}.  

    СТРОГО соблюдай следующую структуру для ответа:

    {{
      "total_products": <число>,
      "products": {{
        "product_1": {{
          "name": "<название блюда или продукта {' ' + user_description if user_description else ''}>",
          "weight": <число грамм>,
          "per_100g": {{
            "protein": <г>,
            "fat": <г>,
            "carbs": <г>
          }}
        }},
        "product_2": {{
          "name": "<название блюда или продукта {' ' + user_description if user_description else ''}>",
          "weight": <число грамм>,
          "per_100g": {{
            "protein": <г>,
            "fat": <г>,
            "carbs": <г>
          }}
        }}
        ...
      }}
    }}
    """

    data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": "Ты нутрициолог, отвечай только JSON."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"}}
            ]}
        ],
        "max_tokens": 600
    }

    response = requests.post(url, headers=headers, json=data).json()
    content = response["choices"][0]["message"]["content"]

    usage = response.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)


    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    img_path = f"logs/photo_{timestamp}.jpg"
    db.save_log(img_path,total_tokens)
    return content
