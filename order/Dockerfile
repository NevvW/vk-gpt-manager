FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/order

COPY requirements.txt /app/order/
RUN pip install --no-cache-dir -r /app/order/requirements.txt

COPY . /app/order/

RUN python manage.py migrate
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "order.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]

