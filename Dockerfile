FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

# Expose all OpenStack service ports
EXPOSE 5000 8774 8776 9292 9696 9876 10000 8999

CMD ["openstack-emulator"]
