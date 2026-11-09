FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY admin-panel/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY admin-panel/app.py admin-panel/index.html admin-panel/instagram.py admin-panel/instagram_translations.py admin-panel/schedule_info.py admin-panel/media.py admin-panel/instagram_gallery.py admin-panel/instagram_reel.py admin-panel/instagram_editorial.py admin-panel/instagram_story.py admin-panel/instagram_campaign.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
