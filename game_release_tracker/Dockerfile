ARG BUILD_FROM=python:3.12-alpine
FROM ${BUILD_FROM}

RUN apk add --no-cache curl tzdata

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python3", "-u", "run.py" ]
