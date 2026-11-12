FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py index.html instagram.py instagram_translations.py schedule_info.py media.py instagram_gallery.py instagram_reel.py instagram_editorial.py instagram_story.py instagram_campaign.py instagram_facts.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
