FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

#CMD ["sh","-c","sleep 100000"]
#ENV DJANGO_SETTINGS_MODULE=order.settings

CMD ["python", "vk_bot.py"]
