import time
import random
import pandas as pd

from schema import Application, CITIES
from llm_client import make_client, get_model


client = make_client()
model = get_model()

APPLICATION_COUNT = 50

# Решение через стратификацию: 
# 50 заявок / 10 городов = по 5 на каждый город
city_queue = (CITIES * (APPLICATION_COUNT // len(CITIES) + 1))[:APPLICATION_COUNT]
random.shuffle(city_queue)

applications = []

for i, seed_city in enumerate(city_queue):
    seed_city = random.choice(CITIES)

    messages = [
        {
            "role": "system",
            "content": "Ты генерируешь реалистичные заявки на курсы повышения квалификации для российских специалистов."
        },
        {
            "role": "user",
            "content": (
                f"Сгенерируй одну заявку на курс повышения квалификации. "
                f"Seed-город: {seed_city}. "
                f"Сделай данные максимально разнообразными и реалистичными: "
                f"разные специальности, возрасты, опыт работы, желаемые курсы." 
            )
        }
    ]

    application: Application = client.chat.completions.create(
        model=model,
        messages=messages,
        response_model=Application,
        max_retries=3,
        temperature=0.9
    )
    applications.append(application)
    print(f"[{i+1}|{APPLICATION_COUNT}] {application.full_name} — {application.address.city}")

    time.sleep(2)

# Формируем датасет applications.csv:
rows = []
for application in applications:
    row = application.model_dump()
    row["city"] = row["address"]["city"]
    row["district"] = row["address"]["district"]
    del row["address"]
    rows.append(row)

df = pd.DataFrame(rows)
df.to_csv("applications.csv", index=False, encoding="utf-8")
print("Данные успешно сохранены в applications.csv")