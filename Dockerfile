FROM python:3.12-slim
WORKDIR /srv
COPY admin-panel/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY admin-panel/app.py admin-panel/index.html admin-panel/instagram.py admin-panel/instagram_translations.py admin-panel/schedule_info.py admin-panel/media.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
