FROM python:3.6-slim-buster

COPY requirements.txt /app/hockeygamebot/requirements.txt
RUN pip install --no-cache-dir -r /app/hockeygamebot/requirements.txt

COPY . /app
WORKDIR /app

CMD [ "python" , "-m", "hockeygamebot", "--docker" ]