FROM python:3.11-slim

# Build metadata (passed by CI). The installed package version already matches the
# release tag because the version bump is committed on the tagged commit; these
# just stamp the image so it self-reports its provenance.
ARG VERSION="latest"
ARG COMMIT_INFO="unknown"
LABEL org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$COMMIT_INFO"

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .

# Expose all OpenStack service ports
EXPOSE 5000 8774 8776 9292 9696 9876 10000 8999

CMD ["openstack-emulator"]
